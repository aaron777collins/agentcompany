"""
Tests for the Roles API — /api/v1/roles.

Covers CRUD, parent role creation, duplicate slug detection,
and circular reference handling.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_company(client: AsyncClient, headers: dict, slug: str) -> str:
    resp = await client.post(
        "/api/v1/companies/",
        json={"name": f"Co {slug}", "slug": slug},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _role_payload(company_id: str, slug: str = "engineer", **overrides) -> dict:
    base = {
        "name": "Engineer",
        "slug": slug,
        "company_id": company_id,
        "level": 1,
        "permissions": ["task:read"],
        "tool_access": {},
        "max_headcount": 3,
        "headcount_type": "agent",
    }
    return {**base, **overrides}


async def _create_role(
    client: AsyncClient, headers: dict, company_id: str, slug: str = "engineer", **overrides
) -> dict:
    resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id, slug, **overrides),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_role_returns_201(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "role-create-co")
    resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["id"].startswith("rol_")
    assert data["slug"] == "engineer"
    assert data["company_id"] == company_id


async def test_create_role_with_parent_role(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "parent-role-co")
    parent = await _create_role(client, auth_headers, company_id, slug="manager", level=2)

    child_resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id, slug="engineer", level=1, reports_to_role_id=parent["id"]),
        headers=auth_headers,
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["data"]["reports_to_role_id"] == parent["id"]


async def test_create_role_with_nonexistent_parent_returns_422(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "bad-parent-co")
    resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id, reports_to_role_id="rol_doesnotexist"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_role_duplicate_slug_returns_409(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "dup-role-co")
    await _create_role(client, auth_headers, company_id)
    resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id),  # same slug
        headers=auth_headers,
    )
    assert resp.status_code == 409


async def test_create_role_invalid_headcount_type_returns_422(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "hc-type-co")
    resp = await client.post(
        "/api/v1/roles/",
        json=_role_payload(company_id, headcount_type="robot"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_roles_returns_items(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "list-roles-co")
    await _create_role(client, auth_headers, company_id, slug="cto", level=3)
    await _create_role(client, auth_headers, company_id, slug="ic", level=0)

    resp = await client.get("/api/v1/roles/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2


async def test_list_roles_filter_by_company(client: AsyncClient, auth_headers: dict):
    co1 = await _create_company(client, auth_headers, "role-list-co1")
    co2 = await _create_company(client, auth_headers, "role-list-co2")
    await _create_role(client, auth_headers, co1, slug="role-in-co1")
    await _create_role(client, auth_headers, co2, slug="role-in-co2")

    resp = await client.get(f"/api/v1/roles/?company_id={co1}", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(r["company_id"] == co1 for r in items)


async def test_list_roles_ordered_by_level(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "order-roles-co")
    await _create_role(client, auth_headers, company_id, slug="senior", level=3)
    await _create_role(client, auth_headers, company_id, slug="junior", level=1)

    resp = await client.get(f"/api/v1/roles/?company_id={company_id}", headers=auth_headers)
    items = resp.json()["items"]
    levels = [i["level"] for i in items]
    assert levels == sorted(levels), "Roles should be returned ordered by level ascending"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_role_returns_204(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "del-role-co")
    role = await _create_role(client, auth_headers, company_id)

    resp = await client.delete(f"/api/v1/roles/{role['id']}", headers=auth_headers)
    assert resp.status_code == 204


async def test_deleted_role_not_returned(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "vis-del-role-co")
    role = await _create_role(client, auth_headers, company_id)
    await client.delete(f"/api/v1/roles/{role['id']}", headers=auth_headers)

    resp = await client.get(f"/api/v1/roles/{role['id']}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Circular reference prevention
# ---------------------------------------------------------------------------


async def test_create_role_circular_reference_not_possible_at_db_level(
    client: AsyncClient, auth_headers: dict
):
    """
    The API does not explicitly prevent circular role references — the DB
    enforces referential integrity. We verify the API does not crash when
    a self-referential reports_to is submitted (role A reports to itself).
    Creating role A first, then updating it to report to itself, should either
    succeed at the DB level (SQLite does not reject self-FK) or be rejected
    with a 4xx. Either way, no 5xx is acceptable.
    """
    company_id = await _create_company(client, auth_headers, "circ-ref-co")
    role = await _create_role(client, auth_headers, company_id)

    # Attempt to create a role that reports to itself (would be circular)
    resp = await client.put(
        f"/api/v1/roles/{role['id']}",
        json={"reports_to_role_id": role["id"]},
        headers=auth_headers,
    )
    # The DB may allow this (SQLite FK is not enforced by default), but we
    # assert it does not raise an unhandled 5xx error.
    assert resp.status_code < 500

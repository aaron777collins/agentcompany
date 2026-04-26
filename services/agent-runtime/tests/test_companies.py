"""
Tests for the Companies API — /api/v1/companies.

Covers CRUD operations, duplicate-slug detection, auth enforcement,
and the soft-delete workflow.
"""

from __future__ import annotations

import itertools

import pytest
from httpx import AsyncClient

from tests.conftest import DEFAULT_ADMIN_CLAIMS, DEFAULT_MEMBER_CLAIMS, build_authed_client


pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Use a counter so every test gets a unique slug — tests share a SQLite DB so
# slugs from one test must not collide with slugs in a subsequent test.
_slug_counter = itertools.count(1)


def _unique_slug(prefix: str = "co") -> str:
    return f"{prefix}-{next(_slug_counter)}"


def _company_payload(slug: str | None = None) -> dict:
    s = slug or _unique_slug("acme")
    return {
        "name": f"Company {s}",
        "slug": s,
        "description": "A test company",
        "settings": {"timezone": "UTC"},
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_company_returns_201(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/companies/", json=_company_payload(), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["data"]["status"] == "provisioning"
    assert body["data"]["id"].startswith("cmp_")


async def test_create_company_duplicate_slug_returns_409(
    client: AsyncClient, auth_headers: dict
):
    payload = _company_payload()
    await client.post("/api/v1/companies/", json=payload, headers=auth_headers)
    resp = await client.post("/api/v1/companies/", json=payload, headers=auth_headers)
    assert resp.status_code == 409
    assert payload["slug"] in resp.json()["detail"]


async def test_create_company_missing_auth_header_returns_401():
    """
    _get_token_claims raises HTTP 401 when the Authorization header is absent.
    We test this by creating a test app with the auth dependency NOT overridden
    but the DB dependency still overridden so the session factory is reachable.
    """
    from httpx import ASGITransport
    from app.main import create_app
    from app.dependencies import get_db
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    _engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    _factory = async_sessionmaker(bind=_engine, expire_on_commit=False)

    raw_app = create_app()

    async def _fake_db():
        async with _factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    raw_app.dependency_overrides[get_db] = _fake_db

    transport = ASGITransport(app=raw_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as raw_client:
        resp = await raw_client.post("/api/v1/companies/", json=_company_payload())
    assert resp.status_code == 401


async def test_create_company_invalid_slug_returns_422(
    client: AsyncClient, auth_headers: dict
):
    payload = {**_company_payload(), "slug": "has spaces"}
    resp = await client.post("/api/v1/companies/", json=payload, headers=auth_headers)
    assert resp.status_code == 422


async def test_create_company_member_role_forbidden():
    """org:member (not admin) cannot create companies."""
    async with build_authed_client(DEFAULT_MEMBER_CLAIMS) as ac:
        resp = await ac.post(
            "/api/v1/companies/",
            json=_company_payload(),
            headers={"Authorization": "Bearer x"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_companies_returns_items(client: AsyncClient, auth_headers: dict):
    await client.post("/api/v1/companies/", json=_company_payload(), headers=auth_headers)
    resp = await client.get("/api/v1/companies/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1


async def test_list_companies_pagination_defaults(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/companies/?limit=5&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_size"] == 5


async def test_list_companies_limit_out_of_range_returns_400(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/companies/?limit=200", headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


async def test_get_company_returns_200(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/companies/", json=_company_payload(), headers=auth_headers
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/companies/{company_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == company_id


async def test_get_company_not_found_returns_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/companies/cmp_nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_update_company_returns_200(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/companies/", json=_company_payload(), headers=auth_headers
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]
    original_version = create_resp.json()["data"]["version"]

    update_resp = await client.put(
        f"/api/v1/companies/{company_id}",
        json={"name": "Renamed Co"},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()["data"]
    assert data["name"] == "Renamed Co"
    assert data["version"] == original_version + 1


async def test_update_company_partial_settings_merge(
    client: AsyncClient, auth_headers: dict
):
    """Settings update merges fields rather than replacing wholesale."""
    create_resp = await client.post(
        "/api/v1/companies/",
        json={**_company_payload(), "settings": {"timezone": "UTC", "key": "val"}},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/v1/companies/{company_id}",
        json={"settings": {"new_key": "new_val"}},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    settings = update_resp.json()["data"]["settings"]
    # Original key must still be present
    assert settings.get("key") == "val"
    assert settings.get("new_key") == "new_val"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_company_returns_204(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/companies/",
        json=_company_payload(),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/companies/{company_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204


async def test_deleted_company_not_returned_in_get(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post(
        "/api/v1/companies/",
        json=_company_payload(),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]
    await client.delete(f"/api/v1/companies/{company_id}", headers=auth_headers)

    get_resp = await client.get(f"/api/v1/companies/{company_id}", headers=auth_headers)
    assert get_resp.status_code == 404


async def test_deleted_company_is_not_findable_by_get(
    client: AsyncClient, auth_headers: dict
):
    """After soft-delete, GET by ID returns 404 and list does not include it."""
    slug = _unique_slug("softdel")
    create_resp = await client.post(
        "/api/v1/companies/",
        json=_company_payload(slug=slug),
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    company_id = create_resp.json()["data"]["id"]
    await client.delete(f"/api/v1/companies/{company_id}", headers=auth_headers)

    # Deleted company must not appear in GET-by-ID
    get_resp = await client.get(f"/api/v1/companies/{company_id}", headers=auth_headers)
    assert get_resp.status_code == 404

    # Deleted company must not appear in list
    list_resp = await client.get("/api/v1/companies/", headers=auth_headers)
    ids = [c["id"] for c in list_resp.json()["items"]]
    assert company_id not in ids

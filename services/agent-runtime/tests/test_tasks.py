"""
Tests for the Tasks API — /api/v1/tasks.

Covers create, list-by-status, update (with status transitions),
assign, and invalid-status-transition handling.
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
        json={"name": f"Task Co {slug}", "slug": slug},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _task_payload(company_id: str, title: str = "Fix the bug") -> dict:
    return {
        "title": title,
        "description": "Reproduce and fix the regression",
        "company_id": company_id,
        "priority": "high",
        "tags": ["regression"],
    }


async def _create_task(
    client: AsyncClient, headers: dict, company_id: str, title: str = "Fix the bug"
) -> dict:
    resp = await client.post(
        "/api/v1/tasks/",
        json=_task_payload(company_id, title),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_task_returns_201(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "task-create-co")
    resp = await client.post(
        "/api/v1/tasks/", json=_task_payload(company_id), headers=auth_headers
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["id"].startswith("tsk_")
    assert data["status"] == "backlog"
    assert data["priority"] == "high"


async def test_create_task_default_status_is_backlog(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-default-co")
    task = await _create_task(client, auth_headers, company_id)
    assert task["status"] == "backlog"


async def test_create_task_missing_title_returns_422(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-422-co")
    resp = await client.post(
        "/api/v1/tasks/",
        json={"company_id": company_id},  # missing title
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_create_task_invalid_priority_returns_422(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-pri-co")
    payload = _task_payload(company_id)
    payload["priority"] = "critical"  # not a valid priority
    resp = await client.post("/api/v1/tasks/", json=payload, headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_tasks_returns_items(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "task-list-co")
    await _create_task(client, auth_headers, company_id, title="Task A")
    await _create_task(client, auth_headers, company_id, title="Task B")

    resp = await client.get("/api/v1/tasks/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


async def test_list_tasks_by_status(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "task-status-co")
    task = await _create_task(client, auth_headers, company_id)

    # Update task to in_progress
    await client.put(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/tasks/?status=in_progress", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(t["status"] == "in_progress" for t in items)


async def test_list_tasks_filter_by_company(client: AsyncClient, auth_headers: dict):
    co1 = await _create_company(client, auth_headers, "task-flt-co1")
    co2 = await _create_company(client, auth_headers, "task-flt-co2")
    await _create_task(client, auth_headers, co1, title="Co1 Task")
    await _create_task(client, auth_headers, co2, title="Co2 Task")

    resp = await client.get(f"/api/v1/tasks/?company_id={co1}", headers=auth_headers)
    items = resp.json()["items"]
    assert all(t["company_id"] == co1 for t in items)


# ---------------------------------------------------------------------------
# Update and status transitions
# ---------------------------------------------------------------------------


async def test_update_task_status_backlog_to_in_progress(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-trans-co")
    task = await _create_task(client, auth_headers, company_id)
    assert task["status"] == "backlog"

    resp = await client.put(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "in_progress"
    # started_at should be stamped when transitioning to in_progress
    assert data["started_at"] is not None


async def test_update_task_status_to_done_stamps_completed_at(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-done-co")
    task = await _create_task(client, auth_headers, company_id)

    resp = await client.put(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["completed_at"] is not None


async def test_update_task_status_to_cancelled_stamps_completed_at(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-cancel-co")
    task = await _create_task(client, auth_headers, company_id)

    resp = await client.put(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["completed_at"] is not None


async def test_invalid_status_value_returns_422(client: AsyncClient, auth_headers: dict):
    """The status field only accepts the enum values from TaskUpdate."""
    company_id = await _create_company(client, auth_headers, "task-inv-status-co")
    task = await _create_task(client, auth_headers, company_id)

    resp = await client.put(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "open"},  # removed status value
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_update_task_metadata_merges(client: AsyncClient, auth_headers: dict):
    """Metadata updates merge with existing metadata, not replace."""
    company_id = await _create_company(client, auth_headers, "task-meta-co")
    resp = await client.post(
        "/api/v1/tasks/",
        json={**_task_payload(company_id), "metadata": {"key1": "val1"}},
        headers=auth_headers,
    )
    task_id = resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/v1/tasks/{task_id}",
        json={"metadata": {"key2": "val2"}},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    # Both key1 (original) and key2 (new) must be present
    assert update_resp.json()["data"]["metadata_"].get("key1") == "val1"
    assert update_resp.json()["data"]["metadata_"].get("key2") == "val2"


# ---------------------------------------------------------------------------
# Assign
# ---------------------------------------------------------------------------


async def test_assign_task_to_agent(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "task-assign-co")
    task = await _create_task(client, auth_headers, company_id)
    agent_id = "agt_fake-agent-001"

    resp = await client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": agent_id, "assignee_type": "agent"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["assigned_to"] == agent_id
    assert data["assigned_type"] == "agent"


async def test_assign_task_to_human(client: AsyncClient, auth_headers: dict):
    company_id = await _create_company(client, auth_headers, "task-human-co")
    task = await _create_task(client, auth_headers, company_id)

    resp = await client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": "user-abc", "assignee_type": "human"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["assigned_type"] == "human"


async def test_assign_task_invalid_type_returns_422(
    client: AsyncClient, auth_headers: dict
):
    company_id = await _create_company(client, auth_headers, "task-inv-assign-co")
    task = await _create_task(client, auth_headers, company_id)

    resp = await client.post(
        f"/api/v1/tasks/{task['id']}/assign",
        json={"assignee_id": "xxx", "assignee_type": "robot"},
        headers=auth_headers,
    )
    assert resp.status_code == 422

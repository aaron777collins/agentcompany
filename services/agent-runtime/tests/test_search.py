"""
Tests for the Search API — /api/v1/search.

Key security focus: verifying that the filter injection fix (C-2) is in place.
The search endpoint must reject filter keys not on the whitelist and filter
values containing Meilisearch operators.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _search_payload(company_id: str = "cmp_test", **overrides) -> dict:
    base = {
        "q": "bug fix",
        "company_id": company_id,
        "scope": "tasks",
        "filters": {},
        "limit": 10,
        "offset": 0,
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Valid query (Meilisearch mocked to return empty results)
# ---------------------------------------------------------------------------


async def test_search_valid_query_returns_200(client: AsyncClient, auth_headers: dict):
    with patch("app.api.search.httpx.AsyncClient") as mock_httpx_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": [], "estimatedTotalHits": 0}
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value = mock_client_instance

        resp = await client.post(
            "/api/v1/search/", json=_search_payload(), headers=auth_headers
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "hits" in body["data"]


async def test_search_valid_filter_keys_accepted(client: AsyncClient, auth_headers: dict):
    with patch("app.api.search.httpx.AsyncClient") as mock_httpx_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": [], "estimatedTotalHits": 0}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value = mock_client

        resp = await client.post(
            "/api/v1/search/",
            json=_search_payload(filters={"status": "open", "priority": "high"}),
            headers=auth_headers,
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# C-2 fix: filter injection blocked
# ---------------------------------------------------------------------------


async def test_search_filter_injection_blocked_disallowed_key(
    client: AsyncClient, auth_headers: dict
):
    """Filter keys not on the whitelist must be rejected with 400."""
    resp = await client.post(
        "/api/v1/search/",
        json=_search_payload(filters={"org_id": "other-org"}),  # not in whitelist
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"].lower()


async def test_search_filter_injection_blocked_or_operator(
    client: AsyncClient, auth_headers: dict
):
    """Filter values containing Meilisearch OR operator must be rejected."""
    resp = await client.post(
        "/api/v1/search/",
        json=_search_payload(filters={"status": "open OR status = closed"}),
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_search_filter_injection_blocked_and_operator(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/search/",
        json=_search_payload(filters={"status": 'open AND org_id = "other"'}),
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_search_filter_injection_blocked_parentheses(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/search/",
        json=_search_payload(filters={"status": "(open)"}),
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_search_filter_injection_blocked_comparison_operators(
    client: AsyncClient, auth_headers: dict
):
    for op in ["=", "!=", ">", "<"]:
        resp = await client.post(
            "/api/v1/search/",
            json=_search_payload(filters={"status": f"open{op}closed"}),
            headers=auth_headers,
        )
        assert resp.status_code == 400, f"Expected 400 for operator '{op}'"


async def test_search_filter_injection_blocked_not_keyword(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/search/",
        json=_search_payload(filters={"status": "NOT cancelled"}),
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# company_id required
# ---------------------------------------------------------------------------


async def test_search_requires_company_id(client: AsyncClient, auth_headers: dict):
    """Omitting company_id from the request body must return 422."""
    resp = await client.post(
        "/api/v1/search/",
        json={"q": "test", "scope": "tasks"},  # missing company_id
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_search_requires_nonempty_query(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/search/",
        json={"q": "", "company_id": "cmp_test"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Scope filtering
# ---------------------------------------------------------------------------


async def test_search_unknown_scope_falls_back_to_tasks(
    client: AsyncClient, auth_headers: dict
):
    with patch("app.api.search.httpx.AsyncClient") as mock_httpx_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": [], "estimatedTotalHits": 0}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_httpx_cls.return_value = mock_client

        resp = await client.post(
            "/api/v1/search/",
            json=_search_payload(scope="unknown_scope"),
            headers=auth_headers,
        )
    assert resp.status_code == 200

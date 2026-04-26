"""
Unit tests for the tool adapter layer.

All external HTTP calls are intercepted using httpx.MockTransport /
respx or unittest.mock so no real Plane/Outline/Mattermost/Meilisearch
server is needed.

Tests cover:
- AdapterRegistry.register / get / health_check_all
- PlaneAdapter.create_issue
- OutlineAdapter.search_documents
- MattermostAdapter.send_message
- MeilisearchAdapter.search
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.mattermost import MattermostAdapter
from app.adapters.meilisearch_adapter import MeilisearchAdapter
from app.adapters.outline import OutlineAdapter
from app.adapters.plane import PlaneAdapter
from app.adapters.registry import AdapterRegistry
from app.adapters.types import AdapterError, AdapterErrorCode, HealthStatus


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — build pre-initialized adapters without real HTTP
# ---------------------------------------------------------------------------


def _make_mock_transport(status_code: int = 200, json_body: dict | None = None) -> httpx.MockTransport:
    """Return an httpx.MockTransport that responds with a fixed response."""
    import json

    body = json.dumps(json_body or {}).encode()

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=body, headers={"content-type": "application/json"})

    return httpx.MockTransport(_handler)


async def _init_plane_adapter(workspace: str = "acme", json_response: dict | None = None) -> PlaneAdapter:
    """Build a PlaneAdapter with mocked health check response."""
    adapter = PlaneAdapter()
    config = {
        "config": {
            "base_url": "http://plane.example.com",
            "workspace_slug": workspace,
            "project_id": "proj-001",
        },
        "secrets": {
            "api_key": "test-key",
            "webhook_secret": "wh-secret",
        },
    }
    mock_response = json_response or {"id": workspace, "slug": workspace}
    transport = _make_mock_transport(200, mock_response)
    client = httpx.AsyncClient(transport=transport, base_url="http://plane.example.com")
    adapter._set_config(config)
    adapter._http_client = client
    return adapter


async def _init_outline_adapter() -> OutlineAdapter:
    adapter = OutlineAdapter()
    config = {
        "config": {"base_url": "http://outline.example.com"},
        "secrets": {"api_key": "outline-key", "webhook_secret": "wh-secret"},
    }
    transport = _make_mock_transport(200, {"data": {"user": {"name": "bot"}}})
    client = httpx.AsyncClient(transport=transport, base_url="http://outline.example.com")
    adapter._set_config(config)
    adapter._http_client = client
    return adapter


async def _init_mattermost_adapter() -> MattermostAdapter:
    adapter = MattermostAdapter()
    config = {
        "config": {"base_url": "http://mm.example.com", "team_id": "team-001"},
        "secrets": {"bot_token": "bot-key", "webhook_token": "wh-token"},
    }
    transport = _make_mock_transport(200, {"status": "OK", "Version": "7.0"})
    client = httpx.AsyncClient(transport=transport, base_url="http://mm.example.com")
    adapter._set_config(config)
    adapter._http_client = client
    return adapter


async def _init_meilisearch_adapter() -> MeilisearchAdapter:
    adapter = MeilisearchAdapter()
    config = {
        "config": {"base_url": "http://meili.example.com"},
        "secrets": {"master_key": "meili-key", "search_key": "srch-key"},
    }
    transport = _make_mock_transport(200, {"status": "available"})
    client = httpx.AsyncClient(transport=transport, base_url="http://meili.example.com")
    adapter._set_config(config)
    adapter._http_client = client
    return adapter


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    async def test_register_returns_adapter(self):
        registry = AdapterRegistry()

        # Mock the adapter initialization so no real HTTP is needed
        mock_adapter = AsyncMock()
        mock_adapter.initialize = AsyncMock()
        mock_adapter.health_check = AsyncMock(
            return_value=HealthStatus(healthy=True, latency_ms=5.0)
        )
        mock_adapter.shutdown = AsyncMock()

        with patch.dict("app.adapters.registry._ADAPTER_CLASS_MAP", {"mock": lambda: mock_adapter}):
            result = await registry.register(
                company_id="acme",
                tool="mock",
                config={"config": {}, "secrets": {}},
            )

        assert result is mock_adapter

    async def test_get_unregistered_adapter_raises_adapter_error(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterError) as exc_info:
            registry.get("unknown-company", "plane")
        assert exc_info.value.code == AdapterErrorCode.CONNECTION_REFUSED

    async def test_register_unknown_tool_raises_value_error(self):
        registry = AdapterRegistry()
        with pytest.raises(ValueError, match="Unknown adapter type"):
            await registry.register("acme", "nonexistent_tool", {})

    async def test_empty_company_id_raises_value_error(self):
        registry = AdapterRegistry()
        with pytest.raises(ValueError, match="company_id"):
            await registry.register("", "plane", {})

    async def test_is_registered_returns_false_when_not_registered(self):
        registry = AdapterRegistry()
        assert registry.is_registered("company", "plane") is False

    async def test_deregister_removes_adapter(self):
        registry = AdapterRegistry()
        mock_adapter = AsyncMock()
        mock_adapter.initialize = AsyncMock()
        mock_adapter.shutdown = AsyncMock()

        with patch.dict("app.adapters.registry._ADAPTER_CLASS_MAP", {"mock": lambda: mock_adapter}):
            await registry.register("acme", "mock", {"config": {}, "secrets": {}})
            assert registry.is_registered("acme", "mock")
            await registry.deregister("acme", "mock")
            assert not registry.is_registered("acme", "mock")

    async def test_health_check_all_returns_per_adapter_results(self):
        registry = AdapterRegistry()
        healthy_adapter = AsyncMock()
        healthy_adapter.name = "healthy"
        healthy_adapter.health_check = AsyncMock(
            return_value=HealthStatus(healthy=True, latency_ms=3.0)
        )

        # Inject an adapter directly to avoid full initialization
        registry._adapters[("acme", "healthy")] = healthy_adapter

        results = await registry.health_check_all()
        assert "acme/healthy" in results
        assert results["acme/healthy"].healthy is True

    async def test_health_check_all_captures_exceptions(self):
        registry = AdapterRegistry()
        broken_adapter = AsyncMock()
        broken_adapter.name = "broken"
        broken_adapter.health_check = AsyncMock(side_effect=RuntimeError("boom"))

        registry._adapters[("acme", "broken")] = broken_adapter

        # Must not raise — failures are captured in HealthStatus
        results = await registry.health_check_all()
        assert "acme/broken" in results
        assert results["acme/broken"].healthy is False


# ---------------------------------------------------------------------------
# PlaneAdapter
# ---------------------------------------------------------------------------


class TestPlaneAdapterCreateIssue:
    async def test_create_issue_posts_to_correct_url(self):
        calls = []

        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                201,
                json={"id": "issue-001", "name": "Fix the bug"},
                headers={"content-type": "application/json"},
            )

        adapter = PlaneAdapter()
        config = {
            "config": {
                "base_url": "http://plane.example.com",
                "workspace_slug": "acme",
                "project_id": "proj-001",
            },
            "secrets": {"api_key": "key", "webhook_secret": "secret"},
        }
        adapter._set_config(config)
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://plane.example.com",
        )

        result = await adapter.create_issue(
            project_id="proj-001",
            title="Fix the bug",
            priority="high",
        )
        assert result["id"] == "issue-001"
        assert any("/issues/" in str(c.url) for c in calls)

    async def test_create_issue_empty_title_raises_adapter_error(self):
        adapter = await _init_plane_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.create_issue(project_id="proj-001", title="   ")
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR

    async def test_plane_adapter_http_401_raises_auth_error(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"}, headers={"content-type": "application/json"})

        adapter = await _init_plane_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://plane.example.com",
        )

        with pytest.raises(AdapterError) as exc_info:
            await adapter.list_issues(project_id="proj-001")
        assert exc_info.value.code == AdapterErrorCode.AUTH_FAILED

    async def test_plane_adapter_http_429_is_retryable(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                json={"detail": "rate limited"},
                headers={"content-type": "application/json", "Retry-After": "30"},
            )

        adapter = await _init_plane_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://plane.example.com",
        )

        with pytest.raises(AdapterError) as exc_info:
            await adapter.list_issues(project_id="proj-001")
        assert exc_info.value.retryable is True
        assert exc_info.value.retry_after_seconds == 30


# ---------------------------------------------------------------------------
# OutlineAdapter
# ---------------------------------------------------------------------------


class TestOutlineAdapterSearch:
    async def test_search_documents_posts_to_correct_endpoint(self):
        calls = []

        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                200,
                json={"data": [{"document": {"id": "doc-001"}, "ranking": 0.9}]},
                headers={"content-type": "application/json"},
            )

        adapter = await _init_outline_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://outline.example.com",
        )

        results = await adapter.search_documents("deployment guide", limit=5)
        assert len(results) == 1
        assert results[0]["document"]["id"] == "doc-001"
        assert any("documents.search" in str(c.url) for c in calls)

    async def test_search_empty_query_raises_adapter_error(self):
        adapter = await _init_outline_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search_documents("   ")
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR

    async def test_outline_capabilities_declared(self):
        adapter = OutlineAdapter()
        assert "document:search" in adapter.capabilities
        assert "document:create" in adapter.capabilities
        assert "webhook:receive" in adapter.capabilities


# ---------------------------------------------------------------------------
# MattermostAdapter
# ---------------------------------------------------------------------------


class TestMattermostAdapterSendMessage:
    async def test_send_message_posts_to_posts_endpoint(self):
        calls = []

        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                201,
                json={"id": "post-001", "message": "Hello!"},
                headers={"content-type": "application/json"},
            )

        adapter = await _init_mattermost_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://mm.example.com",
        )

        result = await adapter.send_message(channel_id="chan-001", message="Hello!")
        assert result["id"] == "post-001"
        assert any("/posts" in str(c.url) for c in calls)

    async def test_send_empty_message_raises_adapter_error(self):
        adapter = await _init_mattermost_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.send_message(channel_id="chan-001", message="  ")
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR

    async def test_mattermost_verify_webhook_signature_valid_token(self):
        import json as json_mod

        adapter = MattermostAdapter()
        body = json_mod.dumps({"token": "secret123"}).encode()
        assert adapter.verify_webhook_signature(body, {}, "secret123") is True

    async def test_mattermost_verify_webhook_signature_wrong_token(self):
        import json as json_mod

        adapter = MattermostAdapter()
        body = json_mod.dumps({"token": "wrong"}).encode()
        assert adapter.verify_webhook_signature(body, {}, "secret123") is False

    async def test_mattermost_verify_webhook_invalid_json(self):
        adapter = MattermostAdapter()
        assert adapter.verify_webhook_signature(b"not-json", {}, "secret") is False


# ---------------------------------------------------------------------------
# MeilisearchAdapter
# ---------------------------------------------------------------------------


class TestMeilisearchAdapterSearch:
    async def test_search_single_index(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            if "/indexes/" in str(request.url) and "/search" in str(request.url):
                return httpx.Response(
                    200,
                    json={"hits": [{"id": "task-001", "title": "Deploy"}], "estimatedTotalHits": 1},
                    headers={"content-type": "application/json"},
                )
            return httpx.Response(200, json={}, headers={"content-type": "application/json"})

        adapter = await _init_meilisearch_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://meili.example.com",
        )

        result = await adapter.search(
            index="tasks", query="deploy", company_id="cmp-001"
        )
        assert "hits" in result
        assert len(result["hits"]) == 1

    async def test_search_builds_company_id_filter(self):
        built_filter = None

        def _handler(request: httpx.Request) -> httpx.Response:
            import json as json_mod

            if "/search" in str(request.url):
                body = json_mod.loads(request.content)
                nonlocal built_filter
                built_filter = body.get("filter")
            return httpx.Response(
                200,
                json={"hits": [], "estimatedTotalHits": 0},
                headers={"content-type": "application/json"},
            )

        adapter = await _init_meilisearch_adapter()
        adapter._http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            base_url="http://meili.example.com",
        )

        await adapter.search(index="tasks", query="test", company_id="cmp-abc")
        assert built_filter is not None
        assert 'company_id = "cmp-abc"' in built_filter

    async def test_search_all_requires_company_id(self):
        adapter = await _init_meilisearch_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search_all(query="test", company_id="")
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR

    async def test_index_document_missing_company_id_raises(self):
        adapter = await _init_meilisearch_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.index_document(
                index="tasks",
                document={"id": "task-001"},  # missing company_id
            )
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR
        assert "company_id" in exc_info.value.message

    async def test_index_document_missing_id_raises(self):
        adapter = await _init_meilisearch_adapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.index_document(
                index="tasks",
                document={"company_id": "cmp-001"},  # missing id
            )
        assert exc_info.value.code == AdapterErrorCode.VALIDATION_ERROR

    async def test_build_filter_with_extra_filter(self):
        """Tenant isolation filter is always ANDed with any extra filter."""
        result = MeilisearchAdapter._build_filter("cmp-123", "status = 'open'")
        assert 'company_id = "cmp-123"' in result
        assert "(status = 'open')" in result
        assert " AND " in result

    async def test_build_filter_no_extra_filter(self):
        result = MeilisearchAdapter._build_filter("cmp-456", None)
        assert result == 'company_id = "cmp-456"'

    async def test_build_filter_no_company_id(self):
        result = MeilisearchAdapter._build_filter(None, "status = 'open'")
        assert result == "(status = 'open')"

    async def test_meilisearch_does_not_support_webhooks(self):
        from app.adapters.types import AdapterErrorCode

        adapter = MeilisearchAdapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.handle_webhook({}, {})
        assert exc_info.value.code == AdapterErrorCode.CAPABILITY_NOT_SUPPORTED

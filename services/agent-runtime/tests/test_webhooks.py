"""
Tests for the Webhooks API — /api/v1/webhooks.

Key security focus (C-3 fix): endpoints must return 503 when the respective
webhook secret is not configured, preventing arbitrary event injection.

Auth model: webhooks do NOT use JWT. They use HMAC signatures (Plane/Outline)
or a shared body token (Mattermost). The test app is not configured with
auth overrides for these routes — they bypass JWT entirely.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from tests.conftest import build_test_app, make_outline_signature, make_plane_signature

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test-specific app with webhook secrets configured on settings
# ---------------------------------------------------------------------------

PLANE_SECRET = "test-plane-secret"
OUTLINE_SECRET = "test-outline-secret"
MM_SECRET = "test-mm-secret"


def _sign_plane(body: bytes) -> str:
    return make_plane_signature(body, PLANE_SECRET)


def _sign_outline(body: bytes) -> str:
    return make_outline_signature(body, OUTLINE_SECRET)


# ---------------------------------------------------------------------------
# Plane webhooks
# ---------------------------------------------------------------------------


async def test_plane_webhook_valid_returns_200(auth_headers: dict):
    """A correctly signed Plane webhook returns 200 {received: true}."""
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "issue.created", "data": {"id": "issue-001"}}).encode()
    sig = _sign_plane(payload)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/plane",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Plane-Signature": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


async def test_plane_webhook_invalid_signature_returns_401(auth_headers: dict):
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "issue.created"}).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/plane",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Plane-Signature": "badhash",
            },
        )
    assert resp.status_code == 401


async def test_plane_webhook_missing_signature_returns_401():
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "issue.updated"}).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/plane",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401


async def test_plane_webhook_no_secret_configured_returns_503():
    """
    C-3 fix: when webhook_secret_plane is empty, the endpoint must refuse
    all requests with 503 rather than silently accepting them.
    """
    from app.config import Settings
    import app.config as _config_module
    from unittest.mock import patch

    _config_module.get_settings.cache_clear()

    # Build an app but patch settings to have an empty plane secret
    app = build_test_app()
    # Override settings on the running app
    empty_secret_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        secret_key="a" * 32,
        webhook_secret_plane="",  # empty — not configured
        webhook_secret_mattermost="",
        webhook_secret_outline="",
    )

    from httpx import ASGITransport

    payload = json.dumps({"event": "issue.created"}).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        with patch("app.api.webhooks.get_settings", return_value=empty_secret_settings):
            resp = await ac.post(
                "/api/v1/webhooks/plane",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 503, (
        "Plane webhook endpoint must return 503 when secret is not configured (C-3 fix)"
    )


# ---------------------------------------------------------------------------
# Mattermost webhooks
# ---------------------------------------------------------------------------


async def test_mattermost_webhook_valid_returns_200():
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({
        "token": MM_SECRET,
        "channel_id": "chan-001",
        "user_id": "user-001",
        "text": "Hello agent",
        "event": "message.posted",
    }).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/mattermost",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


async def test_mattermost_webhook_wrong_token_returns_401():
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({
        "token": "wrong-token",
        "channel_id": "chan-001",
        "user_id": "user-001",
    }).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/mattermost",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401


async def test_mattermost_webhook_no_secret_returns_503():
    """C-3 fix: missing Mattermost secret returns 503."""
    from unittest.mock import patch
    from app.config import Settings

    empty_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        secret_key="a" * 32,
        webhook_secret_plane="",
        webhook_secret_mattermost="",
        webhook_secret_outline="",
    )
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"token": "anything"}).encode()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        with patch("app.api.webhooks.get_settings", return_value=empty_settings):
            resp = await ac.post(
                "/api/v1/webhooks/mattermost",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Outline webhooks
# ---------------------------------------------------------------------------


async def test_outline_webhook_valid_returns_200():
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({
        "event": "documents.update",
        "payload": {"model": {"id": "doc-001"}},
        "actorId": "user-001",
    }).encode()
    sig = _sign_outline(payload)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/outline",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Outline-Signature": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["received"] is True


async def test_outline_webhook_invalid_signature_returns_401():
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "documents.update"}).encode()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/outline",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Outline-Signature": "sha256=badhash",
            },
        )
    assert resp.status_code == 401


async def test_outline_webhook_no_secret_returns_503():
    """C-3 fix: missing Outline secret returns 503."""
    from unittest.mock import patch
    from app.config import Settings

    empty_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        secret_key="a" * 32,
        webhook_secret_plane="",
        webhook_secret_mattermost="",
        webhook_secret_outline="",
    )
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "documents.create"}).encode()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        with patch("app.api.webhooks.get_settings", return_value=empty_settings):
            resp = await ac.post(
                "/api/v1/webhooks/outline",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# HMAC signature with sha256= prefix accepted
# ---------------------------------------------------------------------------


async def test_plane_webhook_sha256_prefix_stripped():
    """Plane may include a sha256= prefix on the signature header."""
    app = build_test_app()
    from httpx import ASGITransport

    payload = json.dumps({"event": "cycle.created"}).encode()
    raw_hash = hmac.new(PLANE_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    sig_with_prefix = f"sha256={raw_hash}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/api/v1/webhooks/plane",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Plane-Signature": sig_with_prefix,
            },
        )
    assert resp.status_code == 200

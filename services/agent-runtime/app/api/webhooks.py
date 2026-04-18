"""Webhook receivers — /api/v1/webhooks.

These endpoints receive inbound webhooks from external tools (Plane, Outline,
Mattermost).  They do NOT use JWT auth — instead each uses the tool's native
authentication mechanism:
  - Plane:        HMAC-SHA256 signature on request body (X-Plane-Signature)
  - Outline:      HMAC-SHA256 signature (X-Outline-Signature)
  - Mattermost:   Shared token in request body

Raw payloads are validated, then persisted as Events and published to the
Redis event bus so the agent runtime can react asynchronously.
"""

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/plane", summary="Receive Plane webhooks")
async def plane_webhook(
    request: Request,
    x_plane_signature: str | None = Header(default=None),
) -> dict:
    """Accept Plane issue/project events.

    Plane sends a SHA-256 HMAC signature in X-Plane-Signature.  We verify it
    before doing anything with the payload.
    """
    body = await request.body()
    settings = get_settings()

    # Refuse requests entirely when the secret is not configured — silently
    # accepting unverified payloads would allow arbitrary event injection.
    if not settings.webhook_secret_plane:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plane webhook secret is not configured on this server",
        )

    _verify_hmac(
        secret=settings.webhook_secret_plane,
        body=body,
        signature=x_plane_signature,
        header_name="X-Plane-Signature",
    )

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    event_type = payload.get("event", "unknown")
    logger.info("Plane webhook received: event=%s", event_type)

    # Fan out to the event bus so agents can react.  The actual persistence
    # and dispatch is handled by the engine layer (written by another agent).
    await _emit_webhook_event(request, source="plane", event_type=event_type, payload=payload)

    return {"received": True}


@router.post("/outline", summary="Receive Outline webhooks")
async def outline_webhook(
    request: Request,
    x_outline_signature: str | None = Header(default=None),
) -> dict:
    """Accept Outline document/collection events."""
    body = await request.body()
    settings = get_settings()

    # Refuse requests entirely when the secret is not configured — same
    # reasoning as the Plane handler above.
    if not settings.webhook_secret_outline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Outline webhook secret is not configured on this server",
        )

    _verify_hmac(
        secret=settings.webhook_secret_outline,
        body=body,
        signature=x_outline_signature,
        header_name="X-Outline-Signature",
    )

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    event_type = payload.get("event", "unknown")
    logger.info("Outline webhook received: event=%s", event_type)

    await _emit_webhook_event(
        request, source="outline", event_type=event_type, payload=payload
    )
    return {"received": True}


@router.post("/mattermost", summary="Receive Mattermost webhooks")
async def mattermost_webhook(
    request: Request,
) -> dict:
    """Accept Mattermost outgoing webhook events.

    Mattermost uses a shared token in the request body (not HMAC), so we
    extract and compare it against our configured secret.
    """
    settings = get_settings()

    # Refuse requests entirely when the secret is not configured — same
    # reasoning as the Plane handler above.
    if not settings.webhook_secret_mattermost:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mattermost webhook secret is not configured on this server",
        )

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    # Mattermost puts the token in the body for outgoing webhooks
    token = payload.get("token", "")
    if not hmac.compare_digest(
        token.encode(), settings.webhook_secret_mattermost.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Mattermost webhook token",
        )

    event_type = payload.get("event", "message.posted")
    logger.info("Mattermost webhook received: event=%s", event_type)

    await _emit_webhook_event(
        request, source="mattermost", event_type=event_type, payload=payload
    )
    return {"received": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_hmac(
    secret: str,
    body: bytes,
    signature: str | None,
    header_name: str,
) -> None:
    """Validate an HMAC-SHA256 signature against the raw request body.

    Raises 401 if the signature is absent or does not match.
    """
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {header_name} header",
        )

    expected = hmac.new(
        key=secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Strip any "sha256=" prefix some tools add
    received = signature.removeprefix("sha256=")

    if not hmac.compare_digest(expected, received):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid {header_name} signature",
        )


async def _emit_webhook_event(
    request: Request,
    source: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Publish the webhook payload to the event bus if available."""
    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus is None:
        return

    company_id: str = payload.get("company_id", "")
    if not company_id:
        # Try to resolve company_id from workspace or channel context
        company_id = payload.get("workspace_id", payload.get("channel_id", ""))

    await event_bus.publish(
        company_id or "system",
        {
            "type": f"webhook.{source}.{event_type}",
            "source": source,
            "payload": payload,
        },
    )

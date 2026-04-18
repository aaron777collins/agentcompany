"""Events API — /api/v1/events.

Exposes the immutable event log and a Server-Sent Events stream for real-time
updates.  SSE is used instead of WebSocket for simplicity — SSE is
unidirectional (server → client) which matches the push model perfectly.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, status
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.dependencies import Bus, DBSession, OrgMember
from app.models.event import Event
from app.schemas.common import make_list_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="List events (audit log)")
async def list_events(
    db: DBSession,
    claims: OrgMember,
    company_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="type"),
    actor_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Cursor-paginated event log.  Events are sorted newest-first."""
    query = select(Event).where(Event.org_id == claims.org_id)

    if company_id:
        query = query.where(Event.company_id == company_id)
    if event_type:
        query = query.where(Event.type == event_type)
    if actor_id:
        query = query.where(Event.actor_id == actor_id)
    if resource_type:
        query = query.where(Event.resource_type == resource_type)
    if resource_id:
        query = query.where(Event.resource_id == resource_id)

    # Cursor is the ID of the last event seen; we return events after it
    if cursor:
        anchor = await db.scalar(select(Event).where(Event.id == cursor))
        if anchor:
            query = query.where(Event.timestamp < anchor.timestamp)

    rows = await db.scalars(
        query.order_by(Event.timestamp.desc()).limit(limit + 1)
    )
    events = list(rows)

    has_more = len(events) > limit
    events = events[:limit]

    next_cursor = events[-1].id if (has_more and events) else None

    return {
        "data": [_serialize_event(e) for e in events],
        "meta": {
            "next_cursor": next_cursor,
            "has_more": has_more,
        },
    }


@router.get(
    "/stream",
    summary="SSE stream for real-time events",
    response_class=EventSourceResponse,
)
async def stream_events(
    claims: OrgMember,
    bus: Bus,
    company_id: str | None = Query(default=None),
    types: str | None = Query(
        default=None, description="Comma-separated event type prefixes, e.g. task.*,agent.*"
    ),
) -> EventSourceResponse:
    """Server-Sent Events endpoint.  The client keeps the connection open and
    receives events as they are published to the Redis event bus.

    Filtering by type prefix (e.g. 'task.*') is applied server-side so we
    don't push events the client doesn't want.
    """
    type_filters: list[str] = []
    if types:
        type_filters = [t.strip().rstrip("*") for t in types.split(",") if t.strip()]

    target_company = company_id or ""

    async def generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in bus.subscribe(target_company or claims.org_id):
                if event.get("type") == "keepalive":
                    yield {"event": "keepalive", "data": ""}
                    continue

                # Apply type prefix filter if specified
                if type_filters:
                    event_type = event.get("type", "")
                    if not any(event_type.startswith(f) for f in type_filters):
                        continue

                # Tenant isolation: only forward events for the requested company
                if target_company and event.get("company_id") != target_company:
                    continue

                yield {"event": event.get("type", "event"), "data": json.dumps(event)}
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(generator())


# ── Internal helper ───────────────────────────────────────────────────────────

def _serialize_event(event: Event) -> dict:
    return {
        "id": event.id,
        "type": event.type,
        "org_id": event.org_id,
        "company_id": event.company_id,
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "payload": event.payload,
        "source": event.source,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    }

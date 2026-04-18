"""Shared schemas used across all API endpoints.

These types implement the standard response envelope defined in api-design.md:
    { "data": ..., "meta": { "request_id": ..., "timestamp": ..., ... } }

Every list endpoint returns ListResponse[T]; every single-resource endpoint
returns DataResponse[T]; errors are serialised as ErrorResponse.
"""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_request_id() -> str:
    return f"req_{str(uuid4()).replace('-', '')[:26]}"


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None = None


class CursorMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool


class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=_new_request_id)
    timestamp: str = Field(default_factory=_now_iso)
    version: str = "1.0.0"


class ListMeta(ResponseMeta):
    pagination: PaginationMeta


class DataResponse(BaseModel, Generic[T]):
    """Single-resource response envelope."""

    data: T
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ListResponse(BaseModel, Generic[T]):
    """Paginated list response envelope.

    Shape matches what the frontend expects:
        { items, total, page, page_size, has_next }
    Page is 1-based to align with typical UI pagination controls.
    """

    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool


class CursorResponse(BaseModel, Generic[T]):
    """Cursor-paginated list response (used for events)."""

    data: list[T]
    meta: CursorMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=_new_request_id)
    timestamp: str = Field(default_factory=_now_iso)


class ErrorResponse(BaseModel):
    error: ErrorDetail


def make_list_response(
    items: list[Any],
    total: int,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Build a ListResponse-compatible dict for use in route handlers.

    Returns the flat shape the frontend expects:
        { items, total, page, page_size, has_next }

    Page is derived from offset/limit and is 1-based.
    """
    page = (offset // limit) + 1 if limit > 0 else 1
    has_next = (offset + limit) < total
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": limit,
        "has_next": has_next,
    }

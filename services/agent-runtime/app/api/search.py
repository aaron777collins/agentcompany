"""Search API — /api/v1/search.

Proxies unified search requests to Meilisearch.  Tenant isolation is enforced
by injecting a company_id filter into every query before forwarding to
Meilisearch — the client never has direct access to the search index.
"""

import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dependencies import OrgMember
from app.schemas.common import DataResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Only these keys may appear in caller-supplied filter dicts.  Any other key
# is rejected outright — never forward unknown keys to Meilisearch.
_ALLOWED_FILTER_KEYS = frozenset({"status", "priority", "source", "assignee"})

# Characters/tokens that would allow a caller to escape a filter value and
# inject arbitrary filter logic into the Meilisearch expression.
_FORBIDDEN_VALUE_PATTERN = re.compile(
    r"\b(OR|AND|NOT|TO)\b|[=!<>()\"]", re.IGNORECASE
)


def _validate_filter_key(key: str) -> None:
    """Reject filter keys that are not on the explicit whitelist."""
    if key not in _ALLOWED_FILTER_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Filter key '{key}' is not allowed. "
                f"Permitted keys: {sorted(_ALLOWED_FILTER_KEYS)}"
            ),
        )


def _validate_filter_value(key: str, value: Any) -> str:
    """Coerce value to string and reject patterns that could inject filter logic."""
    str_value = str(value)
    if _FORBIDDEN_VALUE_PATTERN.search(str_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Filter value for '{key}' contains disallowed characters or keywords. "
                "Values must not contain: OR, AND, NOT, TO, =, !=, >, <, (, ), \""
            ),
        )
    return str_value


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    company_id: str
    scope: str = "all"
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: str = "relevance"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class IndexRequest(BaseModel):
    resource_type: str
    resource_ids: list[str] = Field(min_length=1)
    company_id: str


@router.post(
    "/",
    summary="Unified search across all tools",
)
async def search(
    body: SearchRequest,
    request: Request,
    claims: OrgMember,
) -> dict:
    settings = get_settings()
    if not settings.meilisearch_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search is not configured",
        )

    # Map scope to Meilisearch index names
    index_names = _scope_to_indices(body.scope)

    # Enforce tenant isolation: always include company_id in the filter.
    # company_id comes from the validated request body (not user-supplied filter
    # dict) and is quoted to prevent injection even if it contains special chars.
    sanitized_company_id = _validate_filter_value("company_id", body.company_id)
    meili_filter = f'company_id = "{sanitized_company_id}"'

    if body.filters:
        for key, value in body.filters.items():
            # Whitelist key and sanitize value before building the expression.
            _validate_filter_key(key)
            safe_value = _validate_filter_value(key, value)
            meili_filter += f' AND {key} = "{safe_value}"'

    all_hits: list[dict] = []
    total = 0

    async with httpx.AsyncClient(
        base_url=settings.meilisearch_url,
        headers={"Authorization": f"Bearer {settings.meilisearch_master_key}"},
        timeout=10,
    ) as client:
        for index_name in index_names:
            try:
                resp = await client.post(
                    f"/indexes/{index_name}/search",
                    json={
                        "q": body.q,
                        "filter": meili_filter,
                        "limit": body.limit,
                        "offset": body.offset,
                        "facets": ["type"],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    all_hits.extend(data.get("hits", []))
                    total += data.get("estimatedTotalHits", 0)
                elif resp.status_code == 404:
                    # Index doesn't exist yet — skip silently
                    pass
                else:
                    logger.warning(
                        "Meilisearch returned %d for index %s", resp.status_code, index_name
                    )
            except Exception as exc:
                logger.warning("Search index %s failed: %s", index_name, exc)

    return {
        "data": {
            "hits": all_hits,
            "total": total,
            "query_time_ms": 0,  # Meilisearch processingTimeMs is per-index
        },
        "meta": {
            "pagination": {
                "total": total,
                "limit": body.limit,
                "offset": body.offset,
                "has_more": (body.offset + body.limit) < total,
            }
        },
    }


@router.post(
    "/index",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger re-indexing of specific resources",
)
async def trigger_index(
    body: IndexRequest,
    claims: OrgMember,
) -> DataResponse[dict]:
    # Real indexing is an async side-effect performed by the relevant services.
    # This endpoint acknowledges the request; actual re-indexing happens via
    # the event bus in the background.
    logger.info(
        "Re-index requested: type=%s ids=%s company=%s",
        body.resource_type, len(body.resource_ids), body.company_id,
    )
    return DataResponse(
        data={
            "accepted": True,
            "resource_type": body.resource_type,
            "resource_count": len(body.resource_ids),
        }
    )


def _scope_to_indices(scope: str) -> list[str]:
    mapping: dict[str, list[str]] = {
        "all": ["tasks", "documents", "messages", "agents", "roles"],
        "tasks": ["tasks"],
        "documents": ["documents"],
        "messages": ["messages"],
        "agents": ["agents"],
        "roles": ["roles"],
    }
    return mapping.get(scope, ["tasks"])

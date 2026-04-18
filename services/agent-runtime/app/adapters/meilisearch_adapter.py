"""
Meilisearch adapter — unified full-text search across all tools.

Meilisearch does not produce webhooks. It is call-only.

Config keys (config["config"]):
    base_url:  str  - e.g. "http://meilisearch:7700"

Secret keys (config["secrets"]):
    master_key:  str  - Meilisearch master key (used for index management)
    search_key:  str  - Read-only search key (used for agent queries)

Capabilities declared:
    search:query, search:multi_index, document:index, document:delete_index

Indexes maintained:
    tickets   — Issues from Plane
    documents — Pages from Outline
    messages  — Posts from Mattermost

Every indexed document must include:
    id, title, content, source, url, created_at, updated_at, author, company_id
The `company_id` field is a filterable attribute used for tenant isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .base import BaseAdapter
from .types import (
    AdapterError,
    AdapterErrorCode,
    AdapterStatus,
    HealthStatus,
    NormalizedEvent,
)

logger = logging.getLogger(__name__)

# Canonical index names
INDEX_TICKETS = "tickets"
INDEX_DOCUMENTS = "documents"
INDEX_MESSAGES = "messages"

_ALL_INDEXES = [INDEX_TICKETS, INDEX_DOCUMENTS, INDEX_MESSAGES]

# Fields that agents can filter on — all must be declared at index creation
_FILTERABLE_ATTRIBUTES = ["company_id", "org_id", "source", "status", "author"]

# Fields agents can sort by
_SORTABLE_ATTRIBUTES = ["created_at", "updated_at"]

# Fields included in full-text indexing
_SEARCHABLE_ATTRIBUTES = ["title", "content", "author"]


class MeilisearchAdapter(BaseAdapter):
    """
    Adapter for Meilisearch — provides unified search across Plane, Outline, and Mattermost.

    Tenant isolation is enforced at the query layer: every search call must include
    a company_id filter. The adapter enforces this in search() and search_all() so
    agents cannot accidentally (or intentionally) see another company's data.
    """

    name = "meilisearch"
    version = "1.0.0"
    capabilities = [
        "search:query",
        "search:multi_index",
        "document:index",
        "document:delete_index",
    ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, config: dict[str, Any]) -> None:
        self._set_config(config)

        self._http_client = httpx.AsyncClient(
            base_url=self._cfg("base_url"),
            headers={"Authorization": f"Bearer {self._secret('master_key')}"},
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
        )

        status = await self.health_check()
        if not status.healthy:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Meilisearch health check failed during initialization: {status.error}",
                tool=self.name,
                operation="initialize",
                retryable=True,
            )

        # Ensure all three indexes exist with correct settings before accepting traffic
        await self._ensure_indexes()

        logger.info(
            "Meilisearch adapter initialized (base_url=%s, latency=%.1fms)",
            self._cfg("base_url"),
            status.latency_ms,
        )

    async def health_check(self) -> HealthStatus:
        assert self._http_client is not None, "Call initialize() before health_check()"
        start = time.monotonic()
        try:
            response = await self._http_client.get("/health", timeout=5.0)
            latency = self._measure_latency_ms(start)
            if response.status_code == 200 and response.json().get("status") == "available":
                return HealthStatus(
                    healthy=True,
                    latency_ms=latency,
                    status=AdapterStatus.CONNECTED,
                    capabilities_verified=["search:query"],
                    details={"status": "available"},
                )
            return HealthStatus(
                healthy=False,
                latency_ms=latency,
                status=AdapterStatus.ERROR,
                error="Meilisearch returned non-available status",
                details={"body": response.text[:200]},
            )
        except httpx.TimeoutException as exc:
            return HealthStatus(
                healthy=False,
                latency_ms=self._measure_latency_ms(start),
                status=AdapterStatus.DISCONNECTED,
                error=f"Connection timeout: {exc}",
            )
        except Exception as exc:
            return HealthStatus(
                healthy=False,
                latency_ms=self._measure_latency_ms(start),
                status=AdapterStatus.DISCONNECTED,
                error=str(exc),
            )

    async def shutdown(self) -> None:
        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception:
                logger.exception("Error closing Meilisearch HTTP client")
            finally:
                self._http_client = None
        logger.info("Meilisearch adapter shut down")

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    async def create_index(self, name: str, primary_key: str = "id") -> dict[str, Any]:
        """
        Create a Meilisearch index with the given primary key.

        If the index already exists this is a no-op (Meilisearch returns 200
        with the existing index or 202 for a task that is a no-op).
        """
        self.require_capability("document:index", "create_index")
        assert self._http_client is not None
        try:
            response = await self._http_client.post(
                "/indexes",
                json={"uid": name, "primaryKey": primary_key},
            )
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error creating index '{name}': {exc}",
                tool=self.name,
                operation="create_index",
                retryable=True,
            ) from exc
        # 200 = already exists (idempotent), 201 = created, 202 = task enqueued
        if response.status_code not in (200, 201, 202):
            self._raise_for_status(response, "create_index")
        return response.json()

    # ------------------------------------------------------------------
    # Document indexing
    # ------------------------------------------------------------------

    async def index_document(self, index: str, document: dict[str, Any]) -> dict[str, Any]:
        """
        Add or replace a single document in the given index.

        The document must contain at minimum: id, company_id.
        Missing company_id would break tenant isolation in searches.
        """
        self.require_capability("document:index", "index_document")
        self._validate_document(document, "index_document")
        return await self._put_documents(index, [document])

    async def index_documents_batch(
        self,
        index: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Bulk-index a list of documents into the given index.

        All documents must contain id and company_id.
        Meilisearch processes bulk indexing asynchronously — the returned
        dict contains a taskUid you can poll for completion.
        """
        self.require_capability("document:index", "index_documents_batch")
        if not documents:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="documents list must not be empty",
                tool=self.name,
                operation="index_documents_batch",
                retryable=False,
            )
        for doc in documents:
            self._validate_document(doc, "index_documents_batch")
        result = await self._put_documents(index, documents)
        logger.info(
            "Meilisearch batch indexed %d documents into '%s' (taskUid=%s)",
            len(documents),
            index,
            result.get("taskUid"),
        )
        return result

    async def delete_document(self, index: str, doc_id: str) -> dict[str, Any]:
        """Remove a single document from an index by its primary key."""
        self.require_capability("document:delete_index", "delete_document")
        assert self._http_client is not None
        try:
            response = await self._http_client.delete(
                f"/indexes/{index}/documents/{doc_id}"
            )
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error deleting document '{doc_id}' from '{index}': {exc}",
                tool=self.name,
                operation="delete_document",
                retryable=True,
            ) from exc
        self._raise_for_status(response, "delete_document")
        return response.json()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        index: str,
        query: str,
        filters: str | None = None,
        limit: int = 20,
        company_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Search a single index.

        `filters` is a Meilisearch filter string, e.g. "status = 'open'".
        If company_id is provided it is ANDed with any existing filter to
        enforce tenant isolation. Pass company_id whenever searching on behalf
        of an agent — do not skip it.
        """
        self.require_capability("search:query", "search")
        effective_filter = self._build_filter(company_id, filters)
        return await self._search_one(index, query, effective_filter, limit)

    async def search_all(
        self,
        query: str,
        company_id: str,
        filters: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search across all three indexes (tickets, documents, messages) simultaneously.

        company_id is required (not optional) because cross-index search with no
        tenant filter would expose data across companies.

        Returns {"results": [{"indexUid": str, "hits": list, ...}, ...]}.
        """
        self.require_capability("search:multi_index", "search_all")
        if not company_id:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="company_id is required for search_all to enforce tenant isolation",
                tool=self.name,
                operation="search_all",
                retryable=False,
            )
        effective_filter = self._build_filter(company_id, filters)
        queries = [
            {
                "indexUid": index_name,
                "q": query,
                "filter": effective_filter,
                "limit": limit,
                "attributesToHighlight": ["title", "content"],
                "highlightPreTag": "<em>",
                "highlightPostTag": "</em>",
            }
            for index_name in _ALL_INDEXES
        ]
        assert self._http_client is not None
        try:
            response = await self._http_client.post(
                "/multi-search",
                json={"queries": queries},
            )
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout during multi-search: {exc}",
                tool=self.name,
                operation="search_all",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error during multi-search: {exc}",
                tool=self.name,
                operation="search_all",
                retryable=True,
            ) from exc
        self._raise_for_status(response, "search_all")
        return response.json()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Return stats for all indexes: document counts, last update times, etc."""
        assert self._http_client is not None
        try:
            response = await self._http_client.get("/stats")
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error fetching stats: {exc}",
                tool=self.name,
                operation="get_stats",
                retryable=True,
            ) from exc
        self._raise_for_status(response, "get_stats")
        return response.json()

    # ------------------------------------------------------------------
    # Webhook (not supported)
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        # Meilisearch does not send webhooks
        return False

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> NormalizedEvent:
        # Meilisearch does not send webhooks. This should never be called.
        raise AdapterError(
            code=AdapterErrorCode.CAPABILITY_NOT_SUPPORTED,
            message="Meilisearch does not support inbound webhooks",
            tool=self.name,
            operation="handle_webhook",
            retryable=False,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _ensure_indexes(self) -> None:
        """
        Idempotently create the three canonical indexes with correct settings.

        Called during initialize(). Safe to call multiple times — Meilisearch
        ignores create requests for existing indexes.
        """
        for index_name in _ALL_INDEXES:
            await self.create_index(index_name, primary_key="id")
            # Configure which fields are filterable and sortable. This must be
            # done before indexing any documents or the filters won't work.
            assert self._http_client is not None
            try:
                await self._http_client.patch(
                    f"/indexes/{index_name}/settings",
                    json={
                        "filterableAttributes": _FILTERABLE_ATTRIBUTES,
                        "sortableAttributes": _SORTABLE_ATTRIBUTES,
                        "searchableAttributes": _SEARCHABLE_ATTRIBUTES,
                    },
                )
            except Exception:
                # Settings updates are best-effort during init; a subsequent
                # health check will surface real problems.
                logger.exception("Failed to update settings for index '%s'", index_name)

    async def _put_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST documents to an index. Meilisearch uses POST for upsert."""
        assert self._http_client is not None
        try:
            response = await self._http_client.post(
                f"/indexes/{index}/documents",
                json=documents,
            )
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout indexing documents into '{index}': {exc}",
                tool=self.name,
                operation="index_document",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error indexing documents into '{index}': {exc}",
                tool=self.name,
                operation="index_document",
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"index into {index}")
        return response.json()

    async def _search_one(
        self,
        index: str,
        query: str,
        filter_str: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Execute a single-index search request."""
        assert self._http_client is not None
        body: dict[str, Any] = {
            "q": query,
            "limit": min(limit, 1000),  # Meilisearch max is 1000
            "attributesToHighlight": ["title", "content"],
        }
        if filter_str:
            body["filter"] = filter_str
        try:
            response = await self._http_client.post(
                f"/indexes/{index}/search",
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout searching index '{index}': {exc}",
                tool=self.name,
                operation="search",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error searching index '{index}': {exc}",
                tool=self.name,
                operation="search",
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"search {index}")
        return response.json()

    @staticmethod
    def _build_filter(
        company_id: str | None,
        extra_filter: str | None,
    ) -> str | None:
        """
        Build a Meilisearch filter expression that includes tenant isolation.

        The company_id filter is always ANDed in when provided, ensuring
        agents cannot see records belonging to another company.
        """
        parts: list[str] = []
        if company_id:
            # Use double quotes around the value to handle IDs with hyphens/spaces
            parts.append(f'company_id = "{company_id}"')
        if extra_filter:
            parts.append(f"({extra_filter})")
        return " AND ".join(parts) if parts else None

    @staticmethod
    def _validate_document(document: dict[str, Any], operation: str) -> None:
        """
        Assert that required fields are present before indexing.

        Missing company_id is treated as a programming error, not a user error,
        because it would silently break tenant isolation.
        """
        missing = [f for f in ("id", "company_id") if not document.get(f)]
        if missing:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message=(
                    f"Document missing required fields for indexing: {missing}. "
                    "Every indexed document must have 'id' and 'company_id' "
                    "for primary key and tenant isolation."
                ),
                tool="meilisearch",
                operation=operation,
                retryable=False,
            )

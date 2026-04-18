"""
Outline adapter — documentation wiki.

Outline uses POST for all operations, with endpoints of the form:
    POST {base_url}/api/documents.list
    POST {base_url}/api/documents.create
    etc.

Config keys (config["config"]):
    base_url:        str           - e.g. "https://docs.example.com"
    collection_id:   str (optional) - Default collection for new documents

Secret keys (config["secrets"]):
    api_key:         str  - Outline API token (Bearer token)
    webhook_secret:  str  - HMAC-SHA256 secret for webhook verification

Capabilities declared:
    document:create, document:read, document:update, document:delete,
    document:search, document:export, collection:read, collection:create,
    webhook:receive
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from .base import BaseAdapter
from .types import (
    AdapterError,
    AdapterErrorCode,
    AdapterStatus,
    EventCategory,
    EventSource,
    HealthStatus,
    NormalizedEvent,
)

logger = logging.getLogger(__name__)

# Outline event type -> canonical AgentCompany event type
_OUTLINE_EVENT_MAP: dict[str, str] = {
    "documents.create": "document.created",
    "documents.update": "document.updated",
    "documents.publish": "document.published",
    "documents.archive": "document.archived",
    "documents.delete": "document.deleted",
    "collections.create": "collection.created",
    "collections.update": "collection.updated",
    "collections.delete": "collection.deleted",
}


class OutlineAdapter(BaseAdapter):
    """
    Adapter for Outline knowledge base / wiki.

    The Outline API is action-based (documents.create, documents.list, etc.)
    over HTTP POST. All requests carry a Bearer token in the Authorization header.
    """

    name = "outline"
    version = "1.0.0"
    capabilities = [
        "document:create",
        "document:read",
        "document:update",
        "document:delete",
        "document:search",
        "document:export",
        "collection:read",
        "collection:create",
        "webhook:receive",
    ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, config: dict[str, Any]) -> None:
        self._set_config(config)

        self._http_client = httpx.AsyncClient(
            base_url=self._cfg("base_url"),
            headers={
                "Authorization": f"Bearer {self._secret('api_key')}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

        status = await self.health_check()
        if not status.healthy:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Outline health check failed during initialization: {status.error}",
                tool=self.name,
                operation="initialize",
                retryable=True,
            )

        logger.info(
            "Outline adapter initialized (base_url=%s, latency=%.1fms)",
            self._cfg("base_url"),
            status.latency_ms,
        )

    async def health_check(self) -> HealthStatus:
        assert self._http_client is not None, "Call initialize() before health_check()"
        start = time.monotonic()
        try:
            # auth.info confirms the token is valid and returns the authenticated user
            response = await self._http_client.post(
                "/api/auth.info",
                json={},
                timeout=5.0,
            )
            latency = self._measure_latency_ms(start)
            if response.status_code == 200:
                data = response.json().get("data", {})
                return HealthStatus(
                    healthy=True,
                    latency_ms=latency,
                    status=AdapterStatus.CONNECTED,
                    capabilities_verified=["document:read"],
                    details={"user": data.get("user", {}).get("name")},
                )
            return HealthStatus(
                healthy=False,
                latency_ms=latency,
                status=AdapterStatus.ERROR,
                error=f"HTTP {response.status_code}",
                details={"status_code": response.status_code},
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
                logger.exception("Error closing Outline HTTP client")
            finally:
                self._http_client = None
        logger.info("Outline adapter shut down")

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def list_documents(
        self,
        collection_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return documents in a collection (or all accessible documents)."""
        self.require_capability("document:read", "list_documents")
        params: dict[str, Any] = {}
        if collection_id:
            params["collectionId"] = collection_id
        result = await self._call("documents.list", params)
        return result.get("data", [])

    async def create_document(
        self,
        title: str,
        text: str,
        collection_id: str | None = None,
        publish: bool = True,
    ) -> dict[str, Any]:
        """Create a new document. Publishes immediately by default."""
        self.require_capability("document:create", "create_document")
        if not title.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Document title must not be empty",
                tool=self.name,
                operation="create_document",
                retryable=False,
            )
        effective_collection_id = collection_id or self._cfg_get("collection_id")
        if not effective_collection_id:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message=(
                    "collection_id is required to create a document. "
                    "Pass it explicitly or set collection_id in adapter config."
                ),
                tool=self.name,
                operation="create_document",
                retryable=False,
            )
        result = await self._call(
            "documents.create",
            {
                "title": title,
                "text": text,
                "collectionId": effective_collection_id,
                "publish": publish,
            },
        )
        doc = result.get("data", {})
        logger.info(
            "Outline document created: id=%s title=%r collection=%s",
            doc.get("id"),
            title,
            effective_collection_id,
        )
        return doc

    async def update_document(
        self,
        doc_id: str,
        title: str | None = None,
        text: str | None = None,
        append: bool = False,
    ) -> dict[str, Any]:
        """Update document title and/or body. Set append=True to append text."""
        self.require_capability("document:update", "update_document")
        body: dict[str, Any] = {"id": doc_id}
        if title is not None:
            body["title"] = title
        if text is not None:
            body["text"] = text
            body["append"] = append
        result = await self._call("documents.update", body)
        return result.get("data", {})

    async def get_document(self, doc_id: str) -> dict[str, Any]:
        """Fetch a document by ID including its full Markdown body."""
        self.require_capability("document:read", "get_document")
        result = await self._call("documents.info", {"id": doc_id})
        data = result.get("data")
        if not data:
            raise AdapterError(
                code=AdapterErrorCode.RESOURCE_NOT_FOUND,
                message=f"Document {doc_id} not found",
                tool=self.name,
                operation="get_document",
                retryable=False,
            )
        return data

    async def search_documents(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Full-text search across all accessible documents.

        Returns a list of SearchResult objects, each containing
        {"document": {...}, "ranking": float, "context": str}.
        """
        self.require_capability("document:search", "search_documents")
        if not query.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Search query must not be empty",
                tool=self.name,
                operation="search_documents",
                retryable=False,
            )
        result = await self._call(
            "documents.search",
            {"query": query, "limit": min(limit, 100)},
        )
        return result.get("data", [])

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document permanently. Returns True on success."""
        self.require_capability("document:delete", "delete_document")
        await self._call("documents.delete", {"id": doc_id})
        logger.info("Outline document deleted: id=%s", doc_id)
        return True

    async def export_document(self, doc_id: str, format: str = "markdown") -> str:
        """
        Export a document as markdown or html.

        Returns the raw export content as a string.
        """
        self.require_capability("document:export", "export_document")
        if format not in ("markdown", "html"):
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message=f"Unsupported export format '{format}'. Use 'markdown' or 'html'.",
                tool=self.name,
                operation="export_document",
                retryable=False,
            )
        result = await self._call("documents.export", {"id": doc_id})
        # Outline returns the export in data field as a string
        return result.get("data", "")

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def list_collections(self) -> list[dict[str, Any]]:
        """Return all collections the authenticated user can access."""
        self.require_capability("collection:read", "list_collections")
        result = await self._call("collections.list", {})
        return result.get("data", [])

    async def create_collection(
        self,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new collection (folder)."""
        self.require_capability("collection:create", "create_collection")
        if not name.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Collection name must not be empty",
                tool=self.name,
                operation="create_collection",
                retryable=False,
            )
        result = await self._call(
            "collections.create",
            {"name": name, "description": description},
        )
        col = result.get("data", {})
        logger.info("Outline collection created: id=%s name=%r", col.get("id"), name)
        return col

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        """Verify Outline's HMAC-SHA256 webhook signature."""
        # Outline sends the signature as "sha256=<hex>" in X-Outline-Signature
        signature_header = headers.get("X-Outline-Signature", "") or headers.get(
            "x-outline-signature", ""
        )
        if not signature_header:
            return False
        expected = "sha256=" + hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> NormalizedEvent:
        """
        Translate a raw Outline webhook payload into a NormalizedEvent.

        Outline embeds the event name in payload["event"] and the document
        in payload["payload"]["model"].
        """
        outline_event = payload.get("event", "")
        if not outline_event:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Outline webhook payload missing 'event' field",
                tool=self.name,
                operation="handle_webhook",
                retryable=False,
            )

        normalized_type = _OUTLINE_EVENT_MAP.get(outline_event, f"outline.{outline_event}")
        inner = payload.get("payload", {})
        model = inner.get("model", {})

        # Determine category based on the event prefix
        category = (
            EventCategory.DOCUMENT
            if outline_event.startswith("documents.")
            else EventCategory.SYSTEM
        )

        return NormalizedEvent(
            source=EventSource.OUTLINE,
            category=category,
            event_type=normalized_type,
            resource_type="document" if category == EventCategory.DOCUMENT else "collection",
            resource_external_id=model.get("id"),
            actor_id=payload.get("actorId"),
            actor_type="human",
            data={
                "document": model,
                "collection_id": model.get("collectionId"),
            },
            raw=payload,
        )

    # ------------------------------------------------------------------
    # Private HTTP helper
    # ------------------------------------------------------------------

    async def _call(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        """
        Call an Outline API action (e.g. "documents.create").

        Outline uses POST for every action at /api/<action>.
        """
        assert self._http_client is not None
        path = f"/api/{action}"
        try:
            response = await self._http_client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout calling Outline {action}: {exc}",
                tool=self.name,
                operation=action,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Outline {action}: {exc}",
                tool=self.name,
                operation=action,
                retryable=True,
            ) from exc
        self._raise_for_status(response, action)
        return response.json()

"""
Adapter registry — manages the lifecycle of all tool adapter instances.

The registry is a process-level singleton. Each company/tool pair maps to
one live adapter instance. The registry owns initialization and shutdown,
so callers never manage adapter lifecycle directly.

Key:   (company_id, tool_name)
Value: initialized BaseAdapter instance

Thread safety: all mutations go through an asyncio.Lock so concurrent
initialize and shutdown calls are serialized.
"""

from __future__ import annotations

import asyncio
import logging

from .base import BaseAdapter
from .mattermost import MattermostAdapter
from .meilisearch_adapter import MeilisearchAdapter
from .outline import OutlineAdapter
from .plane import PlaneAdapter
from .types import AdapterError, AdapterErrorCode, HealthStatus

logger = logging.getLogger(__name__)

# Map config["tool"] string -> adapter class.
# Add new adapters here when integrating additional tools.
_ADAPTER_CLASS_MAP: dict[str, type[BaseAdapter]] = {
    "plane": PlaneAdapter,
    "outline": OutlineAdapter,
    "mattermost": MattermostAdapter,
    "meilisearch": MeilisearchAdapter,
}


class AdapterRegistry:
    """
    Manages the lifecycle of all adapter instances for all companies.

    Usage:
        registry = AdapterRegistry()

        # Register an adapter (initialize it)
        await registry.register(
            company_id="acme",
            tool="plane",
            config={
                "config": {"base_url": "...", "workspace_slug": "acme"},
                "secrets": {"api_key": "...", "webhook_secret": "..."},
            },
        )

        # Retrieve for use
        plane = registry.get("acme", "plane")
        issues = await plane.list_issues(project_id="proj-123")

        # Shutdown everything gracefully
        await registry.shutdown_all()
    """

    def __init__(self) -> None:
        # (company_id, tool_name) -> live adapter instance
        self._adapters: dict[tuple[str, str], BaseAdapter] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(
        self,
        company_id: str,
        tool: str,
        config: dict,
    ) -> BaseAdapter:
        """
        Initialize an adapter and register it under (company_id, tool).

        If an adapter is already registered for this key, it is shut down
        and replaced with the new one. This allows live config reloads.

        Raises ValueError if the tool name is unknown.
        Raises AdapterError if initialization fails (e.g. bad credentials).
        """
        if not company_id:
            raise ValueError("company_id must not be empty")
        if not tool:
            raise ValueError("tool name must not be empty")

        cls = _ADAPTER_CLASS_MAP.get(tool)
        if cls is None:
            raise ValueError(
                f"Unknown adapter type: '{tool}'. "
                f"Registered adapters: {sorted(_ADAPTER_CLASS_MAP.keys())}"
            )

        adapter = cls()
        # initialize() validates config and raises AdapterError on failure,
        # so we do it outside the lock to avoid holding it during I/O.
        await adapter.initialize(config)

        key = (company_id, tool)
        async with self._lock:
            existing = self._adapters.get(key)
            if existing is not None:
                logger.info(
                    "Replacing existing %s adapter for company %s", tool, company_id
                )
                await self._safe_shutdown(existing)
            self._adapters[key] = adapter

        logger.info("Registered %s adapter for company %s", tool, company_id)
        return adapter

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, company_id: str, tool: str) -> BaseAdapter:
        """
        Return the live adapter for (company_id, tool).

        Raises AdapterError(CONNECTION_REFUSED) if no adapter is registered.
        This is a synchronous call — no I/O is performed.
        """
        key = (company_id, tool)
        adapter = self._adapters.get(key)
        if adapter is None:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=(
                    f"No adapter registered for tool='{tool}' "
                    f"company='{company_id}'. "
                    "Call registry.register() before use."
                ),
                tool=tool,
                operation="get",
                retryable=False,
            )
        return adapter

    def get_optional(self, company_id: str, tool: str) -> BaseAdapter | None:
        """Return the adapter or None if not registered. No exception raised."""
        return self._adapters.get((company_id, tool))

    def is_registered(self, company_id: str, tool: str) -> bool:
        """Return True if an adapter is registered for this company/tool pair."""
        return (company_id, tool) in self._adapters

    def registered_tools(self, company_id: str) -> list[str]:
        """Return the list of tool names registered for a company."""
        return [tool for (cid, tool) in self._adapters if cid == company_id]

    # ------------------------------------------------------------------
    # Deregistration
    # ------------------------------------------------------------------

    async def deregister(self, company_id: str, tool: str) -> None:
        """Shutdown and remove the adapter for (company_id, tool)."""
        key = (company_id, tool)
        async with self._lock:
            adapter = self._adapters.pop(key, None)
        if adapter is not None:
            await self._safe_shutdown(adapter)
            logger.info("Deregistered %s adapter for company %s", tool, company_id)

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def health_check_all(self) -> dict[str, HealthStatus]:
        """
        Run health_check() on every registered adapter concurrently.

        Returns a mapping of "company_id/tool" -> HealthStatus.
        Never raises — individual adapter failures are captured in HealthStatus.
        """
        # Snapshot the current adapters to avoid holding the lock during I/O
        snapshot = dict(self._adapters)

        async def _check(key: tuple[str, str], adapter: BaseAdapter) -> tuple[str, HealthStatus]:
            company_id, tool = key
            label = f"{company_id}/{tool}"
            try:
                status = await adapter.health_check()
            except Exception as exc:
                logger.exception("Unexpected error in health_check for %s", label)
                status = HealthStatus(
                    healthy=False,
                    latency_ms=0.0,
                    error=f"Unexpected exception: {exc}",
                )
            return label, status

        results = await asyncio.gather(
            *[_check(key, adapter) for key, adapter in snapshot.items()]
        )
        return dict(results)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown_all(self) -> None:
        """Shutdown all registered adapters concurrently."""
        async with self._lock:
            snapshot = dict(self._adapters)
            self._adapters.clear()

        if not snapshot:
            return

        await asyncio.gather(
            *[self._safe_shutdown(adapter) for adapter in snapshot.values()]
        )
        logger.info("All adapters shut down (%d total)", len(snapshot))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_shutdown(adapter: BaseAdapter) -> None:
        """Shutdown an adapter, swallowing exceptions so they don't abort a batch."""
        try:
            await adapter.shutdown()
        except Exception:
            logger.exception(
                "Error shutting down %s adapter — continuing cleanup", adapter.name
            )

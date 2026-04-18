"""
Abstract base class for all tool adapters.

Every adapter — Plane, Outline, Mattermost, Meilisearch — must implement this
interface. The agent runtime and circuit breaker only depend on BaseAdapter,
never on the concrete implementations, so tools are fully swappable.

Design rules enforced here:
- Secrets must not be logged. Access them only inside method bodies via
  self._config["secrets"]["key"], not stored as attributes.
- health_check() must never raise — catch all exceptions and return HealthStatus.
- All public methods that call external APIs must raise AdapterError, not raw
  httpx errors or tool SDK exceptions.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .types import (
    AdapterError,
    AdapterErrorCode,
    HealthStatus,
    NormalizedEvent,
)


class BaseAdapter(ABC):
    """
    Abstract base for all tool adapters.

    Subclasses receive a config dict with two sub-dicts:
      config["config"]  — non-secret configuration (URLs, workspace IDs, etc.)
      config["secrets"] — resolved secrets (API keys, tokens) — never logged

    Lifecycle:
      initialize(config) -> use the adapter -> shutdown()
    """

    # Override in every subclass — used for error messages and logging
    name: str = ""
    version: str = "1.0.0"
    # Declare capabilities this adapter supports, e.g. ["issue:create", "issue:read"]
    capabilities: list[str] = []

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None
        # Config populated by initialize(); kept private so subclasses don't
        # accidentally log secrets through default __repr__ or similar.
        self.__config: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def initialize(self, config: dict[str, Any]) -> None:
        """
        Initialize the adapter with the provided configuration.

        Called once after construction. Implementations should:
        1. Store config via self._set_config(config).
        2. Build the httpx.AsyncClient with auth headers.
        3. Run a health check to fail fast on bad credentials.

        Raises AdapterError on failure so the registry can surface a clear error.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Verify the tool is reachable and credentials are valid.

        Must complete within 5 seconds. Must NOT raise — return
        HealthStatus(healthy=False, error=...) on any exception.
        """
        ...

    @abstractmethod
    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> NormalizedEvent:
        """
        Transform a raw webhook payload from the tool into a NormalizedEvent.

        Called by the webhook handler in Core API for every inbound webhook.
        Implementations should validate the payload structure and raise
        AdapterError(VALIDATION_ERROR) if it is malformed.
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Gracefully shut down the adapter.

        Close the HTTP client and clear any sensitive state.
        Must not raise — log errors and continue.
        """
        ...

    # ------------------------------------------------------------------
    # Capability declaration
    # ------------------------------------------------------------------

    def supports(self, capability: str) -> bool:
        """Return True if this adapter declares the given capability."""
        return capability in self.capabilities

    def require_capability(self, capability: str, operation: str) -> None:
        """
        Raise AdapterError if the adapter does not support the capability.

        Call this at the start of any method that exercises a capability,
        so callers get a clear error instead of a confusing 404 or 405.
        """
        if not self.supports(capability):
            raise AdapterError(
                code=AdapterErrorCode.CAPABILITY_NOT_SUPPORTED,
                message=f"{self.name} does not support capability '{capability}'",
                tool=self.name,
                operation=operation,
                retryable=False,
            )

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        """
        Verify the webhook signature from the tool.

        Returns True if valid, False if not. Must NOT raise on invalid
        signatures — the caller interprets False as a 401 response.

        Default implementation returns False (no-op for tools without webhooks).
        Override in adapters that receive webhooks.
        """
        return False

    # ------------------------------------------------------------------
    # Shared HTTP error translation
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        """
        Translate an unsuccessful HTTP response into an AdapterError and raise it.

        Call this after every API request. Never let raw httpx errors propagate
        out of an adapter — this method ensures callers always see AdapterError.
        """
        if response.is_success:
            return

        status = response.status_code
        # 429 and 5xx are transient; the runtime's retry logic handles them.
        retryable = status in (429, 500, 502, 503, 504)
        retry_after: int | None = None

        if status == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            code = AdapterErrorCode.RATE_LIMITED
        elif status == 401:
            code = AdapterErrorCode.AUTH_FAILED
        elif status == 403:
            code = AdapterErrorCode.PERMISSION_DENIED
        elif status == 404:
            code = AdapterErrorCode.RESOURCE_NOT_FOUND
            retryable = False
        elif status == 422:
            code = AdapterErrorCode.VALIDATION_ERROR
            retryable = False
        elif status >= 500:
            code = AdapterErrorCode.SERVER_ERROR
        else:
            code = AdapterErrorCode.SERVER_ERROR

        raise AdapterError(
            code=code,
            message=f"HTTP {status} from {self.name}.{operation}",
            tool=self.name,
            operation=operation,
            retryable=retryable,
            retry_after_seconds=retry_after,
            details={
                "status_code": status,
                # Truncate to avoid logging enormous error bodies
                "response_body": response.text[:500],
            },
        )

    # ------------------------------------------------------------------
    # Config helpers — keep secrets off instance attributes
    # ------------------------------------------------------------------

    def _set_config(self, config: dict[str, Any]) -> None:
        """Store config. Called by initialize() implementations."""
        self.__config = config

    def _cfg(self, key: str) -> Any:
        """Read a non-secret config value. Raises KeyError with a clear message."""
        try:
            return self.__config["config"][key]
        except KeyError:
            raise KeyError(
                f"{self.name} adapter missing required config key: '{key}'"
            ) from None

    def _cfg_get(self, key: str, default: Any = None) -> Any:
        """Read an optional non-secret config value."""
        return self.__config.get("config", {}).get(key, default)

    def _secret(self, key: str) -> str:
        """Read a secret value. Raises KeyError with a clear message."""
        try:
            return self.__config["secrets"][key]
        except KeyError:
            raise KeyError(
                f"{self.name} adapter missing required secret: '{key}'"
            ) from None

    # ------------------------------------------------------------------
    # Timing helper for health checks
    # ------------------------------------------------------------------

    @staticmethod
    def _measure_latency_ms(start: float) -> float:
        """Return elapsed milliseconds since `start` (from time.monotonic())."""
        return round((time.monotonic() - start) * 1000, 1)

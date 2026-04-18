"""
Shared types for the adapter layer.

NormalizedEvent is the canonical representation of any external event (webhook, poll, internal).
HealthStatus is the uniform health signal every adapter exposes to the registry and circuit breaker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class EventSource(StrEnum):
    PLANE = "plane"
    OUTLINE = "outline"
    MATTERMOST = "mattermost"
    MEILISEARCH = "meilisearch"
    INTERNAL = "internal"


class EventCategory(StrEnum):
    TASK = "task"
    DOCUMENT = "document"
    MESSAGE = "message"
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AdapterStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    ERROR = "error"


class AdapterErrorCode(StrEnum):
    # Connectivity
    CONNECTION_TIMEOUT = "connection_timeout"
    CONNECTION_REFUSED = "connection_refused"
    # Authentication
    AUTH_FAILED = "auth_failed"
    AUTH_EXPIRED = "auth_expired"
    # Authorization
    PERMISSION_DENIED = "permission_denied"
    # Request errors
    RESOURCE_NOT_FOUND = "resource_not_found"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"
    # Server errors
    SERVER_ERROR = "server_error"
    UNAVAILABLE = "unavailable"
    # Adapter-level errors
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    CIRCUIT_OPEN = "circuit_open"


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NormalizedEvent:
    """
    Canonical representation of any event that enters the AgentCompany system.

    All adapters translate raw webhook payloads into NormalizedEvent before
    publishing to Redis. Downstream consumers (agent runtime) never touch
    raw tool-specific payloads.
    """

    # --- Identity ---
    id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex}")
    # Links related events in a causal chain (e.g. task.created -> task.assigned)
    correlation_id: str | None = None

    # --- Classification ---
    source: EventSource = EventSource.INTERNAL
    category: EventCategory = EventCategory.SYSTEM
    # e.g. "task.created", "document.updated", "message.mentioned"
    event_type: str = ""

    # --- Tenant context ---
    org_id: str = ""
    company_id: str = ""

    # --- Actor (who triggered the event) ---
    actor_id: str | None = None
    # "human" | "agent" | "system"
    actor_type: str | None = None

    # --- Subject resource ---
    resource_type: str | None = None
    resource_id: str | None = None
    # The ID as it exists in the originating tool (Plane issue ID, Outline doc ID, etc.)
    resource_external_id: str | None = None

    # --- Payload ---
    # Normalized, tool-agnostic payload. Schema varies by event_type.
    data: dict[str, Any] = field(default_factory=dict)
    # The original, unmodified payload from the tool — kept for debugging and re-processing.
    raw: dict[str, Any] = field(default_factory=dict)

    # --- Timestamps ---
    # When the event occurred in the originating tool (if provided)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    # When our system received the event
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for Redis publishing."""
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "source": self.source.value,
            "category": self.category.value,
            "event_type": self.event_type,
            "org_id": self.org_id,
            "company_id": self.company_id,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_external_id": self.resource_external_id,
            "data": self.data,
            "raw": self.raw,
            "timestamp": self.timestamp.isoformat(),
            "received_at": self.received_at.isoformat(),
        }


@dataclass
class HealthStatus:
    """
    Uniform health signal returned by every adapter's health_check().

    Must never raise — callers depend on always getting a result so
    the circuit breaker can act on it.
    """

    healthy: bool
    latency_ms: float
    # Human-readable status label for dashboards
    status: AdapterStatus = AdapterStatus.CONNECTED
    # Tool-specific diagnostics (e.g. workspace reachable, auth valid)
    details: dict[str, Any] = field(default_factory=dict)
    # Set when healthy=False to explain why
    error: str | None = None
    # Capabilities confirmed reachable during this check
    capabilities_verified: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AdapterError(Exception):
    """
    Uniform exception raised by all adapters.

    The runtime catches AdapterError and decides whether to retry
    (retryable=True), surface to the user, or open the circuit breaker.
    Never let raw httpx or tool-SDK exceptions escape an adapter — always
    wrap them in AdapterError so the caller gets actionable context.
    """

    code: AdapterErrorCode
    message: str
    # Which adapter raised this
    tool: str
    # Which method/operation was executing
    operation: str
    # True for transient failures worth retrying (429, 5xx, timeouts)
    retryable: bool
    # For rate-limit errors: when the caller may retry
    retry_after_seconds: int | None = None
    # Extra tool-specific context (status code, response snippet, etc.)
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return (
            f"AdapterError[{self.code.value}] {self.tool}.{self.operation}: "
            f"{self.message}"
            + (f" (retry after {self.retry_after_seconds}s)" if self.retry_after_seconds else "")
        )

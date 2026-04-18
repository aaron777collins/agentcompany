"""
AgentCompany tool adapters.

This package provides the integration layer between the agent runtime and
the external tools it orchestrates: Plane (project management), Outline
(documentation), Mattermost (team chat), and Meilisearch (unified search).

Public API
----------
The only stable interface is:

    BaseAdapter     — abstract base all adapters implement
    AdapterRegistry — process-level registry; initialize once at startup

    PlaneAdapter        — Plane project management
    OutlineAdapter      — Outline documentation wiki
    MattermostAdapter   — Mattermost team chat
    MeilisearchAdapter  — Meilisearch unified search

    NormalizedEvent     — canonical event type for all inbound webhooks
    HealthStatus        — uniform health signal from every adapter
    AdapterError        — uniform exception raised by all adapters
    AdapterErrorCode    — error code enum for structured error handling

Do not import from the individual submodules directly in application code —
import from this package so the public surface stays stable.
"""

from .base import BaseAdapter
from .mattermost import MattermostAdapter
from .meilisearch_adapter import MeilisearchAdapter
from .outline import OutlineAdapter
from .plane import PlaneAdapter
from .registry import AdapterRegistry
from .types import (
    AdapterError,
    AdapterErrorCode,
    AdapterStatus,
    EventCategory,
    EventSource,
    HealthStatus,
    NormalizedEvent,
)

__all__ = [
    # Base
    "BaseAdapter",
    # Concrete adapters
    "PlaneAdapter",
    "OutlineAdapter",
    "MattermostAdapter",
    "MeilisearchAdapter",
    # Registry
    "AdapterRegistry",
    # Types
    "NormalizedEvent",
    "HealthStatus",
    "AdapterError",
    "AdapterErrorCode",
    "AdapterStatus",
    "EventSource",
    "EventCategory",
]

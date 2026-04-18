"""
Plane adapter — project management (Jira-equivalent).

Config keys (config["config"]):
    base_url:        str  - e.g. "https://plane.example.com"
    workspace_slug:  str  - Plane workspace identifier
    project_id:      str  - Default project ID (used when not explicitly passed)

Secret keys (config["secrets"]):
    api_key:         str  - Plane API key (X-API-Key header)
    webhook_secret:  str  - HMAC-SHA256 secret for webhook signature verification

Capabilities declared:
    issue:create, issue:read, issue:update, issue:delete,
    issue:comment, cycle:read, cycle:create, label:read,
    label:create, project:read, project:create, webhook:receive
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import date
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

# Plane event type -> canonical AgentCompany event type
_PLANE_EVENT_MAP: dict[str, str] = {
    "issue.created": "task.created",
    "issue.updated": "task.updated",
    "issue.deleted": "task.deleted",
    "issue_comment.created": "task.commented",
    "issue_comment.updated": "task.commented",
    "cycle.created": "cycle.created",
    "cycle.updated": "cycle.updated",
}

# HTTP status codes that warrant a retry
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class PlaneAdapter(BaseAdapter):
    """
    Adapter for Plane project management.

    All methods that call the Plane REST API are async and raise AdapterError
    on failure. Callers must never catch raw httpx exceptions from here.
    """

    name = "plane"
    version = "1.0.0"
    capabilities = [
        "issue:create",
        "issue:read",
        "issue:update",
        "issue:delete",
        "issue:comment",
        "cycle:read",
        "cycle:create",
        "label:read",
        "label:create",
        "project:read",
        "project:create",
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
                "X-API-Key": self._secret("api_key"),
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )

        status = await self.health_check()
        if not status.healthy:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Plane health check failed during initialization: {status.error}",
                tool=self.name,
                operation="initialize",
                retryable=True,
            )

        logger.info(
            "Plane adapter initialized (workspace=%s, latency=%.1fms)",
            self._cfg("workspace_slug"),
            status.latency_ms,
        )

    async def health_check(self) -> HealthStatus:
        assert self._http_client is not None, "Call initialize() before health_check()"
        start = time.monotonic()
        try:
            workspace = self._cfg("workspace_slug")
            response = await self._http_client.get(
                f"/api/v1/workspaces/{workspace}/",
                timeout=5.0,
            )
            latency = self._measure_latency_ms(start)
            if response.status_code == 200:
                return HealthStatus(
                    healthy=True,
                    latency_ms=latency,
                    status=AdapterStatus.CONNECTED,
                    capabilities_verified=["issue:read"],
                    details={"workspace": workspace},
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
                logger.exception("Error closing Plane HTTP client")
            finally:
                self._http_client = None
        logger.info("Plane adapter shut down")

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def list_projects(self) -> list[dict[str, Any]]:
        """Return all projects in the workspace."""
        self.require_capability("project:read", "list_projects")
        workspace = self._cfg("workspace_slug")
        response = await self._get(f"/api/v1/workspaces/{workspace}/projects/")
        return response.get("results", response) if isinstance(response, dict) else response

    async def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new project in the workspace."""
        self.require_capability("project:create", "create_project")
        if not name.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Project name must not be empty",
                tool=self.name,
                operation="create_project",
                retryable=False,
            )
        workspace = self._cfg("workspace_slug")
        return await self._post(
            f"/api/v1/workspaces/{workspace}/projects/",
            body={"name": name, "description": description, "network": 2},
        )

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    async def list_issues(
        self,
        project_id: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List issues for a project, with optional filter params."""
        self.require_capability("issue:read", "list_issues")
        workspace = self._cfg("workspace_slug")
        response = await self._get(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/",
            params=filters or {},
        )
        return response.get("results", response) if isinstance(response, dict) else response

    async def get_issue(self, issue_id: str) -> dict[str, Any]:
        """Return a single issue by ID."""
        self.require_capability("issue:read", "get_issue")
        workspace = self._cfg("workspace_slug")
        project_id = self._cfg("project_id")
        return await self._get(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/",
        )

    async def create_issue(
        self,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
        assignee: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue in the given project."""
        self.require_capability("issue:create", "create_issue")
        if not title.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Issue title must not be empty",
                tool=self.name,
                operation="create_issue",
                retryable=False,
            )
        workspace = self._cfg("workspace_slug")
        body: dict[str, Any] = {
            "name": title,
            "description_html": description,
            "priority": priority,
        }
        if assignee:
            body["assignees"] = [assignee]
        if labels:
            body["label_ids"] = labels

        result = await self._post(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/",
            body=body,
        )
        logger.info(
            "Plane issue created: project=%s id=%s title=%r",
            project_id,
            result.get("id"),
            title,
        )
        return result

    async def update_issue(self, issue_id: str, **fields: Any) -> dict[str, Any]:
        """Patch arbitrary fields on an issue."""
        self.require_capability("issue:update", "update_issue")
        workspace = self._cfg("workspace_slug")
        project_id = self._cfg("project_id")
        result = await self._patch(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/",
            body=fields,
        )
        logger.info("Plane issue updated: id=%s fields=%s", issue_id, list(fields.keys()))
        return result

    async def add_comment(self, issue_id: str, text: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        self.require_capability("issue:comment", "add_comment")
        if not text.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Comment text must not be empty",
                tool=self.name,
                operation="add_comment",
                retryable=False,
            )
        workspace = self._cfg("workspace_slug")
        project_id = self._cfg("project_id")
        return await self._post(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{issue_id}/comments/",
            body={"comment_html": text},
        )

    # ------------------------------------------------------------------
    # Cycles (Sprints)
    # ------------------------------------------------------------------

    async def list_cycles(self, project_id: str) -> list[dict[str, Any]]:
        """Return all cycles (sprints) for a project."""
        self.require_capability("cycle:read", "list_cycles")
        workspace = self._cfg("workspace_slug")
        response = await self._get(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/cycles/",
        )
        return response.get("results", response) if isinstance(response, dict) else response

    async def create_cycle(
        self,
        project_id: str,
        name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Create a new sprint/cycle in a project."""
        self.require_capability("cycle:create", "create_cycle")
        workspace = self._cfg("workspace_slug")
        body: dict[str, Any] = {"name": name}
        if start_date:
            body["start_date"] = start_date.isoformat()
        if end_date:
            body["end_date"] = end_date.isoformat()
        return await self._post(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/cycles/",
            body=body,
        )

    async def move_issue_to_cycle(self, issue_id: str, cycle_id: str) -> dict[str, Any]:
        """Add an issue to a sprint/cycle."""
        self.require_capability("cycle:create", "move_issue_to_cycle")
        workspace = self._cfg("workspace_slug")
        project_id = self._cfg("project_id")
        return await self._post(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/",
            body={"issues": [issue_id]},
        )

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    async def list_labels(self, project_id: str) -> list[dict[str, Any]]:
        """Return all labels for a project."""
        self.require_capability("label:read", "list_labels")
        workspace = self._cfg("workspace_slug")
        response = await self._get(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/labels/",
        )
        return response.get("results", response) if isinstance(response, dict) else response

    async def create_label(
        self,
        project_id: str,
        name: str,
        color: str = "#6b7280",
    ) -> dict[str, Any]:
        """Create a label in a project."""
        self.require_capability("label:create", "create_label")
        workspace = self._cfg("workspace_slug")
        return await self._post(
            f"/api/v1/workspaces/{workspace}/projects/{project_id}/labels/",
            body={"name": name, "color": color},
        )

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        """Verify Plane's HMAC-SHA256 webhook signature."""
        # Plane sends the signature in X-Plane-Signature as "sha256=<hex>"
        signature_header = headers.get("X-Plane-Signature", "") or headers.get(
            "x-plane-signature", ""
        )
        if not signature_header:
            return False
        expected = "sha256=" + hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature_header)

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> NormalizedEvent:
        """
        Translate a raw Plane webhook payload into a NormalizedEvent.

        Plane embeds the event type in payload["event"] and the resource
        in payload["data"].
        """
        plane_event = payload.get("event", "")
        if not plane_event:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Plane webhook payload missing 'event' field",
                tool=self.name,
                operation="handle_webhook",
                retryable=False,
            )

        normalized_type = _PLANE_EVENT_MAP.get(plane_event, f"plane.{plane_event}")
        issue_data = payload.get("data", {})

        return NormalizedEvent(
            source=EventSource.PLANE,
            category=EventCategory.TASK,
            event_type=normalized_type,
            resource_type="task",
            resource_external_id=issue_data.get("id"),
            actor_id=issue_data.get("updated_by") or issue_data.get("created_by"),
            actor_type="human",
            data={
                "issue": issue_data,
                "workspace": self._cfg_get("workspace_slug"),
                "project_id": self._cfg_get("project_id"),
            },
            raw=payload,
        )

    # ------------------------------------------------------------------
    # Private HTTP helpers — retry on transient errors
    # ------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        assert self._http_client is not None
        try:
            response = await self._http_client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout calling Plane GET {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Plane GET {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"GET {path}")
        return response.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        assert self._http_client is not None
        try:
            response = await self._http_client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout calling Plane POST {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Plane POST {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"POST {path}")
        return response.json()

    async def _patch(self, path: str, body: dict[str, Any]) -> Any:
        assert self._http_client is not None
        try:
            response = await self._http_client.patch(path, json=body)
        except httpx.TimeoutException as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_TIMEOUT,
                message=f"Timeout calling Plane PATCH {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Plane PATCH {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"PATCH {path}")
        return response.json()

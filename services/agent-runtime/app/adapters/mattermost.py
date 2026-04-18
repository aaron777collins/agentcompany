"""
Mattermost adapter — team chat platform.

Mattermost uses REST API v4 with Bearer token authentication.

Config keys (config["config"]):
    base_url:     str  - e.g. "https://chat.example.com"
    team_id:      str  - Default Mattermost team ID

Secret keys (config["secrets"]):
    bot_token:      str  - Mattermost bot access token
    webhook_token:  str  - Outgoing webhook verification token (shared token in payload body)

Capabilities declared:
    message:post, message:read, message:update, message:delete,
    message:search, channel:read, channel:create, channel:join,
    user:read, file:upload, reaction:add, webhook:receive
"""

from __future__ import annotations

import hmac
import json
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


class MattermostAdapter(BaseAdapter):
    """
    Adapter for Mattermost team chat.

    Note on webhook verification: Mattermost outgoing webhooks embed a
    shared token in the request body rather than using HMAC signatures.
    verify_webhook_signature() implements this token comparison.
    """

    name = "mattermost"
    version = "1.0.0"
    capabilities = [
        "message:post",
        "message:read",
        "message:update",
        "message:delete",
        "message:search",
        "channel:read",
        "channel:create",
        "channel:join",
        "user:read",
        "file:upload",
        "reaction:add",
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
                "Authorization": f"Bearer {self._secret('bot_token')}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0),
        )

        status = await self.health_check()
        if not status.healthy:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Mattermost health check failed during initialization: {status.error}",
                tool=self.name,
                operation="initialize",
                retryable=True,
            )

        logger.info(
            "Mattermost adapter initialized (base_url=%s, latency=%.1fms)",
            self._cfg("base_url"),
            status.latency_ms,
        )

    async def health_check(self) -> HealthStatus:
        assert self._http_client is not None, "Call initialize() before health_check()"
        start = time.monotonic()
        try:
            response = await self._http_client.get("/api/v4/system/ping", timeout=5.0)
            latency = self._measure_latency_ms(start)
            if response.status_code == 200:
                data = response.json()
                return HealthStatus(
                    healthy=True,
                    latency_ms=latency,
                    status=AdapterStatus.CONNECTED,
                    capabilities_verified=["message:post"],
                    details={"status": data.get("status"), "version": data.get("Version")},
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
                logger.exception("Error closing Mattermost HTTP client")
            finally:
                self._http_client = None
        logger.info("Mattermost adapter shut down")

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    async def list_channels(self, team_id: str | None = None) -> list[dict[str, Any]]:
        """List public channels in a team."""
        self.require_capability("channel:read", "list_channels")
        effective_team_id = team_id or self._cfg("team_id")
        return await self._get(f"/api/v4/teams/{effective_team_id}/channels")

    async def create_channel(
        self,
        name: str,
        display_name: str,
        channel_type: str = "O",
        team_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a channel. channel_type: "O" = public, "P" = private.

        `name` is the URL slug (lowercase, no spaces).
        `display_name` is the human-readable label shown in the UI.
        """
        self.require_capability("channel:create", "create_channel")
        if not name.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Channel name must not be empty",
                tool=self.name,
                operation="create_channel",
                retryable=False,
            )
        if channel_type not in ("O", "P"):
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message=(
                    f"Invalid channel_type '{channel_type}'. "
                    "Must be 'O' (public) or 'P' (private)."
                ),
                tool=self.name,
                operation="create_channel",
                retryable=False,
            )
        effective_team_id = team_id or self._cfg("team_id")
        result = await self._post(
            "/api/v4/channels",
            body={
                "team_id": effective_team_id,
                "name": name.lower().replace(" ", "-"),
                "display_name": display_name,
                "type": channel_type,
            },
        )
        logger.info(
            "Mattermost channel created: id=%s name=%r team=%s",
            result.get("id"),
            name,
            effective_team_id,
        )
        return result

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        """Return channel metadata by ID."""
        self.require_capability("channel:read", "get_channel")
        return await self._get(f"/api/v4/channels/{channel_id}")

    # ------------------------------------------------------------------
    # Posts (messages)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        channel_id: str,
        message: str,
        props: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Post a message to a channel."""
        self.require_capability("message:post", "send_message")
        if not message.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Message text must not be empty",
                tool=self.name,
                operation="send_message",
                retryable=False,
            )
        body: dict[str, Any] = {"channel_id": channel_id, "message": message}
        if props:
            body["props"] = props
        result = await self._post("/api/v4/posts", body=body)
        logger.debug("Mattermost message sent: post_id=%s channel=%s", result.get("id"), channel_id)
        return result

    async def reply_to_message(self, post_id: str, message: str) -> dict[str, Any]:
        """
        Reply in a thread rooted at post_id.

        Mattermost threads use root_id to group replies. The adapter fetches
        the parent post to determine the channel so callers only need the post ID.
        """
        self.require_capability("message:post", "reply_to_message")
        if not message.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Reply message must not be empty",
                tool=self.name,
                operation="reply_to_message",
                retryable=False,
            )
        parent = await self._get(f"/api/v4/posts/{post_id}")
        channel_id = parent["channel_id"]
        # If the parent is itself a reply, use its root_id to keep the thread flat
        root_id = parent.get("root_id") or post_id
        return await self._post(
            "/api/v4/posts",
            body={"channel_id": channel_id, "message": message, "root_id": root_id},
        )

    async def get_posts(
        self,
        channel_id: str,
        page: int = 0,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """
        Return paginated posts for a channel.

        Returns the raw Mattermost posts response: {"order": [...], "posts": {...}}.
        """
        self.require_capability("message:read", "get_posts")
        return await self._get(
            f"/api/v4/channels/{channel_id}/posts",
            params={"page": page, "per_page": min(per_page, 200)},
        )

    async def search_posts(
        self,
        terms: str,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        """Search for posts matching the query terms in a team."""
        self.require_capability("message:search", "search_posts")
        if not terms.strip():
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Search terms must not be empty",
                tool=self.name,
                operation="search_posts",
                retryable=False,
            )
        effective_team_id = team_id or self._cfg("team_id")
        return await self._post(
            f"/api/v4/teams/{effective_team_id}/posts/search",
            body={"terms": terms, "is_or_search": False},
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """Fetch user profile by ID. Pass 'me' for the authenticated bot."""
        self.require_capability("user:read", "get_user")
        return await self._get(f"/api/v4/users/{user_id}")

    async def create_bot(
        self,
        username: str,
        display_name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """
        Create a bot account.

        Bots are the recommended identity for agents in Mattermost.
        Requires the authenticated user to have permission to create bots.
        """
        self.require_capability("user:read", "create_bot")
        result = await self._post(
            "/api/v4/bots",
            body={
                "username": username,
                "display_name": display_name,
                "description": description,
            },
        )
        logger.info(
            "Mattermost bot created: user_id=%s username=%r",
            result.get("user_id"),
            username,
        )
        return result

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    async def upload_file(self, channel_id: str, file_path: str) -> dict[str, Any]:
        """
        Upload a file to a channel and return the file info.

        The file must exist on the local filesystem. The adapter reads it
        and sends it as multipart form data.
        """
        self.require_capability("file:upload", "upload_file")
        assert self._http_client is not None
        try:
            with open(file_path, "rb") as fh:
                file_name = file_path.split("/")[-1]
                response = await self._http_client.post(
                    "/api/v4/files",
                    data={"channel_id": channel_id},
                    files={"files": (file_name, fh)},
                )
        except OSError as exc:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message=f"Cannot read file '{file_path}': {exc}",
                tool=self.name,
                operation="upload_file",
                retryable=False,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error uploading file: {exc}",
                tool=self.name,
                operation="upload_file",
                retryable=True,
            ) from exc
        self._raise_for_status(response, "upload_file")
        result = response.json()
        file_infos = result.get("file_infos", [])
        logger.info(
            "Mattermost file uploaded: channel=%s filename=%s",
            channel_id,
            file_name,
        )
        return file_infos[0] if file_infos else result

    # ------------------------------------------------------------------
    # Reactions
    # ------------------------------------------------------------------

    async def add_reaction(self, post_id: str, emoji: str) -> dict[str, Any]:
        """
        Add an emoji reaction to a post.

        `emoji` should be the emoji name without colons, e.g. "thumbsup".
        """
        self.require_capability("reaction:add", "add_reaction")
        # We need the bot's user ID to create the reaction
        me = await self.get_user("me")
        return await self._post(
            "/api/v4/reactions",
            body={
                "user_id": me["id"],
                "post_id": post_id,
                "emoji_name": emoji,
            },
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
        """
        Verify Mattermost outgoing webhook by comparing the token in the body.

        Mattermost embeds a shared token in the JSON body rather than using
        HMAC headers. We compare against the configured webhook_token.
        """
        try:
            body = json.loads(raw_body)
            return hmac.compare_digest(body.get("token", ""), secret)
        except (json.JSONDecodeError, TypeError):
            return False

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> NormalizedEvent:
        """
        Translate a raw Mattermost outgoing webhook payload into a NormalizedEvent.

        Mattermost sends: channel_id, user_id, text, trigger_word, post_id, team_id.
        A trigger_word being present indicates an @mention or slash command trigger.
        """
        channel_id = payload.get("channel_id", "")
        user_id = payload.get("user_id", "")
        text = payload.get("text", "")

        if not channel_id or not user_id:
            raise AdapterError(
                code=AdapterErrorCode.VALIDATION_ERROR,
                message="Mattermost webhook payload missing channel_id or user_id",
                tool=self.name,
                operation="handle_webhook",
                retryable=False,
            )

        # A trigger_word indicates the agent was @mentioned or used a slash command
        event_type = (
            "message.mentioned" if payload.get("trigger_word") else "message.posted"
        )

        return NormalizedEvent(
            source=EventSource.MATTERMOST,
            category=EventCategory.MESSAGE,
            event_type=event_type,
            actor_id=user_id,
            actor_type="human",
            resource_type="message",
            resource_external_id=payload.get("post_id"),
            data={
                "channel_id": channel_id,
                "text": text,
                "user_id": user_id,
                "team_id": payload.get("team_id"),
                "trigger_word": payload.get("trigger_word"),
                "post_id": payload.get("post_id"),
            },
            raw=payload,
        )

    # ------------------------------------------------------------------
    # Private HTTP helpers
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
                message=f"Timeout calling Mattermost GET {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Mattermost GET {path}: {exc}",
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
                message=f"Timeout calling Mattermost POST {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(
                code=AdapterErrorCode.CONNECTION_REFUSED,
                message=f"Network error calling Mattermost POST {path}: {exc}",
                tool=self.name,
                operation=path,
                retryable=True,
            ) from exc
        self._raise_for_status(response, f"POST {path}")
        return response.json()

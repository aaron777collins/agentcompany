"""
Tool definitions — maps adapter methods to LLM-callable tool descriptions.

Each function returns a handler that closes over a live adapter instance.
Call ``build_registry_for_company(adapter_registry, company_id)`` to produce
a ToolRegistry populated with every tool whose underlying adapter is currently
registered for that company.

Handler contract:
  - async function
  - receives a single ``arguments`` dict (the LLM's parsed tool call)
  - returns a JSON-serialisable value (dict, list, str, …)
  - raises AdapterError on failure — the decision loop catches this and feeds
    the error message back to the LLM as a tool result

Role mapping (architecture spec §Tool Permissions):
  - Plane tools:        "engineer", "manager", "qa"
  - Outline tools:      "writer", "researcher", "manager", "analyst"
  - Mattermost tools:   all roles (communication is universal)
  - Search tools:       all roles
"""

from __future__ import annotations

import logging
from typing import Any

from app.engine.tool_registry import AgentTool, ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plane — project management tools
# ---------------------------------------------------------------------------

def _make_create_issue_handler(plane_adapter: Any) -> Any:
    """Return an async handler that creates a Plane issue."""
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        project_id = arguments.get("project_id") or ""
        title = arguments.get("title") or ""
        if not project_id:
            raise ValueError("create_issue requires 'project_id'")
        if not title:
            raise ValueError("create_issue requires 'title'")
        return await plane_adapter.create_issue(
            project_id=project_id,
            title=title,
            description=arguments.get("description", ""),
            priority=arguments.get("priority", "medium"),
            assignee=arguments.get("assignee"),
            labels=arguments.get("labels"),
        )
    return _handler


def _make_update_issue_handler(plane_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        issue_id = arguments.get("issue_id") or ""
        if not issue_id:
            raise ValueError("update_issue requires 'issue_id'")
        # Pass remaining kwargs as field updates
        fields = {k: v for k, v in arguments.items() if k != "issue_id"}
        return await plane_adapter.update_issue(issue_id=issue_id, **fields)
    return _handler


def _make_get_issue_handler(plane_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        issue_id = arguments.get("issue_id") or ""
        if not issue_id:
            raise ValueError("get_issue requires 'issue_id'")
        return await plane_adapter.get_issue(issue_id=issue_id)
    return _handler


def _make_add_comment_handler(plane_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        issue_id = arguments.get("issue_id") or ""
        text = arguments.get("text") or ""
        if not issue_id:
            raise ValueError("add_comment requires 'issue_id'")
        if not text:
            raise ValueError("add_comment requires 'text'")
        return await plane_adapter.add_comment(issue_id=issue_id, text=text)
    return _handler


def _make_list_issues_handler(plane_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        project_id = arguments.get("project_id") or ""
        if not project_id:
            raise ValueError("list_issues requires 'project_id'")
        filters = {k: v for k, v in arguments.items() if k != "project_id"}
        return await plane_adapter.list_issues(
            project_id=project_id,
            filters=filters or None,
        )
    return _handler


# ---------------------------------------------------------------------------
# Outline — document search and authoring tools
# ---------------------------------------------------------------------------

def _make_search_documents_handler(outline_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = arguments.get("query") or ""
        if not query:
            raise ValueError("search_documents requires 'query'")
        limit = int(arguments.get("limit", 10))
        return await outline_adapter.search_documents(query=query, limit=limit)
    return _handler


def _make_create_document_handler(outline_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        title = arguments.get("title") or ""
        text = arguments.get("text") or ""
        if not title:
            raise ValueError("create_document requires 'title'")
        return await outline_adapter.create_document(
            title=title,
            text=text,
            collection_id=arguments.get("collection_id"),
            publish=bool(arguments.get("publish", True)),
        )
    return _handler


def _make_get_document_handler(outline_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        doc_id = arguments.get("doc_id") or ""
        if not doc_id:
            raise ValueError("get_document requires 'doc_id'")
        return await outline_adapter.get_document(doc_id=doc_id)
    return _handler


def _make_update_document_handler(outline_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        doc_id = arguments.get("doc_id") or ""
        if not doc_id:
            raise ValueError("update_document requires 'doc_id'")
        return await outline_adapter.update_document(
            doc_id=doc_id,
            title=arguments.get("title"),
            text=arguments.get("text"),
            append=bool(arguments.get("append", False)),
        )
    return _handler


# ---------------------------------------------------------------------------
# Mattermost — messaging tools
# ---------------------------------------------------------------------------

def _make_send_message_handler(mattermost_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        channel_id = arguments.get("channel_id") or ""
        message = arguments.get("message") or ""
        if not channel_id:
            raise ValueError("send_message requires 'channel_id'")
        if not message:
            raise ValueError("send_message requires 'message'")
        return await mattermost_adapter.send_message(
            channel_id=channel_id,
            message=message,
            props=arguments.get("props"),
        )
    return _handler


def _make_reply_to_message_handler(mattermost_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        post_id = arguments.get("post_id") or ""
        message = arguments.get("message") or ""
        if not post_id:
            raise ValueError("reply_to_message requires 'post_id'")
        if not message:
            raise ValueError("reply_to_message requires 'message'")
        return await mattermost_adapter.reply_to_message(
            post_id=post_id,
            message=message,
        )
    return _handler


def _make_search_posts_handler(mattermost_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        terms = arguments.get("terms") or ""
        if not terms:
            raise ValueError("search_posts requires 'terms'")
        return await mattermost_adapter.search_posts(
            terms=terms,
            team_id=arguments.get("team_id"),
        )
    return _handler


# ---------------------------------------------------------------------------
# Meilisearch — unified search
# ---------------------------------------------------------------------------

def _make_search_all_handler(meili_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query") or ""
        company_id = arguments.get("company_id") or ""
        if not query:
            raise ValueError("search_all requires 'query'")
        if not company_id:
            raise ValueError("search_all requires 'company_id' for tenant isolation")
        return await meili_adapter.search_all(
            query=query,
            company_id=company_id,
            filters=arguments.get("filters"),
            limit=int(arguments.get("limit", 20)),
        )
    return _handler


def _make_search_index_handler(meili_adapter: Any) -> Any:
    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        index = arguments.get("index") or ""
        query = arguments.get("query") or ""
        company_id = arguments.get("company_id") or ""
        if not index:
            raise ValueError("search requires 'index' (tickets|documents|messages)")
        if not query:
            raise ValueError("search requires 'query'")
        return await meili_adapter.search(
            index=index,
            query=query,
            filters=arguments.get("filters"),
            limit=int(arguments.get("limit", 20)),
            company_id=company_id or None,
        )
    return _handler


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

def build_registry_for_company(
    adapter_registry: Any,  # AdapterRegistry
    company_id: str,
) -> ToolRegistry:
    """
    Build a ToolRegistry populated with every tool whose adapter is
    currently registered for *company_id*.

    Tools whose adapter is absent are silently skipped — the agent will only
    see tools that are actually available.  This keeps the LLM prompt honest
    and avoids confusing tool-not-found errors at runtime.
    """
    if not company_id:
        raise ValueError("company_id must not be empty")

    registry = ToolRegistry()

    # ── Plane ──────────────────────────────────────────────────────────────
    plane = adapter_registry.get_optional(company_id, "plane")
    if plane is not None:
        registry.register(AgentTool(
            name="create_issue",
            description=(
                "Create a new issue (ticket) in a Plane project. "
                "Use this to track work items, bugs, or feature requests."
            ),
            parameters={
                "type": "object",
                "required": ["project_id", "title"],
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The Plane project ID to create the issue in.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short, descriptive title for the issue.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the issue (HTML supported).",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["urgent", "high", "medium", "low", "none"],
                        "description": "Issue priority. Defaults to 'medium'.",
                    },
                    "assignee": {
                        "type": "string",
                        "description": "User ID to assign the issue to.",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of label IDs to apply.",
                    },
                },
            },
            handler=_make_create_issue_handler(plane),
            required_roles=["engineer", "manager", "qa"],
        ))

        registry.register(AgentTool(
            name="update_issue",
            description=(
                "Update fields on an existing Plane issue. "
                "Pass only the fields you want to change."
            ),
            parameters={
                "type": "object",
                "required": ["issue_id"],
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "The ID of the issue to update.",
                    },
                    "name": {
                        "type": "string",
                        "description": "New title for the issue.",
                    },
                    "description_html": {
                        "type": "string",
                        "description": "New description (HTML).",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["urgent", "high", "medium", "low", "none"],
                    },
                    "state": {
                        "type": "string",
                        "description": "New state ID for the issue.",
                    },
                },
            },
            handler=_make_update_issue_handler(plane),
            required_roles=["engineer", "manager", "qa"],
        ))

        registry.register(AgentTool(
            name="get_issue",
            description="Retrieve full details for a single Plane issue by its ID.",
            parameters={
                "type": "object",
                "required": ["issue_id"],
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "The Plane issue ID.",
                    },
                },
            },
            handler=_make_get_issue_handler(plane),
            required_roles=["engineer", "manager", "qa"],
        ))

        registry.register(AgentTool(
            name="add_comment",
            description="Add a comment to a Plane issue.",
            parameters={
                "type": "object",
                "required": ["issue_id", "text"],
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "The Plane issue ID to comment on.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Comment text (HTML supported).",
                    },
                },
            },
            handler=_make_add_comment_handler(plane),
            required_roles=["engineer", "manager", "qa"],
        ))

        registry.register(AgentTool(
            name="list_issues",
            description=(
                "List issues in a Plane project. "
                "Optionally pass filter params (status, assignee, priority, etc.)."
            ),
            parameters={
                "type": "object",
                "required": ["project_id"],
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The Plane project ID.",
                    },
                    "state": {
                        "type": "string",
                        "description": "Filter by state ID.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["urgent", "high", "medium", "low", "none"],
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Filter by assignee user ID.",
                    },
                },
            },
            handler=_make_list_issues_handler(plane),
            required_roles=["engineer", "manager", "qa"],
        ))

    # ── Outline ────────────────────────────────────────────────────────────
    outline = adapter_registry.get_optional(company_id, "outline")
    if outline is not None:
        registry.register(AgentTool(
            name="search_documents",
            description=(
                "Full-text search across all Outline wiki documents. "
                "Returns documents with relevance ranking and a context snippet."
            ),
            parameters={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text to search for.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum number of results to return. Defaults to 10.",
                    },
                },
            },
            handler=_make_search_documents_handler(outline),
            required_roles=["writer", "researcher", "manager", "analyst"],
        ))

        registry.register(AgentTool(
            name="create_document",
            description=(
                "Create a new document in the Outline wiki. "
                "The document is published immediately by default."
            ),
            parameters={
                "type": "object",
                "required": ["title", "text"],
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Document title.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Document body in Markdown.",
                    },
                    "collection_id": {
                        "type": "string",
                        "description": (
                            "Collection (folder) to place the document in. "
                            "Uses the adapter default if omitted."
                        ),
                    },
                    "publish": {
                        "type": "boolean",
                        "description": "Publish immediately. Defaults to true.",
                    },
                },
            },
            handler=_make_create_document_handler(outline),
            required_roles=["writer", "researcher", "manager", "analyst"],
        ))

        registry.register(AgentTool(
            name="get_document",
            description="Retrieve the full content of an Outline document by its ID.",
            parameters={
                "type": "object",
                "required": ["doc_id"],
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "The Outline document UUID.",
                    },
                },
            },
            handler=_make_get_document_handler(outline),
            required_roles=["writer", "researcher", "manager", "analyst"],
        ))

        registry.register(AgentTool(
            name="update_document",
            description=(
                "Update an Outline document's title or body. "
                "Set append=true to add content rather than replace."
            ),
            parameters={
                "type": "object",
                "required": ["doc_id"],
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "The Outline document UUID.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title (leave unset to keep existing).",
                    },
                    "text": {
                        "type": "string",
                        "description": "New body text in Markdown.",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "If true, append text instead of replacing. Defaults to false.",
                    },
                },
            },
            handler=_make_update_document_handler(outline),
            required_roles=["writer", "researcher", "manager", "analyst"],
        ))

    # ── Mattermost ─────────────────────────────────────────────────────────
    mattermost = adapter_registry.get_optional(company_id, "mattermost")
    if mattermost is not None:
        registry.register(AgentTool(
            name="send_message",
            description=(
                "Post a message to a Mattermost channel. "
                "Use this to notify humans, share updates, or ask for input."
            ),
            parameters={
                "type": "object",
                "required": ["channel_id", "message"],
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The Mattermost channel ID to post to.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The message text (Markdown supported).",
                    },
                },
            },
            handler=_make_send_message_handler(mattermost),
            required_roles=[],  # Available to all roles
        ))

        registry.register(AgentTool(
            name="reply_to_message",
            description=(
                "Reply in a Mattermost thread. "
                "The reply is posted in the same thread as the referenced message."
            ),
            parameters={
                "type": "object",
                "required": ["post_id", "message"],
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "The ID of the post to reply to.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The reply text (Markdown supported).",
                    },
                },
            },
            handler=_make_reply_to_message_handler(mattermost),
            required_roles=[],
        ))

        registry.register(AgentTool(
            name="search_posts",
            description=(
                "Search Mattermost messages for specific terms. "
                "Returns matching posts with metadata."
            ),
            parameters={
                "type": "object",
                "required": ["terms"],
                "properties": {
                    "terms": {
                        "type": "string",
                        "description": "Search terms (supports Mattermost search syntax).",
                    },
                    "team_id": {
                        "type": "string",
                        "description": "Limit search to a specific team. Uses the default team if omitted.",
                    },
                },
            },
            handler=_make_search_posts_handler(mattermost),
            required_roles=[],
        ))

    # ── Meilisearch — unified cross-platform search ────────────────────────
    meili = adapter_registry.get_optional(company_id, "meilisearch")
    if meili is not None:
        registry.register(AgentTool(
            name="search_all",
            description=(
                "Search across all indexed content simultaneously — tickets (Plane), "
                "documents (Outline), and messages (Mattermost). "
                "Always scoped to your company's data. "
                "Use this when you need a broad answer and don't know which tool has it."
            ),
            parameters={
                "type": "object",
                "required": ["query", "company_id"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "company_id": {
                        "type": "string",
                        "description": "Your company ID (required for tenant isolation).",
                    },
                    "filters": {
                        "type": "string",
                        "description": (
                            "Optional Meilisearch filter expression "
                            "e.g. \"status = 'open'\". "
                            "company_id is always applied automatically."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "Results per index. Defaults to 20.",
                    },
                },
            },
            handler=_make_search_all_handler(meili),
            required_roles=[],
        ))

        registry.register(AgentTool(
            name="search",
            description=(
                "Search within a specific index: 'tickets', 'documents', or 'messages'. "
                "More targeted than search_all when you know which content type to query."
            ),
            parameters={
                "type": "object",
                "required": ["index", "query"],
                "properties": {
                    "index": {
                        "type": "string",
                        "enum": ["tickets", "documents", "messages"],
                        "description": "The index to search.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "company_id": {
                        "type": "string",
                        "description": "Your company ID (recommended for tenant isolation).",
                    },
                    "filters": {
                        "type": "string",
                        "description": "Optional Meilisearch filter expression.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "Maximum results. Defaults to 20.",
                    },
                },
            },
            handler=_make_search_index_handler(meili),
            required_roles=[],
        ))

    logger.debug(
        "Built tool registry for company %s: %d tools registered",
        company_id,
        len(registry),
    )
    return registry

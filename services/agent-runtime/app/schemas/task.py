"""Pydantic schemas for Task resources."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50000)
    company_id: str
    # assigned_to is optional at creation — can be assigned later
    assigned_to: str | None = None
    assigned_type: Literal["agent", "human"] | None = None
    priority: Literal["urgent", "high", "medium", "low"] = "medium"
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    parent_task_id: str | None = None
    # Whether to create a mirrored issue in Plane
    sync_to_plane: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50000)
    # Values must match the frontend kanban board column identifiers.
    # "open" and "blocked" were removed; "backlog" and "todo" were added.
    status: Literal["backlog", "todo", "in_progress", "review", "done", "cancelled"] | None = (
        None
    )
    priority: Literal["urgent", "high", "medium", "low"] | None = None
    assigned_to: str | None = None
    assigned_type: Literal["agent", "human"] | None = None
    due_at: datetime | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TaskAssign(BaseModel):
    assignee_id: str
    assignee_type: Literal["agent", "human"]


class TaskRead(BaseModel):
    id: str
    org_id: str
    company_id: str
    title: str
    description: str | None
    status: str
    priority: str
    assigned_to: str | None
    assigned_type: str | None
    created_by: str
    parent_task_id: str | None
    external_refs: dict[str, Any]
    metadata_: dict[str, Any] = Field(alias="metadata_")
    tags: list[str]
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True, "populate_by_name": True}

"""Pydantic schemas for Role resources."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    company_id: str
    description: str | None = Field(default=None, max_length=5000)
    level: int = Field(default=0, ge=0)
    reports_to_role_id: str | None = None
    permissions: list[str] = Field(default_factory=list)
    tool_access: dict[str, Any] = Field(default_factory=dict)
    max_headcount: int = Field(default=1, ge=1)
    headcount_type: str = Field(default="agent", pattern="^(agent|human|mixed)$")


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    level: int | None = Field(default=None, ge=0)
    reports_to_role_id: str | None = None
    permissions: list[str] | None = None
    tool_access: dict[str, Any] | None = None
    max_headcount: int | None = Field(default=None, ge=1)
    headcount_type: str | None = Field(
        default=None, pattern="^(agent|human|mixed)$"
    )


class RoleRead(BaseModel):
    id: str
    org_id: str
    company_id: str
    name: str
    slug: str
    description: str | None
    level: int
    reports_to_role_id: str | None
    permissions: list[str]
    tool_access: dict[str, Any]
    max_headcount: int
    headcount_type: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}

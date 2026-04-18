"""Pydantic schemas for Approval resources."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalRead(BaseModel):
    id: str
    org_id: str
    company_id: str
    agent_id: str
    task_id: str | None
    action_summary: str
    action_payload: dict[str, Any]
    status: Literal["pending", "approved", "denied"]
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    """Request body for approve/deny actions."""

    note: str | None = Field(default=None, max_length=2000)

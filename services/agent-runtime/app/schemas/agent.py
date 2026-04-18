"""Pydantic schemas for Agent resources."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    model: str = "claude-sonnet-4-5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=200000)

    model_config = {"extra": "allow"}


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    company_id: str
    role_id: str | None = None
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    system_prompt: str | None = Field(default=None, max_length=100000)
    capabilities: list[str] = Field(default_factory=list)
    tool_permissions: dict[str, Any] = Field(default_factory=dict)
    token_budget_daily: int | None = Field(default=None, ge=1)
    token_budget_monthly: int | None = Field(default=None, ge=1)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role_id: str | None = None
    llm_config: LLMConfig | None = None
    system_prompt: str | None = Field(default=None, max_length=100000)
    capabilities: list[str] | None = None
    tool_permissions: dict[str, Any] | None = None
    token_budget_daily: int | None = Field(default=None, ge=1)
    token_budget_monthly: int | None = Field(default=None, ge=1)


class AgentStopRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    drain: bool = True  # finish current task before stopping


class AgentTriggerRequest(BaseModel):
    """Payload for manually triggering an agent run."""

    task_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high"] = "normal"


class AgentRead(BaseModel):
    id: str
    org_id: str
    company_id: str
    role_id: str | None
    name: str
    slug: str
    status: str
    keycloak_client_id: str | None
    llm_config: dict[str, Any]
    system_prompt_ref: str | None
    capabilities: list[str]
    tool_permissions: dict[str, Any]
    token_budget_daily: int | None
    token_budget_monthly: int | None
    version: int
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime | None
    deleted_at: datetime | None

    model_config = {"from_attributes": True}

"""Prompt templates and system prompts for agent roles."""

from .system_prompts import (
    ROLE_PROMPT_REGISTRY,
    ceo_prompt,
    cfo_prompt,
    cto_prompt,
    developer_prompt,
    designer_prompt,
    pm_prompt,
    qa_prompt,
    get_system_prompt,
)
from .templates import (
    code_review_prompt,
    delegation_prompt,
    escalation_prompt,
    standup_report_prompt,
    status_update_prompt,
    task_analysis_prompt,
)

__all__ = [
    "ROLE_PROMPT_REGISTRY",
    "get_system_prompt",
    "ceo_prompt",
    "cto_prompt",
    "cfo_prompt",
    "pm_prompt",
    "developer_prompt",
    "designer_prompt",
    "qa_prompt",
    "task_analysis_prompt",
    "escalation_prompt",
    "status_update_prompt",
    "code_review_prompt",
    "standup_report_prompt",
    "delegation_prompt",
]

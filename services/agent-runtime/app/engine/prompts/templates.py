"""
Prompt templates for common agent actions.

These templates produce consistently-structured prompts for recurring
decision-loop scenarios. Using templates rather than ad-hoc string
formatting ensures:
  - Consistent structure across runs (easier to parse agent outputs)
  - Explicit inclusion of required context (reduces hallucination)
  - Easy unit testing of prompt construction

All functions return a single string ready to be used as the "content"
field of a user message in the conversation.
"""

from __future__ import annotations

from typing import Any, Optional


def task_analysis_prompt(
    task_title: str,
    task_description: str,
    task_id: str,
    assignee_name: str,
    due_date: Optional[str] = None,
    context_documents: Optional[list[str]] = None,
) -> str:
    """
    Prompt an agent to analyze a task and plan its approach.

    Used at the start of a task-triggered run to get the agent oriented
    before it starts calling tools.
    """
    if not task_title:
        raise ValueError("task_title must not be empty")
    if not task_id:
        raise ValueError("task_id must not be empty")

    lines = [
        f"## Task: {task_title}",
        f"**Task ID**: {task_id}",
        f"**Assigned to**: {assignee_name}",
    ]
    if due_date:
        lines.append(f"**Due**: {due_date}")
    lines.append("")

    lines.append("### Description")
    lines.append(task_description or "No description provided.")
    lines.append("")

    if context_documents:
        lines.append("### Relevant Documents")
        for doc in context_documents:
            lines.append(f"- {doc}")
        lines.append("")

    lines += [
        "### Your Task",
        "1. Review the task description and any relevant context.",
        "2. Identify what you need to do and in what order.",
        "3. Begin work using the tools available to you.",
        "4. Update the task status as you progress.",
        "5. When complete, summarize what you accomplished.",
    ]

    return "\n".join(lines)


def escalation_prompt(
    reason: str,
    context: dict[str, Any],
    decision_options: list[str],
    from_agent_name: str,
    to_agent_name: str,
    original_task_id: Optional[str] = None,
) -> str:
    """
    Prompt an agent to handle an escalation from a subordinate agent.

    The receiving agent (manager) uses this to understand what decision
    is needed and what options are available.
    """
    if not reason:
        raise ValueError("reason must not be empty")
    if not decision_options:
        raise ValueError("decision_options must not be empty")

    lines = [
        f"## Escalation from {from_agent_name}",
        "",
        f"**Reason**: {reason}",
    ]
    if original_task_id:
        lines.append(f"**Original Task**: {original_task_id}")
    lines.append("")

    lines.append("### Context")
    for key, value in context.items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")

    lines.append("### Options for {to_agent_name} to Consider".replace("{to_agent_name}", to_agent_name))
    for i, option in enumerate(decision_options, 1):
        lines.append(f"{i}. {option}")
    lines.append("")

    lines += [
        "### Required Action",
        "Review the escalation, choose one of the options above (or propose an alternative),",
        "and communicate your decision back to " + from_agent_name + " via chat.",
        "If this requires human judgment, escalate further up the chain.",
    ]

    return "\n".join(lines)


def status_update_prompt(
    task_id: str,
    task_title: str,
    current_status: str,
    work_completed: list[str],
    blockers: Optional[list[str]] = None,
    next_steps: Optional[list[str]] = None,
    percent_complete: Optional[int] = None,
) -> str:
    """
    Prompt an agent to post a structured status update to a task.

    Used when an agent completes a work session but the task is not yet done.
    """
    if not task_id:
        raise ValueError("task_id must not be empty")

    lines = [
        f"## Status Update for Task {task_id}: {task_title}",
        f"**Current Status**: {current_status}",
    ]
    if percent_complete is not None:
        if not 0 <= percent_complete <= 100:
            raise ValueError("percent_complete must be between 0 and 100")
        lines.append(f"**Progress**: {percent_complete}%")
    lines.append("")

    lines.append("### Completed This Session")
    if work_completed:
        for item in work_completed:
            lines.append(f"- {item}")
    else:
        lines.append("- No items completed this session.")
    lines.append("")

    if blockers:
        lines.append("### Blockers")
        for blocker in blockers:
            lines.append(f"- {blocker}")
        lines.append("")

    if next_steps:
        lines.append("### Next Steps")
        for step in next_steps:
            lines.append(f"- {step}")
        lines.append("")

    lines += [
        "Post this status update as a comment on the task using ProjectManagementTool.",
    ]

    return "\n".join(lines)


def code_review_prompt(
    pr_title: str,
    pr_id: str,
    diff_summary: str,
    review_criteria: Optional[list[str]] = None,
) -> str:
    """
    Prompt a CTO or senior developer agent to review a code change.
    """
    if not pr_title:
        raise ValueError("pr_title must not be empty")

    default_criteria = [
        "Correctness: does the code do what the PR description says?",
        "Test coverage: are there tests for the new behavior?",
        "Security: are there any obvious vulnerabilities (injection, auth bypass, data exposure)?",
        "Performance: are there obvious inefficiencies for large inputs?",
        "Readability: is the code clear enough to maintain without the author present?",
    ]
    criteria = review_criteria or default_criteria

    lines = [
        f"## Code Review: {pr_title}",
        f"**PR ID**: {pr_id}",
        "",
        "### Changes Summary",
        diff_summary,
        "",
        "### Review Criteria",
    ]
    for criterion in criteria:
        lines.append(f"- {criterion}")
    lines.append("")

    lines += [
        "### Instructions",
        "Review the changes against each criterion above.",
        "Post your review as a comment on the PR task.",
        "Mark the task as 'approved' or 'changes_requested' accordingly.",
        "Be specific: include line references and concrete suggestions.",
    ]

    return "\n".join(lines)


def standup_report_prompt(
    agent_name: str,
    role: str,
    period: str,
    tasks: list[dict[str, Any]],
    blockers: Optional[list[str]] = None,
) -> str:
    """
    Prompt an agent to generate a standup/status report for a time period.

    tasks: list of {"id": str, "title": str, "status": str, "work_done": str}
    """
    if not agent_name:
        raise ValueError("agent_name must not be empty")
    if not period:
        raise ValueError("period must not be empty")

    lines = [
        f"## Standup Report: {agent_name} ({role})",
        f"**Period**: {period}",
        "",
        "### Tasks",
    ]

    if tasks:
        for task in tasks:
            status = task.get("status", "unknown")
            lines.append(f"- [{status}] **{task.get('title', 'Untitled')}** ({task.get('id', '')})")
            work = task.get("work_done", "")
            if work:
                lines.append(f"  - {work}")
    else:
        lines.append("- No tasks to report.")
    lines.append("")

    if blockers:
        lines.append("### Blockers")
        for blocker in blockers:
            lines.append(f"- {blocker}")
        lines.append("")

    lines += [
        "### Instructions",
        "Write this standup report and post it to the team channel using ChatTool.",
        "Be concise — the report should take less than 2 minutes to read.",
    ]

    return "\n".join(lines)


def delegation_prompt(
    task_title: str,
    task_description: str,
    delegate_to_role: str,
    delegate_to_agent_name: str,
    priority: str = "medium",
    due_date: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """
    Prompt a manager agent to create and assign a delegated task.
    """
    if not task_title:
        raise ValueError("task_title must not be empty")
    if not delegate_to_role:
        raise ValueError("delegate_to_role must not be empty")

    lines = [
        f"## Delegate Task to {delegate_to_agent_name} ({delegate_to_role})",
        "",
        f"**Task**: {task_title}",
        f"**Priority**: {priority}",
    ]
    if due_date:
        lines.append(f"**Due**: {due_date}")
    lines.append("")

    lines.append("### Task Description")
    lines.append(task_description)
    lines.append("")

    if context:
        lines.append("### Context for the Assignee")
        lines.append(context)
        lines.append("")

    lines += [
        "### Instructions",
        f"1. Create this task in the project management system using ProjectManagementTool.",
        f"2. Assign it to {delegate_to_agent_name}.",
        f"3. Notify {delegate_to_agent_name} via ChatTool with a brief message linking the task.",
        "4. Set a reminder to follow up if the task is not updated within 24 hours.",
    ]

    return "\n".join(lines)

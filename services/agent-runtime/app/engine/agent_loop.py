"""
Main agent decision loop.

Implements the Observe -> Think -> Act -> Reflect cycle described in
agent-framework.md. One instance of this class handles a single agent run.

The loop is bounded by max_steps to prevent runaway token consumption.
When max_steps is reached the agent posts a progress summary and returns
with outcome="max_steps" so a human or manager agent can review.

Key invariants:
  1. Budget is checked before EVERY LLM call, not just at run start.
  2. Tool permission checks happen in the tool executor, not here.
  3. Context compaction happens before every LLM call.
  4. The agent's state machine is updated on start and on every terminal exit.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from .context_manager import ContextWindowManager
from .cost_tracker import BudgetStatus, CostTracker
from .memory import AgentMemory, MemoryEntry
from .state_machine import AgentState, AgentStateMachine, InvalidTransitionError

if TYPE_CHECKING:
    from .llm.base import BaseLLMAdapter
    from .llm.types import LLMResponse, ToolDefinition

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 10


@dataclass
class AgentContext:
    """
    Working memory for a single agent run.

    Held in memory for the duration of one run and written to the DB on
    completion. Not shared between runs — each trigger creates a fresh context.
    """

    run_id: str
    agent_id: str
    trigger: dict[str, Any]
    messages: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    step_count: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LoopResult:
    """
    The outcome of a single agent run.

    Persisted to agent_runs and surfaced in the management API.
    """

    run_id: str
    agent_id: str
    outcome: str               # "completed" | "max_steps" | "budget_exceeded" | "error"
    steps_taken: int
    tokens_used: int
    cost_usd: float
    final_message: Optional[str] = None
    error: Optional[str] = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AgentDecisionLoop:
    """
    Orchestrates the observe-think-act-reflect loop for one agent run.

    Dependencies are injected so each can be independently tested.
    """

    def __init__(
        self,
        llm_adapter: "BaseLLMAdapter",
        tool_executor: Any,         # ToolSandbox or compatible executor
        memory: AgentMemory,
        cost_tracker: CostTracker,
        state_machine: AgentStateMachine,
        context_manager: ContextWindowManager,
        max_steps: int = MAX_STEPS_DEFAULT,
    ) -> None:
        if max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {max_steps}")

        self._llm = llm_adapter
        self._tools = tool_executor
        self._memory = memory
        self._cost_tracker = cost_tracker
        self._state_machine = state_machine
        self._ctx_manager = context_manager
        self._max_steps = max_steps

    async def run(
        self,
        agent_id: str,
        company_id: str,
        system_prompt: str,
        available_tools: list["ToolDefinition"],
        trigger: dict[str, Any],
        run_id: Optional[str] = None,
    ) -> LoopResult:
        """
        Execute one complete agent run for a given trigger.

        Returns a LoopResult regardless of outcome — never raises to the caller.
        All exceptions are caught, logged, and reflected in the result.
        """
        rid = run_id or f"run_{uuid.uuid4().hex}"
        context = AgentContext(
            run_id=rid,
            agent_id=agent_id,
            trigger=trigger,
        )

        # Attach run context to log records for easy filtering
        run_log = logging.LoggerAdapter(
            logger,
            {"agent_id": agent_id, "run_id": rid, "company_id": company_id},
        )

        # ----------------------------------------------------------------
        # Phase 1: OBSERVE — retrieve relevant memories, build initial context
        # ----------------------------------------------------------------
        try:
            memories = await self._memory.search(
                query=self._trigger_summary(trigger),
                top_k=5,
            )
        except Exception:
            run_log.warning("Memory retrieval failed (non-fatal); proceeding without memories", exc_info=True)
            memories = []

        context.messages = self._build_initial_messages(trigger, memories)

        # ----------------------------------------------------------------
        # Transition to RUNNING
        # ----------------------------------------------------------------
        try:
            transition = self._state_machine.transition(
                to_state=AgentState.RUNNING,
                reason="loop_start",
                triggered_by=trigger.get("trigger_id"),
            )
            run_log.info("Decision loop started: state=%s", AgentState.RUNNING.value)
        except InvalidTransitionError as exc:
            run_log.warning("Cannot start loop (bad state): %s", exc)
            return LoopResult(
                run_id=rid,
                agent_id=agent_id,
                outcome="error",
                steps_taken=0,
                tokens_used=0,
                cost_usd=0.0,
                error=str(exc),
            )

        # ----------------------------------------------------------------
        # Main loop: THINK -> ACT -> REFLECT
        # ----------------------------------------------------------------
        try:
            return await self._loop(
                context=context,
                system_prompt=system_prompt,
                available_tools=available_tools,
                run_log=run_log,
            )
        except Exception as exc:
            run_log.exception("Unhandled exception in decision loop")
            # Attempt to move to ACTIVE so the agent can be retriggered
            try:
                self._state_machine.transition(
                    to_state=AgentState.ACTIVE,
                    reason="error_recovery",
                )
            except InvalidTransitionError:
                pass
            return LoopResult(
                run_id=rid,
                agent_id=agent_id,
                outcome="error",
                steps_taken=context.step_count,
                tokens_used=context.tokens_used,
                cost_usd=context.cost_usd,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _loop(
        self,
        context: AgentContext,
        system_prompt: str,
        available_tools: list["ToolDefinition"],
        run_log: logging.LoggerAdapter,
    ) -> LoopResult:
        """Inner loop body extracted to keep run() focused on lifecycle."""

        while context.step_count < self._max_steps:
            context.step_count += 1

            # Budget check — mandatory before every LLM call
            budget: BudgetStatus = await self._cost_tracker.check(estimated_tokens=500)
            if not budget.allowed:
                run_log.warning(
                    "Budget exceeded at step %d: reason=%s remaining_daily=%d",
                    context.step_count,
                    budget.reason,
                    budget.remaining_daily_tokens,
                )
                try:
                    self._state_machine.transition(
                        to_state=AgentState.PAUSED,
                        reason=f"budget_exceeded:{budget.reason}",
                    )
                except InvalidTransitionError:
                    pass
                return LoopResult(
                    run_id=context.run_id,
                    agent_id=context.agent_id,
                    outcome="budget_exceeded",
                    steps_taken=context.step_count,
                    tokens_used=context.tokens_used,
                    cost_usd=context.cost_usd,
                    final_message=f"Paused: {budget.reason}. "
                                  f"Remaining daily tokens: {budget.remaining_daily_tokens}",
                )

            # Compact context window if needed
            context.messages = await self._ctx_manager.maybe_compact(
                messages=context.messages,
                system=system_prompt,
                agent_id=context.agent_id,
                run_id=context.run_id,
            )

            # THINK — ask the LLM
            run_log.debug("Step %d/%d: calling LLM", context.step_count, self._max_steps)
            llm_response: "LLMResponse" = await self._llm.complete(
                messages=context.messages,
                system=system_prompt,
                tools=available_tools or None,
            )

            # Record token usage immediately after the call
            context.tokens_used += llm_response.tokens_used
            context.cost_usd += llm_response.cost_usd

            await self._cost_tracker.record_usage(
                input_tokens=llm_response.input_tokens,
                output_tokens=llm_response.output_tokens,
                cost_usd=llm_response.cost_usd,
                model=llm_response.model,
                provider=self._llm.name(),
                run_id=context.run_id,
            )

            # Append the assistant's response to the conversation
            context.messages.append({
                "role": "assistant",
                "content": llm_response.content,
            })

            # ACT — execute tool calls if the LLM requested any
            if llm_response.tool_calls:
                for tool_call in llm_response.tool_calls:
                    run_log.debug("Executing tool: %s", tool_call.name)
                    result = await self._tools.execute(
                        agent_id=context.agent_id,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        call_id=tool_call.id,
                    )
                    context.tool_results.append({
                        "tool_name": tool_call.name,
                        "tool_call_id": tool_call.id,
                        "output": result.output,
                        "success": result.success,
                    })
                    # Append tool result so the LLM has it in next turn
                    context.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.output,
                    })
                # Loop back to THINK with tool results appended
                continue

            # No tool calls — the LLM produced a final answer.
            # REFLECT — store what we learned, update state.
            await self._reflect(context, llm_response.content, run_log)

            try:
                self._state_machine.transition(
                    to_state=AgentState.ACTIVE,
                    reason="task_complete",
                )
            except InvalidTransitionError as exc:
                run_log.warning("Could not transition to ACTIVE after completion: %s", exc)

            run_log.info(
                "Run complete: steps=%d tokens=%d cost_usd=%.6f",
                context.step_count,
                context.tokens_used,
                context.cost_usd,
            )
            return LoopResult(
                run_id=context.run_id,
                agent_id=context.agent_id,
                outcome="completed",
                steps_taken=context.step_count,
                tokens_used=context.tokens_used,
                cost_usd=context.cost_usd,
                final_message=llm_response.content,
            )

        # Exited loop without a final answer — max steps reached
        run_log.warning(
            "Max steps (%d) reached without final answer", self._max_steps
        )
        await self._reflect(context, "Max steps reached without resolution.", run_log)

        try:
            self._state_machine.transition(
                to_state=AgentState.ACTIVE,
                reason="max_steps_reached",
            )
        except InvalidTransitionError as exc:
            run_log.warning("Could not transition to ACTIVE after max_steps: %s", exc)

        return LoopResult(
            run_id=context.run_id,
            agent_id=context.agent_id,
            outcome="max_steps",
            steps_taken=context.step_count,
            tokens_used=context.tokens_used,
            cost_usd=context.cost_usd,
            final_message="Max steps reached. Review run history for progress.",
        )

    async def _reflect(
        self,
        context: AgentContext,
        final_content: str,
        run_log: logging.LoggerAdapter,
    ) -> None:
        """
        Store a summary of this run in long-term memory.

        Failing here must not fail the run — memory writes are best-effort.
        """
        try:
            trigger_type = context.trigger.get("type", "unknown")
            summary = (
                f"Run {context.run_id} (trigger={trigger_type}): "
                f"{final_content[:500]}"
            )
            await self._memory.store(
                content=summary,
                metadata={
                    "run_id": context.run_id,
                    "trigger_type": trigger_type,
                    "steps": context.step_count,
                    "tokens": context.tokens_used,
                    "cost_usd": context.cost_usd,
                },
                category="task_summary",
                memory_id=f"run_{context.run_id}",
            )
        except Exception:
            run_log.warning("Failed to store run memory (non-fatal)", exc_info=True)

    def _build_initial_messages(
        self,
        trigger: dict[str, Any],
        memories: list[MemoryEntry],
    ) -> list[dict]:
        """
        Construct the first message for the conversation.

        Relevant memories are injected here so the LLM has historical context
        before it starts working on the current task.
        """
        memory_block = ""
        if memories:
            memory_lines = "\n".join(f"- {m.content}" for m in memories)
            memory_block = f"\n## Relevant Memory\n{memory_lines}\n"

        payload = trigger.get("payload", {})
        task_description = ""
        if isinstance(payload, dict):
            title = payload.get("title", "")
            description = payload.get("description", "")
            task_description = f"{title}\n{description}".strip()
        elif isinstance(payload, str):
            task_description = payload

        return [
            {
                "role": "user",
                "content": (
                    f"{memory_block}"
                    f"\n## Current Task\n{task_description or 'No task description provided.'}"
                ),
            }
        ]

    def _trigger_summary(self, trigger: dict[str, Any]) -> str:
        """Produce a short text summary of the trigger for memory search."""
        payload = trigger.get("payload", {})
        if isinstance(payload, dict):
            parts = [
                trigger.get("type", ""),
                payload.get("title", ""),
                payload.get("description", ""),
            ]
            return " ".join(p for p in parts if p)
        return trigger.get("type", "unknown trigger")

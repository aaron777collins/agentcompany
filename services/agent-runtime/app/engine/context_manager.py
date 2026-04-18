"""
LLM context window management.

As a conversation grows, the context window fills up. This module manages
that transparently so the decision loop never needs to worry about token limits.

Compaction strategy (from architecture spec):
  - Check before every LLM call
  - Compact when > 80% full
  - Summarize the oldest 50% of messages using the same adapter (cheap model
    settings: low max_tokens, no tools)
  - Always preserve the last 4 messages intact for conversational coherence
  - Archive the original messages to long-term memory before discarding

80% threshold chosen to leave room for the response tokens plus overhead.
50% target gives the conversation room to grow before the next compaction.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .llm.base import BaseLLMAdapter
    from .memory import AgentMemory

logger = logging.getLogger(__name__)

# These constants match the architecture spec exactly.
# Changing them affects token cost and context quality — update the spec too.
COMPACTION_THRESHOLD = 0.80  # Compact when context exceeds this fraction
COMPACTION_TARGET = 0.50     # Aim to compact down to this fraction
MIN_MESSAGES_TO_KEEP = 4     # Always preserve the most recent N messages


@dataclass
class CompactionResult:
    """Metadata about a compaction operation, useful for logging and metrics."""

    original_message_count: int
    compacted_message_count: int
    tokens_before: int
    tokens_after: int
    summary: str


class ContextWindowManager:
    """
    Manages context window size for a single agent run.

    Call maybe_compact() before every LLM call in the decision loop.
    It is a no-op when the context is below the threshold, so it's safe
    to call unconditionally.
    """

    def __init__(
        self,
        adapter: "BaseLLMAdapter",
        memory: "AgentMemory",
    ) -> None:
        self._adapter = adapter
        self._memory = memory

    async def maybe_compact(
        self,
        messages: list[dict],
        system: str,
        agent_id: str,
        run_id: str,
    ) -> list[dict]:
        """
        Check token usage and compact if needed.

        Returns the messages list unchanged if no compaction was needed,
        or a compacted version otherwise. The caller must use the returned
        list for all subsequent LLM calls — do not retain a reference to
        the original.
        """
        if not messages:
            return messages

        current_tokens = self._adapter.count_tokens(messages, system)
        max_tokens = self._adapter.max_context_tokens()
        threshold = int(max_tokens * COMPACTION_THRESHOLD)

        if current_tokens <= threshold:
            return messages

        logger.info(
            "Context window compaction triggered for agent=%s run=%s "
            "(current=%d threshold=%d max=%d)",
            agent_id,
            run_id,
            current_tokens,
            threshold,
            max_tokens,
        )

        return await self._compact(
            messages=messages,
            system=system,
            agent_id=agent_id,
            run_id=run_id,
            current_tokens=current_tokens,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _compact(
        self,
        messages: list[dict],
        system: str,
        agent_id: str,
        run_id: str,
        current_tokens: int,
        max_tokens: int,
    ) -> list[dict]:
        # Preserve the last MIN_MESSAGES_TO_KEEP messages for coherence.
        # Everything older gets summarized.
        split_point = max(1, len(messages) - MIN_MESSAGES_TO_KEEP)
        to_summarize = messages[:split_point]
        to_keep = messages[split_point:]

        # Archive the raw messages to long-term memory before discarding them.
        # This ensures nothing is truly lost — just compressed.
        await self._archive_to_memory(to_summarize, agent_id, run_id, len(messages))

        summary = await self._summarize(to_summarize)

        # Replace summarized messages with a single context summary block
        summary_message: dict = {
            "role": "user",
            "content": f"[Compressed context from earlier in this conversation]\n\n{summary}",
        }
        compacted = [summary_message, *to_keep]

        tokens_after = self._adapter.count_tokens(compacted, system)
        logger.info(
            "Compaction complete for agent=%s run=%s: "
            "messages %d->%d tokens %d->%d",
            agent_id,
            run_id,
            len(messages),
            len(compacted),
            current_tokens,
            tokens_after,
        )

        return compacted

    async def _summarize(self, messages: list[dict]) -> str:
        """
        Ask the LLM to produce a compact summary of a message list.

        Uses the same adapter as the decision loop but with a small max_tokens
        budget since we only need a brief summary, not a full response.
        """
        # Build a simple transcript for the summarization prompt
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                # Structured content blocks
                content = " ".join(
                    block.get("content", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            lines.append(f"{role}: {content}")

        transcript = "\n".join(lines)
        summarization_prompt = (
            "Summarize the following conversation excerpt in 3–5 sentences. "
            "Preserve: key decisions made, action items, important facts, and "
            "current task status. Omit pleasantries and redundant information.\n\n"
            f"{transcript}"
        )

        response = await self._adapter.complete(
            messages=[{"role": "user", "content": summarization_prompt}],
            system="You are a concise summarizer. Output only the summary, with no preamble.",
            max_tokens=500,
            temperature=0.1,
        )
        return response.content

    async def _archive_to_memory(
        self,
        messages: list[dict],
        agent_id: str,
        run_id: str,
        total_message_count: int,
    ) -> None:
        """
        Store original messages in long-term memory before they are dropped.

        This is a best-effort operation — a failure here must not abort the
        compaction or the run.
        """
        try:
            lines = []
            for msg in messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = str(content)
                lines.append(f"{role}: {content}")

            full_text = "\n".join(lines)
            # Truncate to avoid storing enormous blobs in memory
            archived_text = full_text[:4000]

            await self._memory.store(
                content=archived_text,
                metadata={
                    "run_id": run_id,
                    "compacted": True,
                    "message_count": len(messages),
                    "total_messages_at_compact": total_message_count,
                },
                category="conversation",
                memory_id=f"compact_{run_id}_{total_message_count}_{uuid.uuid4().hex[:8]}",
            )
        except Exception:
            # Non-fatal — compaction must still proceed even if archiving fails
            logger.warning(
                "Failed to archive messages to memory for agent=%s run=%s (non-fatal)",
                agent_id,
                run_id,
                exc_info=True,
            )

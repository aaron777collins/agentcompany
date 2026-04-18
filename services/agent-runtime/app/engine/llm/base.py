"""
Abstract LLM adapter interface.

All provider-specific adapters inherit from BaseLLMAdapter. The decision loop
only ever holds a reference to this base class, so providers are swappable
at runtime without touching any agent logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import LLMChunk, LLMResponse, ToolDefinition


class BaseLLMAdapter(ABC):
    """
    Defines the contract every LLM provider adapter must fulfill.

    Thread-safety requirement: multiple coroutines may call the same adapter
    instance concurrently. Implementations must not share mutable state across
    calls (e.g. do not cache partial responses in instance variables).
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """
        Send a completion request and return a full response.

        messages format follows the internal representation:
          [{"role": "user"|"assistant"|"tool", "content": str, ...}, ...]

        Tool messages must include "tool_call_id" for the adapter to route
        results back to the correct tool call in providers that require it
        (e.g. Anthropic's tool_result content blocks).
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        """
        Send a streaming completion request.

        Yields LLMChunk objects until one with is_final=True is produced.
        Used by the web UI "watch agent think" feature, not the decision loop itself.
        The decision loop uses complete() because tool calls require a full response.
        """
        ...

    @abstractmethod
    def count_tokens(self, messages: list[dict], system: str = "") -> int:
        """
        Estimate token count for the given messages without an API call.

        Used by the context window manager to decide whether compaction is needed.
        Accuracy matters more than speed; imprecise estimates cause premature
        compaction (wasted cost) or missed compaction (context overflow errors).
        """
        ...

    @abstractmethod
    def max_context_tokens(self) -> int:
        """Return the maximum context window size for the configured model."""
        ...

    @abstractmethod
    def name(self) -> str:
        """
        Return the adapter identifier used in agent config and the registry.

        Examples: 'anthropic_claude', 'openai_gpt', 'ollama'
        """
        ...

    def cost_per_token(self) -> tuple[float, float]:
        """
        Return (input_cost_per_token, output_cost_per_token) in USD.

        Default implementation returns (0, 0). Override in adapters that have
        per-token pricing to enable pre-run cost estimation.
        """
        return (0.0, 0.0)

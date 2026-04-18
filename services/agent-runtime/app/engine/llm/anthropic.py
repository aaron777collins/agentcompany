"""
Anthropic Claude adapter.

Uses Claude's native messages API with tool_use content blocks.
Anthropic's tool calling format differs from OpenAI's function calling format:
  - Tool results are sent as "user" role messages with tool_result content blocks
  - Tool calls come back as tool_use content blocks, not a separate field
  - stop_reason "tool_use" signals that tool calls are present

This adapter normalizes all of that into the internal types so the decision
loop never needs to know which provider it's talking to.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator

from .base import BaseLLMAdapter
from .types import (
    ANTHROPIC_CONTEXT_WINDOWS,
    ANTHROPIC_PRICING,
    LLMChunk,
    LLMResponse,
    PricingConfig,
    StopReason,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class AnthropicAdapter(BaseLLMAdapter):
    """
    Adapter for Anthropic Claude models.

    Each instance is bound to a single model. If you need multiple Claude models
    (e.g. Sonnet for most agents, Haiku for cheap summarization), register
    separate adapter instances in the registry.
    """

    # Fallback pricing if the configured model is not in the table
    _FALLBACK_PRICING = ANTHROPIC_PRICING["claude-sonnet-4-6"]

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        if not api_key:
            raise ValueError("Anthropic API key must not be empty")
        if not model:
            raise ValueError("Model name must not be empty")

        # Import here so the module can load even if the package is absent
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for AnthropicAdapter. "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._pricing: PricingConfig = ANTHROPIC_PRICING.get(model, self._FALLBACK_PRICING)

        if model not in ANTHROPIC_PRICING:
            logger.warning(
                "Model '%s' not found in ANTHROPIC_PRICING table; "
                "using claude-sonnet-4-6 pricing as fallback",
                model,
            )

    # ------------------------------------------------------------------
    # BaseLLMAdapter interface
    # ------------------------------------------------------------------

    def name(self) -> str:
        return "anthropic_claude"

    def max_context_tokens(self) -> int:
        return ANTHROPIC_CONTEXT_WINDOWS.get(self._model, 200_000)

    def count_tokens(self, messages: list[dict], system: str = "") -> int:
        # Character-based approximation: ~4 chars per token for English text.
        # This is intentionally conservative — better to compact early than to
        # hit a context overflow mid-run. For exact counts use the async API.
        total = len(system) // 4
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                # Structured content blocks (e.g. tool results)
                for block in content:
                    if isinstance(block, dict):
                        total += len(str(block.get("content", ""))) // 4
        # Add ~4 tokens per message for role/formatting overhead
        total += len(messages) * 4
        return total

    def cost_per_token(self) -> tuple[float, float]:
        return (
            self._pricing.input_per_million / 1_000_000,
            self._pricing.output_per_million / 1_000_000,
        )

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        if not messages:
            raise ValueError("messages list must not be empty")
        if max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": self._normalize_messages(messages),
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [self._format_tool(t) for t in tools]
        if stop_sequences:
            kwargs["stop_sequences"] = stop_sequences

        response = await self._client.messages.create(**kwargs)

        tool_calls: list[ToolCall] = []
        text_content = ""

        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)
        stop_reason = self._map_stop_reason(response.stop_reason)

        logger.debug(
            "Anthropic complete: model=%s input_tokens=%d output_tokens=%d cost_usd=%.6f",
            self._model,
            input_tokens,
            output_tokens,
            cost,
        )

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=input_tokens + output_tokens,
            model=self._model,
            cost_usd=cost,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        if not messages:
            raise ValueError("messages list must not be empty")

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": self._normalize_messages(messages),
        }
        if tools:
            kwargs["tools"] = [self._format_tool(t) for t in tools]

        async with self._client.messages.stream(**kwargs) as stream_ctx:
            async for event in stream_ctx:
                if not hasattr(event, "type"):
                    continue
                if event.type == "content_block_delta":
                    if hasattr(event, "delta") and hasattr(event.delta, "text"):
                        yield LLMChunk(delta=event.delta.text)
                    elif hasattr(event, "delta") and hasattr(event.delta, "partial_json"):
                        # Tool call argument streaming
                        yield LLMChunk(
                            delta="",
                            tool_call_delta={"partial_json": event.delta.partial_json},
                        )
                elif event.type == "message_stop":
                    yield LLMChunk(delta="", is_final=True, stop_reason=StopReason.END_TURN)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert the internal message format to Anthropic's wire format.

        Anthropic uses "user" role for tool results (wrapped in a tool_result
        content block) rather than a separate "tool" role.
        Consecutive same-role messages must be merged, which Anthropic rejects.
        """
        normalized: list[dict] = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "tool":
                # Tool results become user messages with tool_result content blocks
                tool_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg.get("content", ""),
                        }
                    ],
                }
                # Merge into the previous user message if it also holds tool results,
                # since Anthropic disallows consecutive same-role messages.
                if normalized and normalized[-1]["role"] == "user":
                    prev = normalized[-1]
                    if isinstance(prev["content"], list):
                        prev["content"].extend(tool_msg["content"])
                    else:
                        # Previous user message had a string content; convert to list
                        prev["content"] = [
                            {"type": "text", "text": prev["content"]},
                            *tool_msg["content"],
                        ]
                else:
                    normalized.append(tool_msg)
            else:
                normalized.append({"role": role, "content": msg.get("content", "")})
        return normalized

    def _format_tool(self, tool: ToolDefinition) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self._pricing.input_per_million / 1_000_000
            + output_tokens * self._pricing.output_per_million / 1_000_000
        )

    def _map_stop_reason(self, reason: str) -> StopReason:
        mapping: dict[str, StopReason] = {
            "end_turn": StopReason.END_TURN,
            "tool_use": StopReason.TOOL_USE,
            "max_tokens": StopReason.MAX_TOKENS,
            "stop_sequence": StopReason.STOP_SEQUENCE,
        }
        return mapping.get(reason, StopReason.END_TURN)

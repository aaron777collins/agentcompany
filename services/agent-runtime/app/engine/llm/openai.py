"""
OpenAI GPT adapter.

Uses OpenAI's chat completions API with function calling (now called "tools").
The primary behavioral difference from Anthropic: system instructions are
injected as the first message with role "system", not a separate parameter.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from .base import BaseLLMAdapter
from .types import (
    OPENAI_CONTEXT_WINDOWS,
    OPENAI_PRICING,
    LLMChunk,
    LLMResponse,
    PricingConfig,
    StopReason,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseLLMAdapter):
    """
    Adapter for OpenAI GPT models.

    Also serves as the base for OllamaAdapter and any other OpenAI-compatible
    endpoint. Subclasses override _calculate_cost() and max_context_tokens()
    as needed.
    """

    _FALLBACK_PRICING = OPENAI_PRICING["gpt-4o"]

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be empty")
        if not model:
            raise ValueError("Model name must not be empty")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAIAdapter. "
                "Install it with: pip install openai"
            ) from exc

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._pricing: PricingConfig = OPENAI_PRICING.get(model, self._FALLBACK_PRICING)

        if model not in OPENAI_PRICING and base_url is None:
            logger.warning(
                "Model '%s' not found in OPENAI_PRICING table; using gpt-4o pricing as fallback",
                model,
            )

    # ------------------------------------------------------------------
    # BaseLLMAdapter interface
    # ------------------------------------------------------------------

    def name(self) -> str:
        return "openai_gpt"

    def max_context_tokens(self) -> int:
        return OPENAI_CONTEXT_WINDOWS.get(self._model, 128_000)

    def count_tokens(self, messages: list[dict], system: str = "") -> int:
        # Use tiktoken when available for accurate counts.
        # Fall back to character-based approximation when the model is unknown
        # (e.g. a local Ollama model passed through this adapter).
        try:
            import tiktoken

            try:
                enc = tiktoken.encoding_for_model(self._model)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")

            total = len(enc.encode(system))
            for msg in messages:
                content = msg.get("content") or ""
                if isinstance(content, str):
                    total += len(enc.encode(content))
                total += 4  # per-message role/formatting overhead
            return total
        except ImportError:
            # tiktoken not installed — use character heuristic
            total = len(system) // 4
            for msg in messages:
                total += len(str(msg.get("content", ""))) // 4 + 4
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

        # OpenAI puts the system prompt as the first message
        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(self._normalize_messages(messages))

        kwargs: dict = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [self._format_tool(t) for t in tools]
            kwargs["tool_choice"] = "auto"
        if stop_sequences:
            kwargs["stop"] = stop_sequences

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning(
                        "Tool call %s returned invalid JSON arguments: %s",
                        tc.id,
                        tc.function.arguments,
                    )
                    args = {}
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        logger.debug(
            "OpenAI complete: model=%s input_tokens=%d output_tokens=%d cost_usd=%.6f",
            self._model,
            input_tokens,
            output_tokens,
            cost,
        )

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            stop_reason=self._map_stop_reason(choice.finish_reason),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=input_tokens + output_tokens,
            model=self._model,
            cost_usd=cost,
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

        openai_messages = [{"role": "system", "content": system}]
        openai_messages.extend(self._normalize_messages(messages))

        kwargs: dict = {
            "model": self._model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = [self._format_tool(t) for t in tools]

        async with self._client.chat.completions.stream(**kwargs) as stream_ctx:
            async for chunk in stream_ctx:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                if delta and delta.content:
                    yield LLMChunk(delta=delta.content)

                if finish_reason:
                    yield LLMChunk(
                        delta="",
                        is_final=True,
                        stop_reason=self._map_stop_reason(finish_reason),
                    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert internal message format to OpenAI's wire format.

        Internal "tool" role messages map to "tool" role in OpenAI format,
        which is already correct — no special wrapping needed unlike Anthropic.
        """
        normalized = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "tool":
                normalized.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }
                )
            else:
                normalized.append({"role": role, "content": msg.get("content", "")})
        return normalized

    def _format_tool(self, tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self._pricing.input_per_million / 1_000_000
            + output_tokens * self._pricing.output_per_million / 1_000_000
        )

    def _map_stop_reason(self, reason: str | None) -> StopReason:
        mapping: dict[str, StopReason] = {
            "stop": StopReason.END_TURN,
            "tool_calls": StopReason.TOOL_USE,
            "length": StopReason.MAX_TOKENS,
            "content_filter": StopReason.STOP_SEQUENCE,
        }
        return mapping.get(reason or "", StopReason.END_TURN)

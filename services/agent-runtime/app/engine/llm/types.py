"""
Shared types for the LLM adapter layer.

These types are the contract between the decision loop and any LLM provider.
The loop never imports provider-specific code — only these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StopReason(str, Enum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


@dataclass
class Message:
    """A single message in a conversation history."""

    role: MessageRole
    content: str
    # Only present on tool result messages
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""

    id: str          # Provider-generated call ID, used to correlate tool results
    name: str        # Tool name as registered in the tool registry
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """
    Typed response from any LLM provider.

    cost_usd is calculated by the adapter using the pricing table at call time.
    The budget tracker consumes this directly rather than re-deriving it.
    """

    content: str
    tool_calls: list[ToolCall]
    stop_reason: StopReason
    input_tokens: int
    output_tokens: int
    tokens_used: int           # input_tokens + output_tokens, pre-summed for convenience
    model: str                 # Exact model string used (e.g. "claude-sonnet-4-6")
    cost_usd: float
    raw_response: dict[str, Any] | None = None  # Original provider payload for debugging


@dataclass
class LLMChunk:
    """A single chunk from a streaming response."""

    delta: str
    tool_call_delta: dict[str, Any] | None = None
    is_final: bool = False
    stop_reason: StopReason | None = None


@dataclass
class ToolDefinition:
    """
    A tool description passed to the LLM so it can decide when to call it.

    input_schema must be a valid JSON Schema object describing the tool's parameters.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class PricingConfig:
    """USD pricing per million tokens for a single model."""

    input_per_million: float
    output_per_million: float
    cache_write_per_million: float | None = None
    cache_read_per_million: float | None = None


# ---------------------------------------------------------------------------
# Pricing tables — update when providers change rates.
# These live here (not in each adapter) so cost calculations stay consistent
# even if adapters are extended or replaced.
# ---------------------------------------------------------------------------

# Prices as of April 2026
ANTHROPIC_PRICING: dict[str, PricingConfig] = {
    "claude-opus-4-5": PricingConfig(
        input_per_million=15.0,
        output_per_million=75.0,
        cache_write_per_million=18.75,
        cache_read_per_million=1.50,
    ),
    "claude-sonnet-4-6": PricingConfig(
        input_per_million=3.0,
        output_per_million=15.0,
        cache_write_per_million=3.75,
        cache_read_per_million=0.30,
    ),
    "claude-haiku-4-5": PricingConfig(
        input_per_million=0.80,
        output_per_million=4.0,
        cache_write_per_million=1.00,
        cache_read_per_million=0.08,
    ),
    "claude-3-5-haiku": PricingConfig(
        input_per_million=0.80,
        output_per_million=4.0,
        cache_write_per_million=1.00,
        cache_read_per_million=0.08,
    ),
}

OPENAI_PRICING: dict[str, PricingConfig] = {
    "gpt-4o": PricingConfig(input_per_million=2.50, output_per_million=10.0),
    "gpt-4o-mini": PricingConfig(input_per_million=0.15, output_per_million=0.60),
    "gpt-4-turbo": PricingConfig(input_per_million=10.0, output_per_million=30.0),
    "o3": PricingConfig(input_per_million=10.0, output_per_million=40.0),
    "o4-mini": PricingConfig(input_per_million=1.10, output_per_million=4.40),
}

# Context window sizes by model — used by adapters to report their limits
ANTHROPIC_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-3-5-haiku": 200_000,
}

OPENAI_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "o3": 200_000,
    "o4-mini": 200_000,
}

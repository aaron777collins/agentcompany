"""
Unit tests for LLM adapter layer.

All external API calls are mocked — no real Anthropic/OpenAI/Ollama calls.
The anthropic and openai packages may not be installed in the test environment;
we mock their imports so the adapters can be instantiated.

Tests focus on:
- Message formatting (wire format translation)
- Tool definition formatting
- Cost calculation
- Token counting approximations
- Zero-cost for Ollama
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.llm.types import (
    LLMResponse,
    StopReason,
    ToolCall,
    ToolDefinition,
)


# ---------------------------------------------------------------------------
# Provider package stubs
# ---------------------------------------------------------------------------
# Install minimal stubs for 'anthropic' and 'openai' so importing the adapters
# does not fail even when the real packages are absent.

def _stub_anthropic():
    """Install a minimal anthropic stub into sys.modules."""
    if "anthropic" in sys.modules:
        return
    stub = ModuleType("anthropic")
    stub.AsyncAnthropic = MagicMock()
    sys.modules["anthropic"] = stub


def _stub_openai():
    """Install a minimal openai stub into sys.modules."""
    if "openai" in sys.modules:
        return
    stub = ModuleType("openai")
    stub.AsyncOpenAI = MagicMock()
    sys.modules["openai"] = stub


_stub_anthropic()
_stub_openai()

# Now import adapters — they will use the stubs
from app.engine.llm.anthropic import AnthropicAdapter  # noqa: E402
from app.engine.llm.openai import OpenAIAdapter  # noqa: E402
from app.engine.llm.ollama import OllamaAdapter  # noqa: E402


# ---------------------------------------------------------------------------
# AnthropicAdapter
# ---------------------------------------------------------------------------


class TestAnthropicAdapterInit:
    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="API key"):
            AnthropicAdapter(api_key="")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="Model"):
            AnthropicAdapter(api_key="key", model="")

    def test_known_model_has_correct_name(self):
        adapter = AnthropicAdapter(api_key="key", model="claude-sonnet-4-6")
        assert adapter.name() == "anthropic_claude"

    def test_unknown_model_uses_fallback_pricing(self):
        adapter = AnthropicAdapter(api_key="key", model="claude-future-99")
        # Should not raise; fallback pricing is used
        in_cost, out_cost = adapter.cost_per_token()
        assert in_cost > 0
        assert out_cost > 0

    def test_max_context_tokens_for_known_model(self):
        adapter = AnthropicAdapter(api_key="key", model="claude-sonnet-4-6")
        assert adapter.max_context_tokens() == 200_000

    def test_max_context_tokens_fallback_for_unknown_model(self):
        adapter = AnthropicAdapter(api_key="key", model="unknown-model")
        assert adapter.max_context_tokens() == 200_000


class TestAnthropicAdapterMessageFormatting:
    def setup_method(self):
        self.adapter = AnthropicAdapter(api_key="test-key", model="claude-sonnet-4-6")

    def test_user_message_passes_through(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = self.adapter._normalize_messages(messages)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_assistant_message_passes_through(self):
        messages = [{"role": "assistant", "content": "I can help"}]
        result = self.adapter._normalize_messages(messages)
        assert result == [{"role": "assistant", "content": "I can help"}]

    def test_tool_message_becomes_user_with_tool_result_block(self):
        messages = [
            {
                "role": "tool",
                "content": "result data",
                "tool_call_id": "call-001",
            }
        ]
        result = self.adapter._normalize_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        block = result[0]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "call-001"
        assert block["content"] == "result data"

    def test_consecutive_tool_messages_merged_into_one_user_message(self):
        messages = [
            {"role": "tool", "content": "result1", "tool_call_id": "call-001"},
            {"role": "tool", "content": "result2", "tool_call_id": "call-002"},
        ]
        result = self.adapter._normalize_messages(messages)
        # Both tool results should be merged under a single user message
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert len(result[0]["content"]) == 2

    def test_tool_message_after_user_message_merges_into_previous_user(self):
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "tool", "content": "4", "tool_call_id": "calc-001"},
        ]
        result = self.adapter._normalize_messages(messages)
        # The tool result should be merged into the preceding user message
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        text_blocks = [b for b in result[0]["content"] if b.get("type") == "text"]
        tool_result_blocks = [b for b in result[0]["content"] if b.get("type") == "tool_result"]
        assert len(text_blocks) == 1
        assert len(tool_result_blocks) == 1

    def test_format_tool_definition(self):
        tool = ToolDefinition(
            name="search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        formatted = self.adapter._format_tool(tool)
        assert formatted["name"] == "search"
        assert formatted["description"] == "Search the web"
        assert "input_schema" in formatted

    def test_cost_calculation_sonnet(self):
        # claude-sonnet-4-6: $3/M input, $15/M output
        in_cost, out_cost = self.adapter.cost_per_token()
        # per-token cost * 1M = dollar cost per million
        assert abs(in_cost * 1_000_000 - 3.0) < 0.001
        assert abs(out_cost * 1_000_000 - 15.0) < 0.001


class TestAnthropicAdapterTokenCounting:
    def setup_method(self):
        self.adapter = AnthropicAdapter(api_key="test-key")

    def test_token_count_approximation_scales_with_content(self):
        short_msgs = [{"role": "user", "content": "Hi"}]
        long_msgs = [{"role": "user", "content": "H" * 400}]
        short_count = self.adapter.count_tokens(short_msgs)
        long_count = self.adapter.count_tokens(long_msgs)
        assert long_count > short_count

    def test_system_prompt_contributes_to_token_count(self):
        msgs = [{"role": "user", "content": "Hello"}]
        no_system = self.adapter.count_tokens(msgs, system="")
        with_system = self.adapter.count_tokens(msgs, system="You are a helpful agent. " * 10)
        assert with_system > no_system

    def test_empty_messages_return_small_count(self):
        count = self.adapter.count_tokens([])
        assert count >= 0

    def test_list_content_blocks_count(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "A" * 200, "tool_use_id": "x"}
                ],
            }
        ]
        count = self.adapter.count_tokens(msgs)
        assert count > 0


# ---------------------------------------------------------------------------
# OpenAIAdapter
# ---------------------------------------------------------------------------


class TestOpenAIAdapterInit:
    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="API key"):
            OpenAIAdapter(api_key="")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError):
            OpenAIAdapter(api_key="key", model="")

    def test_name_is_openai_gpt(self):
        adapter = OpenAIAdapter(api_key="key", model="gpt-4o")
        assert adapter.name() == "openai_gpt"


class TestOpenAIAdapterMessageFormatting:
    def setup_method(self):
        self.adapter = OpenAIAdapter(api_key="test-key", model="gpt-4o")

    def test_tool_message_uses_tool_role(self):
        messages = [
            {"role": "tool", "content": "42", "tool_call_id": "call-abc"},
        ]
        result = self.adapter._normalize_messages(messages)
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call-abc"
        assert result[0]["content"] == "42"

    def test_format_tool_definition_includes_function_wrapper(self):
        tool = ToolDefinition(
            name="get_weather",
            description="Get current weather",
            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
        )
        formatted = self.adapter._format_tool(tool)
        assert formatted["type"] == "function"
        assert formatted["function"]["name"] == "get_weather"
        assert "parameters" in formatted["function"]

    def test_cost_calculation_gpt4o(self):
        # gpt-4o: $2.50/M input, $10/M output
        in_cost, out_cost = self.adapter.cost_per_token()
        assert abs(in_cost * 1_000_000 - 2.50) < 0.01
        assert abs(out_cost * 1_000_000 - 10.0) < 0.01

    def test_context_window_for_gpt4o(self):
        adapter = OpenAIAdapter(api_key="k", model="gpt-4o")
        assert adapter.max_context_tokens() == 128_000

    def test_unknown_model_uses_fallback_context_window(self):
        adapter = OpenAIAdapter(api_key="k", model="future-model-99", base_url="http://x")
        assert adapter.max_context_tokens() == 128_000


# ---------------------------------------------------------------------------
# OllamaAdapter
# ---------------------------------------------------------------------------


class TestOllamaAdapter:
    def _make_adapter(self, **kwargs) -> OllamaAdapter:
        with patch("app.engine.llm.ollama.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://ollama:11434"
            mock_settings.return_value.ollama_default_model = "gemma3"
            return OllamaAdapter(base_url="http://localhost:11434", model="gemma3", **kwargs)

    def test_zero_cost_per_token(self):
        adapter = self._make_adapter()
        in_cost, out_cost = adapter.cost_per_token()
        assert in_cost == 0.0
        assert out_cost == 0.0

    def test_calculate_cost_always_zero(self):
        adapter = self._make_adapter()
        assert adapter._calculate_cost(1_000_000, 1_000_000) == 0.0

    def test_name_is_ollama(self):
        adapter = self._make_adapter()
        assert adapter.name() == "ollama"

    def test_custom_context_window(self):
        adapter = self._make_adapter(context_window=32_768)
        assert adapter.max_context_tokens() == 32_768

    def test_default_context_window(self):
        adapter = self._make_adapter()
        assert adapter.max_context_tokens() == 8_192

    def test_token_counting_character_based(self):
        adapter = self._make_adapter()
        msgs = [{"role": "user", "content": "A" * 400}]
        count = adapter.count_tokens(msgs)
        # 400 chars / 4 chars-per-token = 100 tokens + 4 overhead = 104
        assert count == pytest.approx(104, abs=10)


# ---------------------------------------------------------------------------
# Stop reason mapping
# ---------------------------------------------------------------------------


class TestStopReasonMapping:
    def setup_method(self):
        self.anthropic = AnthropicAdapter(api_key="k")
        self.openai = OpenAIAdapter(api_key="k", model="gpt-4o")

    def test_anthropic_end_turn(self):
        assert self.anthropic._map_stop_reason("end_turn") == StopReason.END_TURN

    def test_anthropic_tool_use(self):
        assert self.anthropic._map_stop_reason("tool_use") == StopReason.TOOL_USE

    def test_anthropic_max_tokens(self):
        assert self.anthropic._map_stop_reason("max_tokens") == StopReason.MAX_TOKENS

    def test_anthropic_stop_sequence(self):
        assert self.anthropic._map_stop_reason("stop_sequence") == StopReason.STOP_SEQUENCE

    def test_anthropic_unknown_reason_defaults_to_end_turn(self):
        assert self.anthropic._map_stop_reason("unknown_reason") == StopReason.END_TURN

    def test_openai_stop_maps_to_end_turn(self):
        assert self.openai._map_stop_reason("stop") == StopReason.END_TURN

    def test_openai_tool_calls_maps_to_tool_use(self):
        assert self.openai._map_stop_reason("tool_calls") == StopReason.TOOL_USE

    def test_openai_length_maps_to_max_tokens(self):
        assert self.openai._map_stop_reason("length") == StopReason.MAX_TOKENS

    def test_openai_none_reason_defaults_to_end_turn(self):
        assert self.openai._map_stop_reason(None) == StopReason.END_TURN

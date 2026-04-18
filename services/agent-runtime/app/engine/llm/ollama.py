"""
Ollama local model adapter.

Ollama exposes an OpenAI-compatible REST API, so this is a thin wrapper around
OpenAIAdapter that:
  1. Removes the API key requirement (local, no auth)
  2. Reports zero cost (no external API billing)
  3. Uses a conservative default context window (actual window depends on the
     model and Ollama's OLLAMA_NUM_CTX setting)
  4. Disables tiktoken-based counting since arbitrary local models are not in
     tiktoken's model registry
"""

from __future__ import annotations

import logging

from .openai import OpenAIAdapter
from .types import LLMChunk, LLMResponse, ToolDefinition

logger = logging.getLogger(__name__)

# Default Ollama context window. Real value depends on the loaded model.
# Operators should set this explicitly via the agent's llm_config if they
# know the model's actual context window.
_DEFAULT_CONTEXT_WINDOW = 8_192


class OllamaAdapter(OpenAIAdapter):
    """
    Adapter for models served by a local Ollama instance.

    Defaults to http://localhost:11434/v1 but this can be overridden to
    point at a remote Ollama server.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2",
        context_window: int = _DEFAULT_CONTEXT_WINDOW,
    ) -> None:
        if not model:
            raise ValueError("Model name must not be empty")

        # Ollama does not require a real API key; any non-empty string works
        super().__init__(api_key="ollama", model=model, base_url=base_url)
        self._context_window = context_window

    def name(self) -> str:
        return "ollama"

    def max_context_tokens(self) -> int:
        return self._context_window

    def count_tokens(self, messages: list[dict], system: str = "") -> int:
        # Local models do not have tiktoken encodings.
        # Character-based approximation: 1 token ~= 4 characters.
        total = len(system) // 4
        for msg in messages:
            total += len(str(msg.get("content", ""))) // 4 + 4
        return total

    def cost_per_token(self) -> tuple[float, float]:
        # Local inference has no per-token API cost
        return (0.0, 0.0)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

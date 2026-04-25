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

from app.config import get_settings
from .openai import OpenAIAdapter
from .types import LLMChunk, LLMResponse, ToolDefinition

logger = logging.getLogger(__name__)

# Default Ollama context window. Real value depends on the loaded model.
# Operators should set this explicitly via the agent's llm_config if they
# know the model's actual context window.
_DEFAULT_CONTEXT_WINDOW = 8_192


def _default_base_url() -> str:
    """Return the Ollama base URL from settings, appending the /v1 OpenAI path.

    Resolved lazily so tests can override settings without import-time side effects.
    """
    return f"{get_settings().ollama_base_url}/v1"


def _default_model() -> str:
    """Return the default Ollama model name from settings."""
    return get_settings().ollama_default_model


class OllamaAdapter(OpenAIAdapter):
    """
    Adapter for models served by a local Ollama instance.

    The default base URL and model are read from application settings so they
    can be controlled via environment variables (OLLAMA_BASE_URL, OLLAMA_MODEL)
    without code changes.  Pass explicit values to override for a specific agent.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        context_window: int = _DEFAULT_CONTEXT_WINDOW,
    ) -> None:
        resolved_base_url = base_url if base_url is not None else _default_base_url()
        resolved_model = model if model is not None else _default_model()

        if not resolved_model:
            raise ValueError("Model name must not be empty")

        # Ollama does not require a real API key; any non-empty string satisfies
        # the OpenAI client's validation without sending an Authorization header.
        super().__init__(api_key="ollama", model=resolved_model, base_url=resolved_base_url)
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

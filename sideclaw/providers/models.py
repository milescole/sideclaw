"""Centralized model registry for provider detection and model metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a known model."""

    id: str
    provider: str  # "anthropic" | "openai" | "ollama" | "openrouter"
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True


class ModelRegistry:
    """Source of truth for model metadata and provider detection.

    Detection strategy:
    1. Exact match in registry → return ModelInfo.provider
    2. Prefix match (claude → anthropic, gpt-/o1-/o3-/o4- → openai, ollama/ → ollama)
    3. Fallback → "openrouter"
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}
        self._register_defaults()

    def get(self, model_id: str) -> ModelInfo | None:
        """Look up model metadata by exact id."""
        return self._models.get(model_id)

    def detect_provider(self, model_id: str) -> str:
        """Detect the provider for a given model identifier."""
        # 1. Exact match
        info = self._models.get(model_id)
        if info is not None:
            return info.provider

        # 2. Prefix match
        lower = model_id.lower()
        if lower.startswith("claude"):
            return "anthropic"
        if any(lower.startswith(p) for p in ("gpt-", "o1-", "o3-", "o4-")):
            return "openai"
        if lower.startswith("ollama/"):
            return "ollama"

        # 3. Fallback
        return "openrouter"

    def register(self, info: ModelInfo) -> None:
        """Register or override a model entry."""
        self._models[info.id] = info

    def list_models(self, *, provider: str | None = None) -> list[ModelInfo]:
        """List registered models, optionally filtered by provider."""
        models = list(self._models.values())
        if provider is not None:
            models = [m for m in models if m.provider == provider]
        return models

    def _register_defaults(self) -> None:
        """Register built-in model definitions."""
        defaults = [
            # Anthropic — latest generation
            ModelInfo("claude-opus-4-6", "anthropic", 1_000_000, 128_000, supports_vision=True),
            ModelInfo("claude-sonnet-4-6", "anthropic", 1_000_000, 64_000, supports_vision=True),
            ModelInfo("claude-haiku-4-5-20251001", "anthropic", 200_000, 64_000, supports_vision=True),
            # Anthropic — legacy
            ModelInfo("claude-opus-4-20250918", "anthropic", 200_000, 32_000, supports_vision=True),
            ModelInfo("claude-sonnet-4-20250514", "anthropic", 200_000, 64_000, supports_vision=True),
            ModelInfo("claude-opus-4-20250514", "anthropic", 200_000, 32_000, supports_vision=True),
            # OpenAI
            ModelInfo("gpt-4o", "openai", 128_000, 16_384, supports_vision=True),
            ModelInfo("gpt-4o-mini", "openai", 128_000, 16_384, supports_vision=True),
            ModelInfo("gpt-5.4", "openai", 128_000, 16_384, supports_vision=True),
            ModelInfo("o1-preview", "openai", 128_000, 32_768),
            ModelInfo("o1-mini", "openai", 128_000, 65_536),
            ModelInfo("o3-mini", "openai", 200_000, 100_000),
            ModelInfo("o4-mini", "openai", 200_000, 100_000),
        ]
        for info in defaults:
            self._models[info.id] = info

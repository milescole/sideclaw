"""Per-model cost estimation for LLM token usage."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Pricing for a model pattern."""

    pattern: str  # regex matching model IDs
    input_cost_per_mtok: float  # $/million input tokens
    output_cost_per_mtok: float  # $/million output tokens
    cache_read_discount: float = 0.1  # multiplier vs input cost
    cache_write_premium: float = 1.25  # multiplier vs input cost


# Pricing data (as of early 2026).
_DEFAULT_PRICING: list[ModelPricing] = [
    # Anthropic
    ModelPricing("claude-opus-4", 15.0, 75.0, cache_read_discount=0.1, cache_write_premium=1.25),
    ModelPricing("claude-sonnet-4", 3.0, 15.0, cache_read_discount=0.1, cache_write_premium=1.25),
    ModelPricing("claude-haiku-4", 0.80, 4.0, cache_read_discount=0.1, cache_write_premium=1.25),
    # OpenAI
    ModelPricing("gpt-4o-mini", 0.15, 0.60),
    ModelPricing("gpt-4o", 2.50, 10.0),
    ModelPricing("gpt-5", 2.50, 10.0),
    ModelPricing("o1-preview", 15.0, 60.0),
    ModelPricing("o1-mini", 3.0, 12.0),
    ModelPricing("o3-mini", 1.10, 4.40),
    ModelPricing("o4-mini", 1.10, 4.40),
]


class PricingRegistry:
    """Look up per-model pricing and estimate costs."""

    def __init__(self, extra: list[ModelPricing] | None = None) -> None:
        self._pricing = list(_DEFAULT_PRICING)
        if extra:
            self._pricing = extra + self._pricing

    def get_pricing(self, model: str) -> ModelPricing | None:
        """Find pricing for a model ID via prefix matching."""
        for p in self._pricing:
            if model.startswith(p.pattern) or re.match(p.pattern, model):
                return p
        return None

    def estimate_call_cost(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Estimate cost in dollars for a single LLM call."""
        pricing = self.get_pricing(model)
        if pricing is None:
            return 0.0

        input_cost = (prompt_tokens / 1_000_000) * pricing.input_cost_per_mtok
        output_cost = (completion_tokens / 1_000_000) * pricing.output_cost_per_mtok
        cache_read_cost = (
            (cache_read_tokens / 1_000_000)
            * pricing.input_cost_per_mtok
            * pricing.cache_read_discount
        )
        cache_write_cost = (
            (cache_creation_tokens / 1_000_000)
            * pricing.input_cost_per_mtok
            * pricing.cache_write_premium
        )
        return input_cost + output_cost + cache_read_cost + cache_write_cost

    def estimate_session_cost(self, records: list) -> float:
        """Estimate total cost for a list of UsageRecord objects."""
        total = 0.0
        for r in records:
            total += self.estimate_call_cost(
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                cache_creation_tokens=getattr(r, "cache_creation_tokens", 0),
                cache_read_tokens=getattr(r, "cache_read_tokens", 0),
            )
        return total

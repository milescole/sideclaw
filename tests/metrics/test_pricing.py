"""Tests for PricingRegistry."""

from sideclaw.metrics.pricing import ModelPricing, PricingRegistry
from sideclaw.metrics.usage import UsageRecord


class TestPricingRegistry:
    def test_anthropic_opus_pricing(self):
        registry = PricingRegistry()
        pricing = registry.get_pricing("claude-opus-4-6")
        assert pricing is not None
        assert pricing.input_cost_per_mtok == 15.0
        assert pricing.output_cost_per_mtok == 75.0

    def test_openai_gpt4o_pricing(self):
        registry = PricingRegistry()
        pricing = registry.get_pricing("gpt-4o")
        assert pricing is not None
        assert pricing.input_cost_per_mtok == 2.50

    def test_unknown_model_returns_none(self):
        registry = PricingRegistry()
        assert registry.get_pricing("some-unknown-model") is None

    def test_estimate_call_cost_basic(self):
        registry = PricingRegistry()
        # 1M input tokens at $15/M + 1M output tokens at $75/M = $90
        cost = registry.estimate_call_cost(
            model="claude-opus-4-6",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        assert abs(cost - 90.0) < 0.01

    def test_estimate_call_cost_with_cache(self):
        registry = PricingRegistry()
        cost = registry.estimate_call_cost(
            model="claude-opus-4-6",
            prompt_tokens=100_000,
            completion_tokens=10_000,
            cache_read_tokens=50_000,
            cache_creation_tokens=20_000,
        )
        assert cost > 0.0
        # cache read should be cheaper than regular input
        cost_no_cache = registry.estimate_call_cost(
            model="claude-opus-4-6",
            prompt_tokens=100_000 + 50_000,
            completion_tokens=10_000,
        )
        assert cost < cost_no_cache

    def test_estimate_call_cost_unknown_model(self):
        registry = PricingRegistry()
        cost = registry.estimate_call_cost(
            model="unknown-model",
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
        )
        assert cost == 0.0

    def test_estimate_session_cost(self):
        registry = PricingRegistry()
        records = [
            UsageRecord(
                timestamp="2026-03-20T00:00:00+00:00",
                session_key="cli:test",
                model="gpt-4o",
                prompt_tokens=10_000,
                completion_tokens=5_000,
                total_tokens=15_000,
            ),
            UsageRecord(
                timestamp="2026-03-20T00:01:00+00:00",
                session_key="cli:test",
                model="gpt-4o",
                prompt_tokens=20_000,
                completion_tokens=10_000,
                total_tokens=30_000,
            ),
        ]
        cost = registry.estimate_session_cost(records)
        assert cost > 0.0

    def test_custom_pricing_takes_precedence(self):
        custom = [ModelPricing("gpt-4o", 999.0, 999.0)]
        registry = PricingRegistry(extra=custom)
        pricing = registry.get_pricing("gpt-4o")
        assert pricing is not None
        assert pricing.input_cost_per_mtok == 999.0

    def test_gpt4o_mini_matches_before_gpt4o(self):
        registry = PricingRegistry()
        pricing = registry.get_pricing("gpt-4o-mini")
        assert pricing is not None
        assert pricing.input_cost_per_mtok == 0.15

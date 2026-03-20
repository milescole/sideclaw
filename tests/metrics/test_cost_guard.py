"""Tests for CostGuard."""

from pathlib import Path

from sideclaw.metrics.cost_guard import CostGuard
from sideclaw.metrics.usage import UsageTracker


class TestCostGuard:
    def test_allowed_when_under_budget(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        guard = CostGuard(usage_tracker=tracker, max_daily_cost=5.0)
        allowed, reason = guard.check_allowed("gpt-4o")
        assert allowed is True
        assert reason is None

    def test_denied_when_over_daily_cost(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        # Record enough usage to exceed $5 budget
        # gpt-4o: $2.50/M input + $10/M output
        # 10M input tokens = $25 — well over $5
        tracker.record_from_response(
            usage={"prompt_tokens": 10_000_000, "completion_tokens": 0},
            session_key="cli:test",
            model="gpt-4o",
        )
        guard = CostGuard(usage_tracker=tracker, max_daily_cost=5.0)
        allowed, reason = guard.check_allowed("gpt-4o")
        assert allowed is False
        assert "Daily cost limit" in reason

    def test_denied_when_over_hourly_calls(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        for _ in range(10):
            tracker.record_from_response(
                usage={"prompt_tokens": 100, "completion_tokens": 50},
                session_key="cli:test",
                model="gpt-4o",
            )
        guard = CostGuard(
            usage_tracker=tracker, max_daily_cost=999.0, max_hourly_calls=10
        )
        allowed, reason = guard.check_allowed("gpt-4o")
        assert allowed is False
        assert "Hourly call limit" in reason

    def test_allowed_when_hourly_limit_disabled(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        for _ in range(100):
            tracker.record_from_response(
                usage={"prompt_tokens": 100, "completion_tokens": 50},
                session_key="cli:test",
                model="gpt-4o",
            )
        guard = CostGuard(
            usage_tracker=tracker, max_daily_cost=999.0, max_hourly_calls=0
        )
        allowed, reason = guard.check_allowed("gpt-4o")
        assert allowed is True

    def test_unknown_model_cost_zero(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record_from_response(
            usage={"prompt_tokens": 10_000_000, "completion_tokens": 0},
            session_key="cli:test",
            model="unknown-model",
        )
        guard = CostGuard(usage_tracker=tracker, max_daily_cost=5.0)
        # Unknown model has zero cost, so should still be allowed
        allowed, _ = guard.check_allowed("unknown-model")
        assert allowed is True

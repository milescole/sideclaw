"""Daily spend and hourly rate limiting for LLM calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sideclaw.metrics.pricing import PricingRegistry
from sideclaw.metrics.usage import UsageTracker


class CostGuard:
    """Check daily cost and hourly call budgets before allowing LLM calls."""

    def __init__(
        self,
        *,
        usage_tracker: UsageTracker,
        max_daily_cost: float = 5.0,
        max_hourly_calls: int = 0,
    ) -> None:
        self._tracker = usage_tracker
        self._max_daily_cost = max_daily_cost
        self._max_hourly_calls = max_hourly_calls
        self._pricing = PricingRegistry()

    def check_allowed(self, model: str = "") -> tuple[bool, str | None]:
        """Check whether a new LLM call is within budget.

        Returns ``(True, None)`` if allowed, or ``(False, reason)`` if denied.
        """
        if self._max_daily_cost > 0:
            start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            cost = self._pricing.estimate_session_cost(
                self._tracker.get_all_records(since=start_of_day)
            )
            if cost >= self._max_daily_cost:
                return False, (
                    f"Daily cost limit reached (${cost:.4f} / ${self._max_daily_cost:.2f}). "
                    "Try again tomorrow or increase cost_guard.max_daily_cost."
                )

        if self._max_hourly_calls > 0:
            one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
            recent = self._tracker.get_all_records(since=one_hour_ago)
            if len(recent) >= self._max_hourly_calls:
                return False, (
                    f"Hourly call limit reached ({len(recent)} / {self._max_hourly_calls}). "
                    "Try again later or increase cost_guard.max_hourly_calls."
                )

        return True, None

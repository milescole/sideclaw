"""Tests for UsageTracker."""

from datetime import UTC, datetime
from pathlib import Path

from sideclaw.metrics.usage import UsageRecord, UsageTracker


def _make_record(**overrides) -> UsageRecord:
    defaults = {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_key": "cli:test",
        "model": "claude-opus-4-6",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }
    defaults.update(overrides)
    return UsageRecord(**defaults)


class TestUsageTracker:
    def test_record_and_session_totals(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record(_make_record(session_key="s1", prompt_tokens=100, completion_tokens=50, total_tokens=150))
        tracker.record(_make_record(session_key="s1", prompt_tokens=200, completion_tokens=100, total_tokens=300))
        tracker.record(_make_record(session_key="s2", prompt_tokens=50, completion_tokens=25, total_tokens=75))

        totals = tracker.get_session_totals("s1")
        assert totals.prompt_tokens == 300
        assert totals.completion_tokens == 150
        assert totals.total_tokens == 450
        assert totals.llm_calls == 2

    def test_jsonl_persistence(self, tmp_path: Path):
        log_path = tmp_path / "usage.jsonl"
        tracker = UsageTracker(log_path)
        tracker.record(_make_record())
        tracker.record(_make_record())

        assert log_path.exists()
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_record_from_response(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record_from_response(
            usage={"prompt_tokens": 500, "completion_tokens": 200, "cache_read_tokens": 100},
            session_key="s1",
            model="gpt-4o",
            duration_ms=1234,
        )
        totals = tracker.get_session_totals("s1")
        assert totals.prompt_tokens == 500
        assert totals.completion_tokens == 200
        assert totals.cache_read_tokens == 100
        assert totals.total_duration_ms == 1234

    def test_daily_totals(self, tmp_path: Path):
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record(_make_record(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        tracker.record(_make_record(prompt_tokens=200, completion_tokens=100, total_tokens=300, model="gpt-4o"))

        daily = tracker.get_daily_totals(today)
        assert daily.llm_calls == 2
        assert daily.total_tokens == 450
        assert "claude-opus-4-6" in daily.models
        assert "gpt-4o" in daily.models

    def test_get_all_records(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record(_make_record())
        tracker.record(_make_record())
        tracker.record(_make_record())

        all_recs = tracker.get_all_records()
        assert len(all_recs) == 3

    def test_get_all_records_with_limit(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        for _ in range(5):
            tracker.record(_make_record())

        limited = tracker.get_all_records(limit=2)
        assert len(limited) == 2

    def test_empty_session_totals(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        totals = tracker.get_session_totals("nonexistent")
        assert totals.llm_calls == 0
        assert totals.total_tokens == 0

    def test_duration_tracking(self, tmp_path: Path):
        tracker = UsageTracker(tmp_path / "usage.jsonl")
        tracker.record(_make_record(session_key="s1", duration_ms=500))
        tracker.record(_make_record(session_key="s1", duration_ms=300))

        totals = tracker.get_session_totals("s1")
        assert totals.total_duration_ms == 800

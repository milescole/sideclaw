"""Tests for ExecutionLogger."""

from datetime import UTC, datetime
from pathlib import Path

from sideclaw.metrics.execution_log import ExecutionLogEntry, ExecutionLogger, ToolCallEntry


def _make_entry(**overrides) -> ExecutionLogEntry:
    defaults = {
        "run_id": "r1",
        "session_key": "cli:test",
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "duration_ms": 1000,
        "status": "completed",
        "llm_calls": 2,
        "total_prompt_tokens": 500,
        "total_completion_tokens": 200,
        "model": "gpt-4o",
        "channel": "cli",
    }
    defaults.update(overrides)
    return ExecutionLogEntry(**defaults)


class TestExecutionLogger:
    def test_log_and_read(self, tmp_path: Path):
        log = ExecutionLogger(tmp_path / "runs.jsonl")
        log.log_run(_make_entry(run_id="r1"))
        log.log_run(_make_entry(run_id="r2"))

        runs = log.get_recent_runs()
        assert len(runs) == 2
        assert runs[0].run_id == "r1"
        assert runs[1].run_id == "r2"

    def test_recent_runs_limit(self, tmp_path: Path):
        log = ExecutionLogger(tmp_path / "runs.jsonl")
        for i in range(5):
            log.log_run(_make_entry(run_id=f"r{i}"))

        runs = log.get_recent_runs(limit=2)
        assert len(runs) == 2
        assert runs[0].run_id == "r3"
        assert runs[1].run_id == "r4"

    def test_tool_calls_roundtrip(self, tmp_path: Path):
        log = ExecutionLogger(tmp_path / "runs.jsonl")
        entry = _make_entry(
            tool_calls=[
                ToolCallEntry(name="read_file", duration_ms=50),
                ToolCallEntry(name="exec", duration_ms=200, outcome="denied"),
            ]
        )
        log.log_run(entry)

        runs = log.get_recent_runs()
        assert len(runs) == 1
        assert len(runs[0].tool_calls) == 2
        assert runs[0].tool_calls[0].name == "read_file"
        assert runs[0].tool_calls[1].outcome == "denied"

    def test_get_runs_since(self, tmp_path: Path):
        log = ExecutionLogger(tmp_path / "runs.jsonl")
        log.log_run(_make_entry(run_id="old", started_at="2025-01-01T00:00:00+00:00"))
        log.log_run(_make_entry(run_id="new", started_at="2026-03-20T00:00:00+00:00"))

        cutoff = datetime(2026, 1, 1, tzinfo=UTC)
        runs = log.get_runs_since(cutoff)
        assert len(runs) == 1
        assert runs[0].run_id == "new"

    def test_empty_log(self, tmp_path: Path):
        log = ExecutionLogger(tmp_path / "runs.jsonl")
        assert log.get_recent_runs() == []
        assert log.get_runs_since(datetime.now(UTC)) == []

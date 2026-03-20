"""Structured run-level execution log with JSONL persistence.

Each completed run produces an ``ExecutionLogEntry`` appended to a JSONL
file for post-hoc analysis, separate from the per-call usage log.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger


@dataclass
class ToolCallEntry:
    """Summary of a single tool call within a run."""

    name: str
    duration_ms: int = 0
    outcome: str = "success"


@dataclass
class ExecutionLogEntry:
    """A single completed run's execution summary."""

    run_id: str
    session_key: str
    started_at: str  # ISO-8601
    completed_at: str  # ISO-8601
    duration_ms: int = 0
    status: str = "completed"
    llm_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    tool_calls: list[ToolCallEntry] = field(default_factory=list)
    model: str = ""
    channel: str = ""


class ExecutionLogger:
    """Appends run-level execution logs to a JSONL file."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path

    def log_run(self, entry: ExecutionLogEntry) -> None:
        """Append a completed run entry to the log file."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = asdict(entry)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, default=str) + "\n")
        except OSError as exc:
            logger.warning(f"Failed to write execution log: {exc}")

    def get_recent_runs(self, limit: int = 20) -> list[ExecutionLogEntry]:
        """Read the most recent run entries."""
        entries = self._load_all()
        return entries[-limit:] if limit > 0 else entries

    def get_runs_since(self, since: datetime) -> list[ExecutionLogEntry]:
        """Return runs started at or after the given datetime."""
        cutoff = since.isoformat()
        entries = self._load_all()
        return [e for e in entries if e.started_at >= cutoff]

    def _load_all(self) -> list[ExecutionLogEntry]:
        """Load all entries from the JSONL file."""
        if not self._log_path.exists():
            return []
        entries: list[ExecutionLogEntry] = []
        try:
            for line in self._log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                tool_calls = [
                    ToolCallEntry(**tc) for tc in data.pop("tool_calls", [])
                ]
                entries.append(ExecutionLogEntry(**data, tool_calls=tool_calls))
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning(f"Failed to read execution log: {exc}")
        return entries

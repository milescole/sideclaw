"""Cron execution history tracking."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass
class CronHistoryEntry:
    """A single cron execution record."""

    entry_id: str = field(default_factory=lambda: uuid4().hex[:12])
    job_id: str = ""
    job_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = "completed"
    error: str | None = None
    duration_ms: int = 0


class CronHistory:
    """Append-only JSONL history for cron executions."""

    def __init__(self, history_path: Path) -> None:
        self._path = history_path

    def record(self, entry: CronHistoryEntry) -> None:
        """Append an entry to the history file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(entry)) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)

    def get_entries(
        self, *, job_id: str | None = None, limit: int = 20
    ) -> list[CronHistoryEntry]:
        """Read entries, optionally filtered by job_id, most recent first."""
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().split("\n")
        entries: list[CronHistoryEntry] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if job_id and data.get("job_id") != job_id:
                continue
            entries.append(CronHistoryEntry(**data))
            if len(entries) >= limit:
                break
        return entries

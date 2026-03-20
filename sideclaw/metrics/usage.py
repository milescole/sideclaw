"""Token usage tracking with JSONL persistence.

Records per-call token usage from LLM providers and persists to an
append-only JSONL file.  Provides session, model, and daily aggregation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger

from sideclaw.utils.files import atomic_write_text


@dataclass
class UsageRecord:
    """A single LLM call's token usage."""

    timestamp: str  # ISO-8601
    session_key: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    tool_name: str | None = None
    duration_ms: int | None = None


@dataclass
class SessionUsage:
    """Aggregated usage for a session."""

    session_key: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    llm_calls: int = 0
    total_duration_ms: int = 0
    estimated_cost: float = 0.0


@dataclass
class DailyUsage:
    """Aggregated usage for a single day."""

    date: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    estimated_cost: float = 0.0
    models: dict[str, int] = field(default_factory=dict)


class UsageTracker:
    """Tracks LLM token usage with in-memory accumulation and JSONL persistence."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self._records: list[UsageRecord] = []

    def record(self, rec: UsageRecord) -> None:
        """Append a usage record to memory and flush to JSONL."""
        self._records.append(rec)
        self._flush(rec)

    def record_from_response(
        self,
        *,
        usage: dict[str, int],
        session_key: str,
        model: str,
        duration_ms: int | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Build and record a UsageRecord from a provider's usage dict."""
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        rec = UsageRecord(
            timestamp=datetime.now(UTC).isoformat(),
            session_key=session_key,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            cache_creation_tokens=usage.get("cache_creation_tokens", 0),
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            tool_name=tool_name,
            duration_ms=duration_ms,
        )
        self.record(rec)

    def get_session_totals(self, session_key: str) -> SessionUsage:
        """Aggregate usage for a session from in-memory records."""
        totals = SessionUsage(session_key=session_key)
        for rec in self._records:
            if rec.session_key != session_key:
                continue
            totals.prompt_tokens += rec.prompt_tokens
            totals.completion_tokens += rec.completion_tokens
            totals.total_tokens += rec.total_tokens
            totals.cache_creation_tokens += rec.cache_creation_tokens
            totals.cache_read_tokens += rec.cache_read_tokens
            totals.llm_calls += 1
            if rec.duration_ms is not None:
                totals.total_duration_ms += rec.duration_ms
        return totals

    def get_daily_totals(self, date: str) -> DailyUsage:
        """Aggregate usage for a date (YYYY-MM-DD) from in-memory records."""
        totals = DailyUsage(date=date)
        for rec in self._all_records_for_date(date):
            totals.prompt_tokens += rec.prompt_tokens
            totals.completion_tokens += rec.completion_tokens
            totals.total_tokens += rec.total_tokens
            totals.llm_calls += 1
            totals.models[rec.model] = totals.models.get(rec.model, 0) + 1
        return totals

    def get_all_records(
        self,
        *,
        since: datetime | None = None,
        limit: int = 0,
    ) -> list[UsageRecord]:
        """Return records, optionally filtered by time and capped."""
        records = self._load_all()
        if since is not None:
            cutoff = since.isoformat()
            records = [r for r in records if r.timestamp >= cutoff]
        if limit > 0:
            records = records[-limit:]
        return records

    def _flush(self, rec: UsageRecord) -> None:
        """Append a single record to the JSONL file."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rec), default=str) + "\n")
        except OSError as exc:
            logger.warning(f"Failed to write usage record: {exc}")

    def _all_records_for_date(self, date: str) -> list[UsageRecord]:
        """Return all records (memory + disk) matching a date prefix."""
        all_recs = self._load_all()
        return [r for r in all_recs if r.timestamp.startswith(date)]

    def _load_all(self) -> list[UsageRecord]:
        """Load all records from disk and merge with in-memory records."""
        disk: list[UsageRecord] = []
        if self._log_path.exists():
            try:
                for line in self._log_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    disk.append(UsageRecord(**data))
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                logger.warning(f"Failed to read usage log: {exc}")
        # In-memory records are already flushed, so disk should contain them.
        # But in case of flush failures, merge by returning disk records.
        return disk if disk else list(self._records)

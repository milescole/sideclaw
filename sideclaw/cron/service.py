"""Persisted cron scheduling for SideClaw."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from croniter import croniter
from loguru import logger
from pydantic import BaseModel, Field

from sideclaw.utils.files import atomic_write_text

_INTERVAL_RE = re.compile(r"^(\d+)(m|h|d)$")


def utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _ensure_aware(dt: datetime) -> datetime:
    """Assume naive datetimes are UTC and return timezone-aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _interval_to_cron(interval: str) -> str:
    """Convert an interval shorthand like '30m', '2h', '1d' to a cron expression."""
    match = _INTERVAL_RE.match(interval.strip())
    if not match:
        msg = f"Invalid interval format: {interval} (expected e.g. 30m, 2h, 1d)"
        raise ValueError(msg)
    amount, unit = int(match.group(1)), match.group(2)
    if amount < 1:
        msg = f"Interval amount must be at least 1: {interval}"
        raise ValueError(msg)
    if unit == "m":
        return f"*/{amount} * * * *"
    if unit == "h":
        return f"0 */{amount} * * *"
    return f"0 0 */{amount} * *"


class CronJob(BaseModel):
    """A persisted scheduled prompt delivery."""

    job_id: str
    schedule: str
    prompt: str
    channel: str
    chat_id: str
    enabled: bool = True
    name: str | None = None
    interval: str | None = None
    run_at: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_run_at: datetime | None = None
    last_error: str | None = None


class CronStore(BaseModel):
    """Serialized cron job collection."""

    jobs: list[CronJob] = Field(default_factory=list)


CronExecutor = Callable[[CronJob], Awaitable[None]]


class CronService:
    """Load, persist, and execute scheduled jobs."""

    def __init__(self, store_path: Path, *, poll_interval_seconds: int = 30) -> None:
        if poll_interval_seconds < 1:
            msg = "poll_interval_seconds must be at least 1"
            raise ValueError(msg)

        self._store_path = Path(store_path)
        self._poll_interval_seconds = poll_interval_seconds
        self._jobs: dict[str, CronJob] = {}
        self._task: asyncio.Task[None] | None = None
        self._load()

    def list_jobs(self) -> list[CronJob]:
        """Return jobs ordered by next run time."""
        return sorted(
            self._jobs.values(),
            key=lambda job: (
                self.next_run_at(job) is None,
                self.next_run_at(job) or datetime.max.replace(tzinfo=UTC),
                job.job_id,
            ),
        )

    def get_job(self, job_id: str) -> CronJob | None:
        """Return a single job by ID."""
        return self._jobs.get(job_id)

    def add_job(
        self,
        *,
        schedule: str | None = None,
        prompt: str,
        channel: str,
        chat_id: str,
        name: str | None = None,
        interval: str | None = None,
        run_at: str | None = None,
    ) -> CronJob:
        """Create and persist a new cron job."""
        provided = sum(x is not None for x in (schedule, interval, run_at))
        if provided != 1:
            msg = "Exactly one of schedule, interval, or run_at must be provided"
            raise ValueError(msg)

        resolved_interval: str | None = None

        if run_at:
            try:
                datetime.fromisoformat(run_at)
            except ValueError as exc:
                msg = f"Invalid run_at datetime: {run_at}"
                raise ValueError(msg) from exc
            resolved_schedule = "once"
        elif interval:
            resolved_schedule = _interval_to_cron(interval)
            resolved_interval = interval
        else:
            resolved_schedule = schedule or ""
            self._validate_schedule(resolved_schedule)

        now = utcnow()
        job = CronJob(
            job_id=uuid4().hex[:12],
            schedule=resolved_schedule,
            prompt=prompt,
            channel=channel,
            chat_id=chat_id,
            name=name.strip() if name else None,
            interval=resolved_interval,
            run_at=run_at,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        self._save()
        return job

    def remove_job(self, job_id: str) -> bool:
        """Delete a cron job by ID."""
        removed = self._jobs.pop(job_id, None)
        if removed is None:
            return False
        self._save()
        return True

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        """Enable or disable a persisted job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = enabled
        job.updated_at = utcnow()
        self._save()
        return True

    def next_run_at(self, job: CronJob) -> datetime | None:
        """Return the next scheduled run time for a job."""
        if not job.enabled:
            return None

        if job.run_at:
            if job.last_run_at is not None:
                return None
            return _ensure_aware(datetime.fromisoformat(job.run_at))

        base = _ensure_aware(job.last_run_at or job.created_at)
        next_run = croniter(job.schedule, base).get_next(datetime)
        return _ensure_aware(next_run).astimezone(UTC)

    async def run_due(
        self,
        executor: CronExecutor,
        *,
        now: datetime | None = None,
    ) -> list[CronJob]:
        """Execute all jobs that are due as of now."""
        as_of = _ensure_aware(now or utcnow())

        due_jobs = [
            job
            for job in self.list_jobs()
            if (next_run := self.next_run_at(job)) and next_run <= as_of
        ]
        completed: list[CronJob] = []

        for job in due_jobs:
            ok = await self._execute_job(job, executor, as_of=as_of)
            if ok:
                completed.append(job)

        return completed

    async def fire_job(self, job_id: str, executor: CronExecutor) -> CronJob | None:
        """Manually trigger a single job through the standard execution path."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        await self._execute_job(job, executor, as_of=utcnow())
        return job

    async def _execute_job(
        self,
        job: CronJob,
        executor: CronExecutor,
        *,
        as_of: datetime,
    ) -> bool:
        """Run a single job and persist state. Return True on success."""
        try:
            await executor(job)
        except Exception as exc:  # noqa: BLE001
            job.last_error = str(exc)
            job.updated_at = utcnow()
            logger.exception("Cron job {} failed", job.job_id)
            return False
        else:
            job.last_run_at = as_of
            job.last_error = None
            job.updated_at = utcnow()
            if job.run_at:
                job.enabled = False
            return True
        finally:
            self._save()

    async def start(self, executor: CronExecutor) -> None:
        """Start the background scheduler loop."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(executor))

    async def stop(self) -> None:
        """Stop the background scheduler loop."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run_loop(self, executor: CronExecutor) -> None:
        """Run due jobs on a fixed polling interval."""
        while True:
            await self.run_due(executor)
            await asyncio.sleep(self._poll_interval_seconds)

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        store = CronStore.model_validate_json(self._store_path.read_text(encoding="utf-8"))
        self._jobs = {job.job_id: job for job in store.jobs}

    def _save(self) -> None:
        store = CronStore(jobs=list(self._jobs.values()))
        atomic_write_text(
            self._store_path,
            store.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _validate_schedule(schedule: str) -> None:
        if not croniter.is_valid(schedule):
            msg = f"Invalid cron schedule: {schedule}"
            raise ValueError(msg)

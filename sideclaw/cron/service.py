"""Persisted cron scheduling for SideClaw."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from croniter import croniter
from loguru import logger
from pydantic import BaseModel, Field

from sideclaw.utils.files import atomic_write_text


def utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


class CronJob(BaseModel):
    """A persisted scheduled prompt delivery."""

    job_id: str
    schedule: str
    prompt: str
    channel: str
    chat_id: str
    enabled: bool = True
    name: str | None = None
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
        schedule: str,
        prompt: str,
        channel: str,
        chat_id: str,
        name: str | None = None,
    ) -> CronJob:
        """Create and persist a new cron job."""
        self._validate_schedule(schedule)
        now = utcnow()
        job = CronJob(
            job_id=uuid4().hex[:12],
            schedule=schedule,
            prompt=prompt,
            channel=channel,
            chat_id=chat_id,
            name=name.strip() if name else None,
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

        base = job.last_run_at or job.created_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        next_run = croniter(job.schedule, base).get_next(datetime)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)
        return next_run.astimezone(UTC)

    async def run_due(
        self,
        executor: CronExecutor,
        *,
        now: datetime | None = None,
    ) -> list[CronJob]:
        """Execute all jobs that are due as of now."""
        as_of = now or utcnow()
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)

        due_jobs = [
            job
            for job in self.list_jobs()
            if (next_run := self.next_run_at(job)) and next_run <= as_of
        ]
        completed: list[CronJob] = []

        for job in due_jobs:
            try:
                await executor(job)
            except Exception as exc:  # noqa: BLE001
                job.last_error = str(exc)
                job.updated_at = utcnow()
                logger.exception("Cron job {} failed", job.job_id)
            else:
                job.last_run_at = as_of
                job.last_error = None
                job.updated_at = utcnow()
                completed.append(job)
            finally:
                self._save()

        return completed

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

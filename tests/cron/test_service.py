from datetime import UTC, datetime

import pytest

from sideclaw.cron import CronService


def test_add_job_persists_to_store(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="0 9 * * *",
        prompt="Morning summary",
        channel="telegram",
        chat_id="123",
        name="daily-summary",
    )

    reloaded = CronService(tmp_path / "jobs.json")
    stored = reloaded.get_job(job.job_id)

    assert stored is not None
    assert stored.prompt == "Morning summary"
    assert stored.channel == "telegram"
    assert stored.chat_id == "123"
    assert stored.name == "daily-summary"


def test_add_job_rejects_invalid_schedule(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")

    with pytest.raises(ValueError, match="Invalid cron schedule"):
        service.add_job(
            schedule="not a cron",
            prompt="Bad schedule",
            channel="telegram",
            chat_id="123",
        )


async def test_run_due_executes_matching_jobs(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="*/5 * * * *",
        prompt="Run this",
        channel="telegram",
        chat_id="123",
    )
    job.created_at = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)

    executed: list[str] = []

    async def executor(current_job) -> None:
        executed.append(current_job.job_id)

    completed = await service.run_due(
        executor,
        now=datetime(2026, 3, 10, 9, 5, tzinfo=UTC),
    )

    assert [item.job_id for item in completed] == [job.job_id]
    reloaded = CronService(tmp_path / "jobs.json")
    stored = reloaded.get_job(job.job_id)
    assert stored is not None
    assert stored.last_run_at == datetime(2026, 3, 10, 9, 5, tzinfo=UTC)
    assert stored.last_error is None
    assert executed == [job.job_id]


async def test_run_due_records_executor_error(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="* * * * *",
        prompt="Fails",
        channel="telegram",
        chat_id="123",
    )
    job.created_at = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)

    async def executor(_job) -> None:
        msg = "delivery failed"
        raise RuntimeError(msg)

    completed = await service.run_due(
        executor,
        now=datetime(2026, 3, 10, 9, 1, tzinfo=UTC),
    )

    assert completed == []
    stored = CronService(tmp_path / "jobs.json").get_job(job.job_id)
    assert stored is not None
    assert stored.last_run_at is None
    assert stored.last_error == "delivery failed"


def test_next_run_at_returns_none_when_disabled(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="0 9 * * *",
        prompt="Morning summary",
        channel="telegram",
        chat_id="123",
    )

    service.set_enabled(job.job_id, False)
    disabled = service.get_job(job.job_id)

    assert disabled is not None
    assert service.next_run_at(disabled) is None

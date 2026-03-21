from datetime import UTC, datetime

import pytest

from sideclaw.cron import CronService
from sideclaw.cron.service import _interval_to_cron


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


def test_interval_to_cron_minutes() -> None:
    assert _interval_to_cron("30m") == "*/30 * * * *"


def test_interval_to_cron_hours() -> None:
    assert _interval_to_cron("2h") == "0 */2 * * *"


def test_interval_to_cron_days() -> None:
    assert _interval_to_cron("1d") == "0 0 */1 * *"


def test_interval_to_cron_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid interval"):
        _interval_to_cron("abc")


def test_interval_to_cron_rejects_zero() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        _interval_to_cron("0m")


def test_add_job_with_interval(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        interval="30m",
        prompt="check in",
        channel="telegram",
        chat_id="123",
    )
    assert job.schedule == "*/30 * * * *"
    assert job.interval == "30m"


def test_one_shot_fires_once(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        run_at="2026-03-22T09:00:00+00:00",
        prompt="one-time",
        channel="telegram",
        chat_id="123",
    )
    assert job.run_at == "2026-03-22T09:00:00+00:00"
    next_run = service.next_run_at(job)
    assert next_run is not None
    assert next_run.isoformat() == "2026-03-22T09:00:00+00:00"


async def test_one_shot_auto_disables(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        run_at="2026-03-22T09:00:00+00:00",
        prompt="one-time",
        channel="telegram",
        chat_id="123",
    )

    executed: list[str] = []

    async def executor(current_job) -> None:
        executed.append(current_job.job_id)

    completed = await service.run_due(
        executor,
        now=datetime(2026, 3, 22, 9, 1, tzinfo=UTC),
    )
    assert len(completed) == 1

    reloaded = CronService(tmp_path / "jobs.json")
    stored = reloaded.get_job(job.job_id)
    assert stored is not None
    assert stored.enabled is False


async def test_one_shot_next_run_none_after_fired(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        run_at="2026-03-22T09:00:00+00:00",
        prompt="one-time",
        channel="telegram",
        chat_id="123",
    )

    async def executor(_job) -> None:
        pass

    await service.run_due(executor, now=datetime(2026, 3, 22, 9, 1, tzinfo=UTC))

    reloaded = CronService(tmp_path / "jobs.json")
    stored = reloaded.get_job(job.job_id)
    assert stored is not None
    assert reloaded.next_run_at(stored) is None


async def test_fire_job_executes_and_records_state(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="0 9 * * *",
        prompt="fire me",
        channel="telegram",
        chat_id="123",
    )

    executed: list[str] = []

    async def executor(current_job) -> None:
        executed.append(current_job.job_id)

    result = await service.fire_job(job.job_id, executor)
    assert result.job_id == job.job_id
    assert executed == [job.job_id]

    reloaded = CronService(tmp_path / "jobs.json")
    stored = reloaded.get_job(job.job_id)
    assert stored is not None
    assert stored.last_run_at is not None
    assert stored.last_error is None


async def test_fire_job_returns_none_for_unknown_id(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")

    async def executor(_job) -> None:
        pass

    result = await service.fire_job("nope", executor)
    assert result is None


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

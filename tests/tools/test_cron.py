from datetime import UTC, datetime

from sideclaw.cron import CronService
from sideclaw.runtime.context import (
    ToolRuntimeContext,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)
from sideclaw.tools.cron import CronTool


async def test_cron_tool_adds_job_for_current_chat(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    tool = CronTool(service)
    token = set_tool_runtime_context(
        ToolRuntimeContext(
            channel="telegram",
            chat_id="123",
            sender_id="42",
            session_key="telegram:123",
        )
    )

    try:
        result = await tool.execute(
            action="add",
            prompt="Send me a new meal plan",
            schedule="0 21 * * 5",
            name="weekly meal plan",
        )
    finally:
        reset_tool_runtime_context(token)

    jobs = service.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].channel == "telegram"
    assert jobs[0].chat_id == "123"
    assert jobs[0].schedule == "0 21 * * 5"
    assert "Created cron job" in result


async def test_cron_tool_lists_jobs_for_current_chat_only(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    service.add_job(
        schedule="0 21 * * 5",
        prompt="Meal plan",
        channel="telegram",
        chat_id="123",
        name="meal plan",
    )
    service.add_job(
        schedule="0 9 * * 1",
        prompt="Other chat",
        channel="telegram",
        chat_id="999",
        name="other",
    )
    tool = CronTool(service)
    token = set_tool_runtime_context(
        ToolRuntimeContext(
            channel="telegram",
            chat_id="123",
            sender_id="42",
            session_key="telegram:123",
        )
    )

    try:
        result = await tool.execute(action="list")
    finally:
        reset_tool_runtime_context(token)

    assert "meal plan" in result
    assert "other" not in result


async def test_cron_tool_blocks_nested_scheduling(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    tool = CronTool(service)
    token = tool.set_cron_context(True)

    try:
        result = await tool.execute(
            action="add",
            prompt="Send me a new meal plan",
            schedule="0 21 * * 5",
        )
    finally:
        tool.reset_cron_context(token)

    assert result == "Error: cannot schedule new jobs from within a cron job execution"


def test_cron_service_next_run_for_friday_night(tmp_path) -> None:
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        schedule="0 21 * * 5",
        prompt="Send me a new meal plan",
        channel="telegram",
        chat_id="123",
    )
    job.created_at = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)

    next_run = service.next_run_at(job)

    assert next_run is not None
    assert next_run.weekday() == 4
    assert next_run.hour == 21

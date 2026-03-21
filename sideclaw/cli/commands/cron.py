"""Cron CLI surface."""

import typer

from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import (
    format_cron_history_row,
    format_cron_row,
    format_cron_timestamp,
    format_error_message,
    format_heading,
    format_success_message,
)
from sideclaw.config.loader import get_config_path, load_config
from sideclaw.cron import cron_store_path


def cron_list() -> None:
    """List persisted cron jobs."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    jobs = service.list_jobs()

    if not jobs:
        print_line("[dim]No cron jobs configured.[/dim]")
        return

    print_line(format_heading("Cron Jobs"))
    for job in jobs:
        print_line(
            format_cron_row(
                job_id=job.job_id,
                name=job.name or "-",
                schedule=job.schedule,
                target=f"{job.channel}:{job.chat_id}",
                enabled=job.enabled,
                next_run=format_cron_timestamp(service.next_run_at(job)),
                last_run=format_cron_timestamp(job.last_run_at),
                last_error=job.last_error or "-",
            )
        )


def cron_add(
    schedule: str | None,
    prompt: str,
    channel: str,
    chat_id: str,
    name: str | None,
    every: str | None = None,
    at: str | None = None,
) -> None:
    """Add a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))

    try:
        job = service.add_job(
            schedule=schedule,
            prompt=prompt,
            channel=channel,
            chat_id=chat_id,
            name=name,
            interval=every,
            run_at=at,
        )
    except ValueError as exc:
        print_line(format_error_message(str(exc)))
        raise typer.Exit(1) from exc

    print_line(format_success_message(f"Added cron job {job.job_id}"))


def cron_remove(job_id: str) -> None:
    """Remove a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.remove_job(job_id):
        print_line(format_error_message(f"Cron job not found: {job_id}"))
        raise typer.Exit(1)
    print_line(format_success_message(f"Removed cron job {job_id}"))


def cron_enable(job_id: str) -> None:
    """Enable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, True):
        print_line(format_error_message(f"Cron job not found: {job_id}"))
        raise typer.Exit(1)
    print_line(format_success_message(f"Enabled cron job {job_id}"))


def cron_disable(job_id: str) -> None:
    """Disable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, False):
        print_line(format_error_message(f"Cron job not found: {job_id}"))
        raise typer.Exit(1)
    print_line(format_success_message(f"Disabled cron job {job_id}"))


def cron_history(job_id: str | None = None, limit: int = 20) -> None:
    """Show cron execution history."""
    from sideclaw.cron import CronHistory, CronService

    config = load_config(get_config_path())
    history = CronHistory(config.workspace_path / "cron" / "history.jsonl")
    service = CronService(cron_store_path(config.workspace_path), history=history)
    entries = service.get_history(job_id=job_id, limit=limit)

    if not entries:
        print_line("[dim]No cron execution history.[/dim]")
        return

    print_line(format_heading("Cron History"))
    for entry in entries:
        print_line(
            format_cron_history_row(
                started_at=entry.started_at,
                job_id=entry.job_id,
                job_name=entry.job_name,
                status=entry.status,
                duration_ms=entry.duration_ms,
                error=entry.error,
            )
        )


def cron_fire(job_id: str) -> None:
    """Manually fire a cron job."""
    import asyncio

    from sideclaw.app.cli import build_cli_runtime
    from sideclaw.cron import CronJob
    from sideclaw.runtime.models.requests import RunRequest, RunTrigger

    config = load_config(get_config_path())
    runtime = build_cli_runtime(config)

    async def _executor(job: CronJob) -> None:
        result = await runtime.runtime_service.run(
            RunRequest(
                input_text=job.prompt,
                surface=job.channel,
                conversation_id=job.chat_id,
                user_id="cron",
                trigger=RunTrigger.scheduled,
            )
        )
        print_line(result.output_text)

    result = asyncio.run(runtime.cron_service.fire_job(job_id, _executor))
    if result is None:
        print_line(format_error_message(f"Cron job not found: {job_id}"))
        raise typer.Exit(1)

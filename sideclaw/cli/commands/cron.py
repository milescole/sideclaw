"""Cron CLI surface."""

import typer
from rich.console import Console

from sideclaw.config.loader import get_config_path, load_config
from sideclaw.cron import cron_store_path

console = Console()


def _format_timestamp(value: object) -> str:
    """Render a timestamp for CLI output."""
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def cron_list() -> None:
    """List persisted cron jobs."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    jobs = service.list_jobs()

    if not jobs:
        console.print("[dim]No cron jobs configured.[/dim]")
        return

    console.print("[bold]Cron Jobs[/bold]")
    for job in jobs:
        console.print(
            " | ".join(
                [
                    job.job_id,
                    job.name or "-",
                    job.schedule,
                    f"{job.channel}:{job.chat_id}",
                    f"enabled={'yes' if job.enabled else 'no'}",
                    f"next={_format_timestamp(service.next_run_at(job))}",
                    f"last={_format_timestamp(job.last_run_at)}",
                    f"error={job.last_error or '-'}",
                ]
            )
        )


def cron_add(
    schedule: str,
    prompt: str,
    channel: str,
    chat_id: str,
    name: str | None,
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
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]Added cron job {job.job_id}[/green]")


def cron_remove(job_id: str) -> None:
    """Remove a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.remove_job(job_id):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Removed cron job {job_id}[/green]")


def cron_enable(job_id: str) -> None:
    """Enable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, True):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Enabled cron job {job_id}[/green]")


def cron_disable(job_id: str) -> None:
    """Disable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, False):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Disabled cron job {job_id}[/green]")

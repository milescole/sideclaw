"""CLI entry points for SideClaw."""

import typer

from sideclaw.cli.commands.agent import agent as agent_command
from sideclaw.cli.commands.cron import (
    cron_add as cron_add_command,
)
from sideclaw.cli.commands.cron import (
    cron_disable as cron_disable_command,
)
from sideclaw.cli.commands.cron import (
    cron_enable as cron_enable_command,
)
from sideclaw.cli.commands.cron import (
    cron_list as cron_list_command,
)
from sideclaw.cli.commands.cron import (
    cron_remove as cron_remove_command,
)
from sideclaw.cli.commands.gateway import gateway as gateway_command
from sideclaw.cli.commands.onboard import onboard as onboard_command
from sideclaw.cli.commands.status import status as status_command
from sideclaw.utils.redact import configure_logging

app = typer.Typer(name="sideclaw", help="Lightweight AI assistant framework")
cron_app = typer.Typer(help="Manage scheduled jobs")


@app.callback()
def _startup() -> None:
    configure_logging()


@app.command()
def onboard() -> None:
    """Set up SideClaw for the first time."""
    onboard_command()


@app.command()
def status() -> None:
    """Show SideClaw status."""
    status_command()


@app.command()
def agent(
    message: str | None = typer.Option(
        None, "--message", "-m", help="Single message (non-interactive)"
    ),
) -> None:
    """Run the agent in CLI mode."""
    agent_command(message)


@app.command()
def gateway() -> None:
    """Run as a long-running gateway with all enabled channels."""
    gateway_command()


@cron_app.command("list")
def cron_list() -> None:
    """List persisted cron jobs."""
    cron_list_command()


@cron_app.command("add")
def cron_add(
    schedule: str = typer.Option(..., help="Cron expression, for example '0 9 * * *'"),
    prompt: str = typer.Option(..., help="Prompt to send when the job fires"),
    channel: str = typer.Option(..., help="Target channel name, for example 'telegram'"),
    chat_id: str = typer.Option(..., help="Target chat ID for delivery"),
    name: str | None = typer.Option(None, help="Optional human-readable job name"),
) -> None:
    """Add a persisted cron job."""
    cron_add_command(
        schedule=schedule,
        prompt=prompt,
        channel=channel,
        chat_id=chat_id,
        name=name,
    )


@cron_app.command("remove")
def cron_remove(job_id: str) -> None:
    """Remove a persisted cron job."""
    cron_remove_command(job_id)


@cron_app.command("enable")
def cron_enable(job_id: str) -> None:
    """Enable a persisted cron job."""
    cron_enable_command(job_id)


@cron_app.command("disable")
def cron_disable(job_id: str) -> None:
    """Disable a persisted cron job."""
    cron_disable_command(job_id)


app.add_typer(cron_app, name="cron")

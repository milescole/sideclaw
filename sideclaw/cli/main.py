"""CLI entry points for SideClaw."""

import importlib.metadata

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
from sideclaw.cli.commands.sessions import (
    sessions_delete as sessions_delete_command,
)
from sideclaw.cli.commands.sessions import (
    sessions_list as sessions_list_command,
)
from sideclaw.cli.commands.sessions import (
    sessions_rename as sessions_rename_command,
)
from sideclaw.cli.commands.sessions import (
    sessions_show as sessions_show_command,
)
from sideclaw.cli.commands.gateway import gateway as gateway_command
from sideclaw.cli.commands.memory import memory_show as memory_show_command
from sideclaw.cli.commands.memory import memory_usage as memory_usage_command
from sideclaw.cli.commands.onboard import onboard as onboard_command
from sideclaw.cli.commands.status import status as status_command
from sideclaw.utils.redact import configure_logging

app = typer.Typer(name="sideclaw", help="Lightweight AI assistant framework")
cron_app = typer.Typer(help="Manage scheduled jobs")
sessions_app = typer.Typer(help="Manage conversation sessions")
memory_app = typer.Typer(help="Inspect memory files and token budgets")


def _version_callback(value: bool) -> None:
    if value:
        version = importlib.metadata.version("sideclaw")
        typer.echo(f"sideclaw {version}")
        raise typer.Exit()


@app.callback()
def _startup(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
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


@sessions_app.command("list")
def sessions_list() -> None:
    """List all sessions."""
    sessions_list_command()


@sessions_app.command("show")
def sessions_show(key: str) -> None:
    """Show details for a session."""
    sessions_show_command(key)


@sessions_app.command("rename")
def sessions_rename(key: str, title: str) -> None:
    """Set a user-defined title for a session."""
    sessions_rename_command(key, title)


@sessions_app.command("delete")
def sessions_delete(key: str) -> None:
    """Delete a session by key."""
    sessions_delete_command(key)


app.add_typer(sessions_app, name="sessions")


@memory_app.command("show")
def memory_show() -> None:
    """Display memory file contents and sizes."""
    memory_show_command()


@memory_app.command("usage")
def memory_usage() -> None:
    """Display per-file token usage against the context budget."""
    memory_usage_command()


app.add_typer(memory_app, name="memory")

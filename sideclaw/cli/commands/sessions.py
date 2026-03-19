"""Session management CLI commands — thin dispatch to SessionManager."""

from datetime import datetime

import typer

from sideclaw.config.loader import get_config_path, load_config
from sideclaw.session.manager import SessionManager


def _get_session_manager() -> SessionManager:
    config = load_config(get_config_path())
    return SessionManager(config.workspace_path / "sessions")


def _format_timestamp(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def sessions_list() -> None:
    """List all sessions."""
    manager = _get_session_manager()
    sessions = manager.list_sessions()

    if not sessions:
        typer.echo("No sessions found.")
        return

    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

    for entry in sessions:
        key = entry.get("key", "?")
        title = entry.get("title") or "(untitled)"
        count = entry.get("message_count", 0)
        updated = _format_timestamp(entry.get("updated_at", ""))
        typer.echo(f"  {key:<30} {title:<40} {count:>4} msgs  {updated}")


def sessions_show(key: str) -> None:
    """Show details for a single session."""
    manager = _get_session_manager()
    entry = manager.get_session_info(key)
    if entry is None:
        typer.echo(f"Session not found: {key}")
        raise typer.Exit(1)

    typer.echo(f"  Key:               {key}")
    typer.echo(f"  Title:             {entry.get('title') or '(untitled)'} ({entry.get('title_source', 'auto')})")
    typer.echo(f"  Messages:          {entry.get('message_count', 0)}")
    typer.echo(f"  Created:           {entry.get('created_at', '')}")
    typer.echo(f"  Updated:           {entry.get('updated_at', '')}")
    typer.echo(f"  Last Consolidated: {entry.get('last_consolidated', 0)}")


def sessions_rename(key: str, title: str) -> None:
    """Set a user-defined title for a session."""
    manager = _get_session_manager()
    if manager.rename(key, title):
        typer.echo(f"Renamed session {key} to: {title}")
    else:
        typer.echo(f"Session not found: {key}")
        raise typer.Exit(1)


def sessions_delete(key: str) -> None:
    """Delete a session by key."""
    manager = _get_session_manager()
    if manager.delete(key):
        typer.echo(f"Deleted session: {key}")
    else:
        typer.echo(f"Session not found: {key}")
        raise typer.Exit(1)

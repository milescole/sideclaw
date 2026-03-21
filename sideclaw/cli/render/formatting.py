"""Pure CLI formatting helpers."""

from collections.abc import Sequence

from rich.markdown import Markdown


def format_heading(text: str) -> str:
    """Format a CLI heading."""
    return f"[bold]{text}[/bold]"


def format_success_message(text: str) -> str:
    """Format a success message."""
    return f"[green]{text}[/green]"


def format_warning_message(text: str) -> str:
    """Format a warning message."""
    return f"[yellow]{text}[/yellow]"


def format_error_message(text: str) -> str:
    """Format an error message."""
    return f"[red]{text}[/red]"


def format_session_reset_message() -> str:
    """Format the session-reset notice."""
    return "[dim]Session reset.[/dim]"


def format_exit_message() -> str:
    """Format the interactive agent exit message."""
    return "Bye!"


def format_web_search_status(provider: object | None, api_key: str | None) -> str:
    """Format the web-search status line."""
    if provider is None or not api_key:
        return "Web search: [dim]not configured[/dim]"

    provider_name = getattr(provider, "value", provider)
    return f"Web search: [green]configured[/green] ({provider_name})"


def format_shell_exec_status(enabled: bool) -> str:
    """Format the shell-exec status line."""
    state = "enabled" if enabled else "disabled"
    return f"Shell exec: {state} (trusted local deployments only)"


def format_image_generation_status(
    api_key: str | None, model: str, upscaling_enabled: bool
) -> str:
    """Format the image-generation status line."""
    if not api_key:
        return "Image generation: [dim]disabled[/dim]"
    upscaling = "upscaling on" if upscaling_enabled else "upscaling off"
    return f"Image generation: [green]configured[/green] ({model}; {upscaling})"


def format_browser_status(enabled: bool) -> str:
    """Format the browser automation status line."""
    state = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
    return f"Browser automation: {state}"


def format_tts_status(enabled: bool, provider: str) -> str:
    """Format the text-to-speech status line."""
    if not enabled:
        return "Text-to-speech: [dim]disabled[/dim]"
    return f"Text-to-speech: [green]enabled[/green] ({provider})"


def format_telegram_status(configured: bool) -> str:
    """Format the Telegram status line."""
    state = "[green]configured[/green]" if configured else "[dim]not configured[/dim]"
    return f"Telegram: {state}"


def format_created_file_line(relative_path: str) -> str:
    """Format a created-file notice."""
    return f"  Created {relative_path}"


def build_clarify_lines(question: str, choices: Sequence[str] | None) -> list[str]:
    """Build the clarify prompt lines for interactive CLI mode."""
    lines = ["", f"[bold yellow]Clarify[/bold yellow] {question}"]
    if choices:
        lines.extend(f"  {index}. {choice}" for index, choice in enumerate(choices, start=1))
        lines.append("  0. Other")
    return lines


def build_agent_header_lines(model: str) -> list[str]:
    """Build the interactive agent header."""
    return [
        "[bold green]SideClaw Agent[/bold green] (type 'exit' to quit, '/new' to reset)",
        f"Model: {model}",
        "",
    ]


def format_gateway_header() -> str:
    """Format the gateway startup header."""
    return "[bold green]SideClaw Gateway[/bold green]"


def format_gateway_model_line(model: str) -> str:
    """Format the gateway model line."""
    return f"Model: {model}"


def format_gateway_channels_line(channel_names: Sequence[str]) -> str:
    """Format the gateway channels summary line."""
    return f"Channels: {', '.join(channel_names)}"


def render_agent_markdown(text: str) -> Markdown:
    """Build the markdown renderable for agent responses."""
    return Markdown(text)


def format_provider_key_status(provider_name: str, api_key: str | None) -> str:
    """Format a provider API key status line with masking."""
    if not api_key:
        return f"{provider_name}: [dim]not configured[/dim]"
    masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    return f"{provider_name}: [green]configured[/green] ({masked})"


def format_session_count(count: int) -> str:
    """Format the session count status line."""
    return f"Sessions: {count}"


def format_cron_summary(total: int, enabled: int, next_run: str) -> str:
    """Format the cron jobs summary status line."""
    return f"Cron jobs: {total} total, {enabled} enabled, next run: {next_run}"


def format_cron_timestamp(value: object) -> str:
    """Render a timestamp for CLI output."""
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def format_cron_row(
    *,
    job_id: str,
    name: str,
    schedule: str,
    target: str,
    enabled: bool,
    next_run: str,
    last_run: str,
    last_error: str,
) -> str:
    """Format a cron-job row for CLI output."""
    return " | ".join(
        [
            job_id,
            name,
            schedule,
            target,
            f"enabled={'yes' if enabled else 'no'}",
            f"next={next_run}",
            f"last={last_run}",
            f"error={last_error}",
        ]
    )

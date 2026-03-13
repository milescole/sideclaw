from datetime import UTC, datetime

from rich.markdown import Markdown

from sideclaw.cli.render.console import get_console
from sideclaw.cli.render.formatting import (
    build_agent_header_lines,
    build_clarify_lines,
    format_browser_status,
    format_created_file_line,
    format_cron_row,
    format_cron_timestamp,
    format_error_message,
    format_exit_message,
    format_gateway_channels_line,
    format_gateway_header,
    format_gateway_model_line,
    format_heading,
    format_image_generation_status,
    format_openrouter_status,
    format_session_reset_message,
    format_shell_exec_status,
    format_success_message,
    format_telegram_status,
    format_tts_status,
    format_warning_message,
    format_web_search_status,
    render_agent_markdown,
)


def test_get_console_returns_shared_console() -> None:
    assert get_console() is get_console()


def test_format_heading_wraps_bold_markup() -> None:
    assert format_heading("SideClaw Status") == "[bold]SideClaw Status[/bold]"


def test_message_helpers_apply_expected_colors() -> None:
    assert format_success_message("saved") == "[green]saved[/green]"
    assert format_warning_message("careful") == "[yellow]careful[/yellow]"
    assert format_error_message("boom") == "[red]boom[/red]"


def test_format_openrouter_status_masks_long_keys() -> None:
    status = format_openrouter_status("sk-or-v1-1234567890abcd")
    assert "configured" in status
    assert "sk-or-v1" in status
    assert "abcd" in status
    assert "1234567890abcd" not in status


def test_format_openrouter_status_handles_missing_key() -> None:
    assert "not configured" in format_openrouter_status(None)


def test_render_agent_markdown_returns_markdown() -> None:
    renderable = render_agent_markdown("**hello**")
    assert isinstance(renderable, Markdown)


def test_format_web_search_status_for_missing_key() -> None:
    assert "not configured" in format_web_search_status(None, None)


def test_format_web_search_status_uses_provider_value() -> None:
    class Provider:
        value = "brave"

    assert "brave" in format_web_search_status(Provider(), "key")


def test_format_shell_exec_status_handles_enabled_and_disabled() -> None:
    assert "enabled" in format_shell_exec_status(True)
    assert "disabled" in format_shell_exec_status(False)


def test_format_image_generation_status_handles_disabled() -> None:
    assert "disabled" in format_image_generation_status(None, "fal-ai/model", False)


def test_format_image_generation_status_handles_configured_model() -> None:
    status = format_image_generation_status("fal-key", "fal-ai/model", True)
    assert "configured" in status
    assert "fal-ai/model" in status
    assert "upscaling on" in status


def test_format_browser_status_uses_enabled_markup() -> None:
    assert "enabled" in format_browser_status(True)


def test_format_tts_status_handles_disabled() -> None:
    assert "disabled" in format_tts_status(False, "edge")


def test_format_tts_status_handles_enabled_provider() -> None:
    assert "edge" in format_tts_status(True, "edge")


def test_format_telegram_status_handles_configured_and_missing() -> None:
    assert "configured" in format_telegram_status(True)
    assert "not configured" in format_telegram_status(False)


def test_format_created_file_line_matches_cli_output_shape() -> None:
    assert format_created_file_line("docs/index.md") == "  Created docs/index.md"


def test_build_clarify_lines_includes_choices_and_other_option() -> None:
    lines = build_clarify_lines("Pick one", ["A", "B"])
    assert lines == [
        "",
        "[bold yellow]Clarify[/bold yellow] Pick one",
        "  1. A",
        "  2. B",
        "  0. Other",
    ]


def test_build_agent_header_lines_contains_model() -> None:
    assert build_agent_header_lines("openai/gpt-4o-mini") == [
        "[bold green]SideClaw Agent[/bold green] (type 'exit' to quit, '/new' to reset)",
        "Model: openai/gpt-4o-mini",
        "",
    ]


def test_format_session_reset_message_uses_dim_markup() -> None:
    assert format_session_reset_message() == "[dim]Session reset.[/dim]"


def test_format_exit_message_returns_bye() -> None:
    assert format_exit_message() == "Bye!"


def test_format_gateway_header_uses_green_heading() -> None:
    assert format_gateway_header() == "[bold green]SideClaw Gateway[/bold green]"


def test_format_gateway_model_line_includes_model() -> None:
    assert format_gateway_model_line("openai/gpt-4o-mini") == "Model: openai/gpt-4o-mini"


def test_format_gateway_channels_line_joins_channel_names() -> None:
    assert format_gateway_channels_line(["TelegramChannel", "SlackChannel"]) == (
        "Channels: TelegramChannel, SlackChannel"
    )


def test_format_cron_timestamp_handles_none() -> None:
    assert format_cron_timestamp(None) == "-"


def test_format_cron_timestamp_uses_isoformat_when_available() -> None:
    value = datetime(2026, 3, 12, 15, 30, tzinfo=UTC)
    assert format_cron_timestamp(value) == "2026-03-12T15:30:00+00:00"


def test_format_cron_row_contains_core_fields() -> None:
    row = format_cron_row(
        job_id="job-1",
        name="daily-summary",
        schedule="0 9 * * *",
        target="telegram:123",
        enabled=True,
        next_run="2026-03-12T09:00:00+00:00",
        last_run="-",
        last_error="-",
    )
    assert "job-1" in row
    assert "daily-summary" in row
    assert "enabled=yes" in row

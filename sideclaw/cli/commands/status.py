"""Status CLI surface."""

from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import (
    format_browser_status,
    format_heading,
    format_image_generation_status,
    format_openrouter_status,
    format_shell_exec_status,
    format_telegram_status,
    format_tts_status,
    format_web_search_status,
)
from sideclaw.config.loader import get_config_path, load_config


def status() -> None:
    """Show SideClaw status."""
    config_path = get_config_path()
    config = load_config(config_path)

    print_line(format_heading("SideClaw Status"))
    print_line(f"Config: {config_path} ({'exists' if config_path.exists() else 'not found'})")
    print_line(f"Workspace: {config.workspace_path}")
    print_line(f"Model: {config.agent.model}")
    print_line(format_shell_exec_status(config.tools.exec_enabled))
    print_line(
        format_web_search_status(config.tools.web_search_provider, config.tools.web_search_api_key)
    )
    print_line(
        format_image_generation_status(
            config.tools.fal_api_key,
            config.tools.fal_model,
            config.tools.fal_enable_upscaling,
        )
    )
    print_line(format_browser_status(config.tools.browser_enabled))
    print_line(format_tts_status(config.tools.tts.enabled, config.tools.tts.provider))
    print_line(
        format_openrouter_status(
            config.providers.openrouter.api_key if config.providers.openrouter else None
        )
    )
    print_line(format_telegram_status(config.channels.telegram is not None))

    # Usage tracking status
    if config.usage.track_usage:
        usage_path = config.workspace_path / config.usage.usage_log_path
        if usage_path.exists():
            line_count = sum(1 for _ in usage_path.open())
            print_line(f"Usage tracking: enabled ({line_count} records)")
        else:
            print_line("Usage tracking: enabled (no records yet)")
    else:
        print_line("Usage tracking: disabled")

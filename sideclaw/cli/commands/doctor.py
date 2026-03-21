"""Doctor diagnostics CLI surface."""

import json
import os

from pydantic import ValidationError

from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import (
    format_error_message,
    format_heading,
    format_success_message,
    format_warning_message,
)
from sideclaw.config.loader import get_config_path, load_config


def _check_pass(label: str) -> None:
    print_line(f"  {format_success_message('PASS')} {label}")


def _check_warn(label: str) -> None:
    print_line(f"  {format_warning_message('WARN')} {label}")


def _check_fail(label: str) -> None:
    print_line(f"  {format_error_message('FAIL')} {label}")


def doctor() -> None:
    """Run diagnostic checks."""
    print_line(format_heading("SideClaw Doctor"))

    # Config validity
    config_path = get_config_path()
    try:
        config = load_config(config_path)
        _check_pass(f"Config loads from {config_path}")
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        _check_fail(f"Config failed to load: {exc}")
        return

    # Workspace exists and writable
    workspace = config.workspace_path
    ws_exists = workspace.exists()
    if ws_exists:
        _check_pass(f"Workspace exists: {workspace}")
    else:
        _check_fail(f"Workspace missing: {workspace}")

    if ws_exists and os.access(workspace, os.W_OK):
        _check_pass("Workspace is writable")
    elif ws_exists:
        _check_fail("Workspace is not writable")

    # Provider keys
    has_provider = False
    _key_providers = [
        ("anthropic", "Anthropic API key present"),
        ("openai", "OpenAI API key present"),
        ("openrouter", "OpenRouter API key present"),
    ]
    for attr, label in _key_providers:
        provider = getattr(config.providers, attr, None)
        if provider and provider.api_key:
            _check_pass(label)
            has_provider = True

    if config.providers.ollama:
        _check_pass("Ollama configured")
        has_provider = True
    if not has_provider:
        _check_warn("No provider API keys configured")

    # Browser tool dependency
    if config.tools.browser_enabled:
        try:
            import playwright  # noqa: F401

            _check_pass("Playwright importable (browser enabled)")
        except ImportError:
            _check_warn("Playwright not installed but browser is enabled")
    else:
        _check_pass("Browser disabled (no Playwright check needed)")

    # Cron store
    from sideclaw.cron import CronService, cron_store_path

    store_path = cron_store_path(workspace)
    try:
        CronService(store_path)
        if store_path.exists():
            _check_pass("Cron store loads successfully")
        else:
            _check_pass("Cron store not yet created (OK)")
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        _check_fail(f"Cron store failed to load: {exc}")

"""Agent CLI surface."""

import asyncio
from typing import Any

import typer

from sideclaw.app.cli import build_cli_runtime
from sideclaw.cli.render.console import print_line, prompt_input
from sideclaw.cli.render.formatting import (
    build_agent_header_lines,
    build_clarify_lines,
    format_error_message,
    format_exit_message,
    format_session_reset_message,
    render_agent_markdown,
)
from sideclaw.config.loader import get_config_path, load_config
from sideclaw.config.schema import Config
from sideclaw.runtime.clarify import reset_clarify_callback, set_clarify_callback
from sideclaw.runtime.models.requests import RunRequest


def _reset_cli_session(session_manager: Any, session_key: str = "cli:cli") -> None:
    """Clear a CLI session from memory and persisted storage."""
    session = session_manager.get_or_create(session_key)
    session.clear()
    session_manager.save(session)
    session_manager.invalidate(session_key)


def agent(
    message: str | None = None,
) -> None:
    """Run the agent in CLI mode."""
    config = load_config(get_config_path())

    if not config.providers.openrouter:
        print_line(
            format_error_message("Error: OpenRouter not configured. Run 'sideclaw onboard' first.")
        )
        raise typer.Exit(1)

    asyncio.run(run_agent(config, message))


async def run_agent(config: Config, single_message: str | None = None) -> None:
    """Run the agent loop in CLI mode."""
    runtime = build_cli_runtime(config)
    runtime_service = runtime.runtime_service
    session_manager = runtime.session_manager

    def _cli_clarify(question: str, choices: list[str] | None) -> str:
        for line in build_clarify_lines(question, choices):
            print_line(line)
        return prompt_input("[bold cyan]? [/bold cyan]").strip()

    if single_message:
        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            result = await runtime_service.run(
                RunRequest(
                    input_text=single_message,
                    surface="cli",
                    conversation_id="cli",
                    user_id="cli",
                )
            )
        finally:
            reset_clarify_callback(clarify_token)
        print_line(render_agent_markdown(result.output_text))
        return

    for line in build_agent_header_lines(config.agent.model):
        print_line(line)

    while True:
        try:
            user_input = prompt_input("[bold cyan]> [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            print_line()
            print_line(format_exit_message())
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print_line(format_exit_message())
            break
        if user_input == "/new":
            _reset_cli_session(session_manager, "cli:cli")
            print_line(format_session_reset_message())
            continue

        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            result = await runtime_service.run(
                RunRequest(
                    input_text=user_input,
                    surface="cli",
                    conversation_id="cli",
                    user_id="cli",
                )
            )
        finally:
            reset_clarify_callback(clarify_token)
        print_line()
        print_line(render_agent_markdown(result.output_text))
        print_line()

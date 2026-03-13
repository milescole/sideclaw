"""Agent CLI surface."""

import asyncio
from typing import Any

import typer

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
from sideclaw.config.schema import ApprovalConfig, ApprovalMode, Config
from sideclaw.cron import CronService, cron_store_path


def _approval_config_for_runtime(
    approval: ApprovalConfig,
    *,
    channel_prompt: bool,
) -> ApprovalConfig:
    """Map the configured policy to the current runtime surface."""
    if approval.mode == ApprovalMode.auto_deny:
        return approval

    target_mode = ApprovalMode.channel_prompt if channel_prompt else ApprovalMode.cli_prompt
    if approval.mode == target_mode:
        return approval

    return approval.model_copy(update={"mode": target_mode})


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
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.messages import InboundMessage
    from sideclaw.bus.queue import MessageBus
    from sideclaw.providers.openrouter import OpenRouterProvider
    from sideclaw.runtime.approval import configure as configure_approval
    from sideclaw.runtime.clarify import reset_clarify_callback, set_clarify_callback
    from sideclaw.session.manager import SessionManager

    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sessions").mkdir(exist_ok=True)

    bus = MessageBus()
    provider = OpenRouterProvider(
        api_key=config.providers.openrouter.api_key,
        default_model=config.agent.model,
        api_base=config.providers.openrouter.api_base,
    )
    session_manager = SessionManager(workspace / "sessions")
    cron_service = CronService(
        cron_store_path(workspace),
        poll_interval_seconds=config.cron.poll_interval_seconds,
    )
    agent_loop = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
        cron_service=cron_service,
    )
    configure_approval(_approval_config_for_runtime(config.approval, channel_prompt=False))
    agent_loop.register_default_tools()

    def _cli_clarify(question: str, choices: list[str] | None) -> str:
        for line in build_clarify_lines(question, choices):
            print_line(line)
        return prompt_input("[bold cyan]? [/bold cyan]").strip()

    if single_message:
        msg = InboundMessage(channel="cli", chat_id="cli", sender_id="cli", text=single_message)
        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            response = await agent_loop.process_message(msg)
        finally:
            reset_clarify_callback(clarify_token)
        print_line(render_agent_markdown(response.text))
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

        msg = InboundMessage(channel="cli", chat_id="cli", sender_id="cli", text=user_input)
        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            response = await agent_loop.process_message(msg)
        finally:
            reset_clarify_callback(clarify_token)
        print_line()
        print_line(render_agent_markdown(response.text))
        print_line()

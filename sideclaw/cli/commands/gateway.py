"""Gateway CLI surface."""

import asyncio
from typing import Any

import typer
from loguru import logger
from rich.console import Console

from sideclaw.config.loader import get_config_path, load_config
from sideclaw.config.schema import ApprovalConfig, ApprovalMode, Config
from sideclaw.cron import CronService, cron_store_path
from sideclaw.runtime.models import ApprovalScope

console = Console()
GATEWAY_MAX_CONCURRENCY = 8


def approval_config_for_runtime(
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


def reset_cli_session(session_manager: Any, session_key: str = "cli:cli") -> None:
    """Clear a CLI session from memory and persisted storage."""
    session = session_manager.get_or_create(session_key)
    session.clear()
    session_manager.save(session)
    session_manager.invalidate(session_key)


async def _route_outbound_message(channels: list[Any], response: Any) -> bool:
    """Send a response to the configured channel adapter."""
    for channel in channels:
        if channel.channel_name == response.channel:
            await channel.send(response)
            return True

    logger.warning("No active channel adapter for outbound channel '{}'", response.channel)
    return False


def gateway() -> None:
    """Run as a long-running gateway with all enabled channels."""
    config = load_config(get_config_path())

    if not config.providers.openrouter:
        console.print("[red]Error: OpenRouter not configured. Run 'sideclaw onboard' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(run_gateway(config))


async def run_gateway(config: Config) -> None:
    """Run the gateway with all enabled channels."""
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.messages import InboundMessage
    from sideclaw.bus.queue import MessageBus
    from sideclaw.providers.openrouter import OpenRouterProvider
    from sideclaw.runtime.approval import configure as configure_approval
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
    configure_approval(approval_config_for_runtime(config.approval, channel_prompt=True))
    agent_loop.register_default_tools()

    channels: list[Any] = []
    pending_tasks: set[asyncio.Task[None]] = set()
    semaphore = asyncio.Semaphore(GATEWAY_MAX_CONCURRENCY)

    if config.channels.telegram:
        from sideclaw.channels.telegram import TelegramChannel

        tg = TelegramChannel(
            bus=bus,
            token=config.channels.telegram.token,
            allow_from=config.channels.telegram.allow_from,
        )
        channels.append(tg)

    if not channels:
        console.print("[yellow]No channels configured. Use 'sideclaw agent' for CLI mode.[/yellow]")
        raise typer.Exit(1)

    console.print("[bold green]SideClaw Gateway[/bold green]")
    console.print(f"Model: {config.agent.model}")
    console.print(f"Channels: {', '.join(type(c).__name__ for c in channels)}")

    for ch in channels:
        await ch.start()

    async def _execute_cron_job(job: Any) -> None:
        from sideclaw.tools.cron import CronTool

        if not any(channel.channel_name == job.channel for channel in channels):
            msg = f"No active channel adapter configured for '{job.channel}'"
            raise RuntimeError(msg)

        cron_tool = agent_loop._registry.get("cron")
        token = None
        if isinstance(cron_tool, CronTool):
            token = cron_tool.set_cron_context(True)

        try:
            response = await agent_loop.process_message(
                InboundMessage(
                    channel=job.channel,
                    chat_id=job.chat_id,
                    sender_id="cron",
                    text=job.prompt,
                )
            )
            await _route_outbound_message(channels, response)
        finally:
            if isinstance(cron_tool, CronTool) and token is not None:
                cron_tool.reset_cron_context(token)

    if config.cron.enabled:
        await cron_service.start(_execute_cron_job)
        logger.info("Cron scheduler started")

    try:
        while True:
            msg = await bus.consume_inbound()
            logger.info(f"[{msg.channel}:{msg.chat_id}] {msg.text[:50]}...")
            task = asyncio.create_task(
                handle_message(agent_loop, channels, session_manager, semaphore, msg)
            )
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)
    except asyncio.CancelledError:
        pass
    finally:
        await cron_service.stop()
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        for ch in channels:
            await ch.stop()


async def handle_message(
    agent_loop: Any,
    channels: list[Any],
    session_manager: Any,
    semaphore: asyncio.Semaphore,
    msg: Any,
) -> None:
    """Process a message and route the response."""
    try:
        from sideclaw.bus.messages import OutboundMessage

        async with semaphore:
            session_key = f"{msg.channel}:{msg.chat_id}"

            if msg.text == "/new":
                reset_cli_session(session_manager, session_key)
                return

            session = session_manager.get_or_create(session_key)
            if session.pending_approval is not None:
                lowered = msg.text.strip().lower()
                if lowered in {"y", "yes", "approve"}:
                    response_text = await agent_loop.resume_pending_approval(
                        msg, ApprovalScope.once
                    )
                elif lowered in {"s", "session"}:
                    response_text = await agent_loop.resume_pending_approval(
                        msg, ApprovalScope.session
                    )
                else:
                    response_text = await agent_loop.resume_pending_approval(msg, None)

                response = OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    text=response_text,
                )
            else:
                response = await agent_loop.process_message(msg)

        await _route_outbound_message(channels, response)
    except (RuntimeError, OSError, ValueError, TimeoutError) as e:
        logger.error(f"Error processing message: {e}")

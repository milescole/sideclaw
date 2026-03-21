"""Gateway CLI surface."""

import asyncio
from typing import Any

import typer
from loguru import logger

from sideclaw.app.gateway import build_gateway_runtime
from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import (
    format_error_message,
    format_gateway_channels_line,
    format_gateway_header,
    format_gateway_model_line,
    format_warning_message,
)
from sideclaw.config.loader import get_config_path, load_config
from sideclaw.config.schema import Config
from sideclaw.runtime.models.approval import ApprovalScope
from sideclaw.runtime.models.requests import RunRequest, RunTrigger

GATEWAY_MAX_CONCURRENCY = 8


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
        print_line(
            format_error_message("Error: OpenRouter not configured. Run 'sideclaw onboard' first.")
        )
        raise typer.Exit(1)

    asyncio.run(run_gateway(config))


async def run_gateway(config: Config) -> None:
    """Run the gateway with all enabled channels."""
    from sideclaw.bus.messages import OutboundMessage

    runtime = build_gateway_runtime(config)
    bus = runtime.bus
    session_manager = runtime.session_manager
    cron_service = runtime.cron_service
    runtime_service = runtime.runtime_service
    agent_loop = runtime.agent_loop

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
        print_line(
            format_warning_message("No channels configured. Use 'sideclaw agent' for CLI mode.")
        )
        raise typer.Exit(1)

    print_line(format_gateway_header())
    print_line(format_gateway_model_line(config.agent.model))
    print_line(format_gateway_channels_line([type(channel).__name__ for channel in channels]))

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
            result = await runtime_service.run(
                RunRequest(
                    input_text=job.prompt,
                    surface=job.channel,
                    conversation_id=job.chat_id,
                    user_id="cron",
                    trigger=RunTrigger.scheduled,
                )
            )
            await _route_outbound_message(
                channels,
                OutboundMessage(
                    channel=job.channel,
                    chat_id=job.chat_id,
                    text=result.output_text,
                ),
            )
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
                handle_message(runtime_service, channels, session_manager, semaphore, msg)
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
    runtime_service: Any,
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
                    result = await runtime_service.resume_pending(
                        RunRequest(
                            input_text=msg.text,
                            surface=msg.channel,
                            conversation_id=msg.chat_id,
                            user_id=msg.sender_id,
                        ),
                        ApprovalScope.once,
                    )
                elif lowered in {"s", "session"}:
                    result = await runtime_service.resume_pending(
                        RunRequest(
                            input_text=msg.text,
                            surface=msg.channel,
                            conversation_id=msg.chat_id,
                            user_id=msg.sender_id,
                        ),
                        ApprovalScope.session,
                    )
                else:
                    result = await runtime_service.resume_pending(
                        RunRequest(
                            input_text=msg.text,
                            surface=msg.channel,
                            conversation_id=msg.chat_id,
                            user_id=msg.sender_id,
                        ),
                        None,
                    )

                response = OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    text=result.output_text,
                )
            else:
                result = await runtime_service.run(
                    RunRequest(
                        input_text=msg.text,
                        surface=msg.channel,
                        conversation_id=msg.chat_id,
                        user_id=msg.sender_id,
                    )
                )
                response = OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    text=result.output_text,
                )

        await _route_outbound_message(channels, response)
    except (RuntimeError, OSError, ValueError, TimeoutError) as e:
        logger.error(f"Error processing message: {e}")

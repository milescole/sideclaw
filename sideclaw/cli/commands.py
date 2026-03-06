"""CLI entry points for SideClaw."""

import asyncio
import shutil
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console
from rich.markdown import Markdown

from sideclaw.config.loader import get_config_path, load_config, save_config
from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    TelegramConfig,
)
from sideclaw.runtime.models import ApprovalScope

app = typer.Typer(name="sideclaw", help="Lightweight AI assistant framework")
console = Console()

DEFAULT_WORKSPACE = Path.home() / ".sideclaw" / "workspace"


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


@app.command()
def onboard() -> None:
    """Set up SideClaw for the first time."""
    config_path = get_config_path()
    if config_path.exists():
        console.print(f"[yellow]Config exists at {config_path}; merge mode enabled.[/yellow]")
        config = load_config(config_path)
    else:
        config = Config(
            agent=AgentConfig(workspace=str(DEFAULT_WORKSPACE)),
            providers=ProvidersConfig(),
        )

    existing_key = config.providers.openrouter.api_key if config.providers.openrouter else ""
    key_prompt = (
        "OpenRouter API key (leave blank to keep existing)"
        if existing_key
        else "OpenRouter API key (optional)"
    )
    api_key = typer.prompt(key_prompt, default="", hide_input=True).strip()
    if api_key:
        if config.providers.openrouter:
            config.providers.openrouter.api_key = api_key
        else:
            config.providers.openrouter = OpenRouterConfig(api_key=api_key)

    config.agent.model = typer.prompt("Default model", default=config.agent.model).strip()
    config.agent.workspace = typer.prompt("Workspace path", default=config.agent.workspace).strip()

    current_tg = config.channels.telegram
    configure_telegram = typer.confirm(
        "Configure Telegram channel?",
        default=current_tg is not None,
    )
    if configure_telegram:
        token_prompt = (
            "Telegram bot token (leave blank to keep existing)"
            if current_tg and current_tg.token
            else "Telegram bot token"
        )
        token_input = typer.prompt(token_prompt, default="", hide_input=True).strip()
        token = token_input or (current_tg.token if current_tg else "")

        allow_default = ",".join(current_tg.allow_from) if current_tg else ""
        allow_from_raw = typer.prompt(
            "Telegram allow_from (comma-separated user IDs)",
            default=allow_default,
        ).strip()
        allow_from = [item.strip() for item in allow_from_raw.split(",") if item.strip()]

        if token:
            config.channels.telegram = TelegramConfig(token=token, allow_from=allow_from)
        else:
            console.print("[yellow]Telegram token empty; leaving Telegram disabled.[/yellow]")

    save_config(config, config_path)

    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "sessions").mkdir(exist_ok=True)

    templates_dir = Path(__file__).parent.parent / "templates"
    if templates_dir.exists():
        for tmpl in templates_dir.glob("*.md"):
            dest = workspace / tmpl.name
            if not dest.exists():
                shutil.copy2(tmpl, dest)
                console.print(f"  Created {tmpl.name}")

    console.print(f"[green]Config saved to {config_path}[/green]")
    console.print(f"[green]Workspace created at {workspace}[/green]")
    console.print(
        "[yellow]Shell exec is disabled by default. "
        "Enable tools.exec_enabled only for trusted local deployments.[/yellow]"
    )


@app.command()
def status() -> None:
    """Show SideClaw status."""
    config_path = get_config_path()
    config = load_config(config_path)

    console.print("[bold]SideClaw Status[/bold]")
    console.print(f"Config: {config_path} ({'exists' if config_path.exists() else 'not found'})")
    console.print(f"Workspace: {config.workspace_path}")
    console.print(f"Model: {config.agent.model}")
    console.print(
        f"Shell exec: {'enabled' if config.tools.exec_enabled else 'disabled'} "
        "(trusted local deployments only)"
    )

    if config.providers.openrouter:
        key = config.providers.openrouter.api_key
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        console.print(f"OpenRouter: [green]configured[/green] ({masked})")
    else:
        console.print("OpenRouter: [red]not configured[/red]")

    if config.channels.telegram:
        console.print("Telegram: [green]configured[/green]")
    else:
        console.print("Telegram: [dim]not configured[/dim]")


@app.command()
def agent(
    message: str | None = typer.Option(
        None, "--message", "-m", help="Single message (non-interactive)"
    ),
) -> None:
    """Run the agent in CLI mode."""
    config = load_config()

    if not config.providers.openrouter:
        console.print("[red]Error: OpenRouter not configured. Run 'sideclaw onboard' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_agent(config, message))


async def _run_agent(config: Config, single_message: str | None = None) -> None:
    """Run the agent loop in CLI mode."""
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
    agent_loop = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
    )
    configure_approval(_approval_config_for_runtime(config.approval, channel_prompt=False))
    agent_loop.register_default_tools()

    if single_message:
        msg = InboundMessage(channel="cli", chat_id="cli", sender_id="cli", text=single_message)
        await agent_loop.process_message(msg)
        response = await bus.consume_outbound()
        console.print(Markdown(response.text))
        return

    console.print("[bold green]SideClaw Agent[/bold green] (type 'exit' to quit, '/new' to reset)")
    console.print(f"Model: {config.agent.model}\n")

    while True:
        try:
            user_input = console.input("[bold cyan]> [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("Bye!")
            break
        if user_input == "/new":
            _reset_cli_session(session_manager, "cli:cli")
            console.print("[dim]Session reset.[/dim]")
            continue

        msg = InboundMessage(channel="cli", chat_id="cli", sender_id="cli", text=user_input)
        await agent_loop.process_message(msg)

        response = await bus.consume_outbound()
        console.print()
        console.print(Markdown(response.text))
        console.print()


@app.command()
def gateway() -> None:
    """Run as a long-running gateway with all enabled channels."""
    config = load_config()

    if not config.providers.openrouter:
        console.print("[red]Error: OpenRouter not configured. Run 'sideclaw onboard' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_gateway(config))


async def _run_gateway(config: Config) -> None:
    """Run the gateway with all enabled channels."""
    from sideclaw.agent.loop import AgentLoop
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
    agent_loop = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
    )
    configure_approval(_approval_config_for_runtime(config.approval, channel_prompt=True))
    agent_loop.register_default_tools()

    channels: list[Any] = []
    pending_tasks: set[asyncio.Task[None]] = set()

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

    try:
        while True:
            msg = await bus.consume_inbound()
            logger.info(f"[{msg.channel}:{msg.chat_id}] {msg.text[:50]}...")
            task = asyncio.create_task(
                _handle_message(agent_loop, bus, channels, session_manager, msg)
            )
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)
    except asyncio.CancelledError:
        pass
    finally:
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        for ch in channels:
            await ch.stop()


async def _handle_message(
    agent_loop: Any, bus: Any, channels: list[Any], session_manager: Any, msg: Any
) -> None:
    """Process a message and route the response."""
    try:
        from sideclaw.bus.messages import OutboundMessage

        session_key = f"{msg.channel}:{msg.chat_id}"

        if msg.text == "/new":
            _reset_cli_session(session_manager, session_key)
            return

        session = session_manager.get_or_create(session_key)
        if session.pending_approval is not None:
            lowered = msg.text.strip().lower()
            if lowered in {"y", "yes", "approve"}:
                response_text = await agent_loop.resume_pending_approval(msg, ApprovalScope.once)
            elif lowered in {"s", "session"}:
                response_text = await agent_loop.resume_pending_approval(msg, ApprovalScope.session)
            else:
                response_text = await agent_loop.resume_pending_approval(msg, None)

            if response_text:
                response = OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    text=response_text,
                )
            else:
                response = await bus.consume_outbound()
        else:
            await agent_loop.process_message(msg)
            response = await bus.consume_outbound()

        for ch in channels:
            if ch.channel_name == response.channel:
                await ch.send(response)
                break
    except (RuntimeError, OSError, ValueError, TimeoutError) as e:
        logger.error(f"Error processing message: {e}")

"""CLI entry points for SideClaw."""

import asyncio
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
    WebSearchProvider,
)
from sideclaw.runtime.models import ApprovalScope
from sideclaw.tools.image import normalize_fal_model_id
from sideclaw.utils.redact import configure_logging
from sideclaw.workspace import sync_workspace_templates

app = typer.Typer(name="sideclaw", help="Lightweight AI assistant framework")
cron_app = typer.Typer(help="Manage scheduled jobs")
console = Console()
GATEWAY_MAX_CONCURRENCY = 8


@app.callback()
def _startup() -> None:
    configure_logging()


DEFAULT_WORKSPACE = Path.home() / ".sideclaw" / "workspace"


def _cron_store_path(workspace: Path) -> Path:
    """Return the persisted cron job store path for a workspace."""
    return workspace / "cron" / "jobs.json"


def _format_timestamp(value: object) -> str:
    """Render a timestamp for CLI output."""
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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


async def _route_outbound_message(channels: list[Any], response: Any) -> bool:
    """Send a response to the configured channel adapter."""
    for channel in channels:
        if channel.channel_name == response.channel:
            await channel.send(response)
            return True

    logger.warning("No active channel adapter for outbound channel '{}'", response.channel)
    return False


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

    search_configured = (
        config.tools.web_search_provider is not None and config.tools.web_search_api_key is not None
    )
    configure_web_search = typer.confirm(
        "Configure web search?",
        default=search_configured,
    )
    if configure_web_search:
        provider_default = (
            config.tools.web_search_provider.value
            if config.tools.web_search_provider is not None
            else WebSearchProvider.brave.value
        )
        provider_raw = typer.prompt(
            "Web search provider",
            default=provider_default,
        ).strip().lower()
        existing_search_key = config.tools.web_search_api_key or ""
        search_key_prompt = (
            "Web search API key (leave blank to keep existing)"
            if existing_search_key
            else "Web search API key"
        )
        search_key_input = typer.prompt(search_key_prompt, default="", hide_input=True).strip()
        search_key = search_key_input or existing_search_key
        if provider_raw == WebSearchProvider.brave.value and search_key:
            config.tools.web_search_provider = WebSearchProvider.brave
            config.tools.web_search_api_key = search_key
        else:
            console.print(
                "[yellow]Web search not configured; leaving web_search "
                "disabled.[/yellow]"
            )
            config.tools.web_search_provider = None
            config.tools.web_search_api_key = None

    configure_image_generation = typer.confirm(
        "Configure fal.ai image generation?",
        default=bool(config.tools.fal_api_key),
    )
    if configure_image_generation:
        existing_fal_key = config.tools.fal_api_key or ""
        existing_fal_model = config.tools.fal_model
        fal_key_prompt = (
            "fal.ai API key (leave blank to keep existing)"
            if existing_fal_key
            else "fal.ai API key"
        )
        fal_key_input = typer.prompt(
            fal_key_prompt,
            default="",
            hide_input=True,
        ).strip()
        fal_key = fal_key_input or existing_fal_key
        if fal_key:
            config.tools.fal_api_key = fal_key
            selected_fal_model = (
                typer.prompt(
                    "fal.ai image model",
                    default=existing_fal_model,
                ).strip()
                or existing_fal_model
            )
            config.tools.fal_model = normalize_fal_model_id(
                selected_fal_model
            )
            config.tools.fal_enable_upscaling = typer.confirm(
                "Enable automatic fal.ai upscaling?",
                default=config.tools.fal_enable_upscaling,
            )
            if config.tools.fal_enable_upscaling:
                config.tools.fal_upscaler_model = typer.prompt(
                    "fal.ai upscaler model",
                    default=config.tools.fal_upscaler_model,
                ).strip() or config.tools.fal_upscaler_model
        else:
            console.print(
                "[yellow]Image generation not configured; leaving "
                "image generation disabled.[/yellow]"
            )
            config.tools.fal_api_key = None

    config.tools.browser_enabled = typer.confirm(
        "Enable browser automation?",
        default=config.tools.browser_enabled,
    )
    config.tools.tts.enabled = typer.confirm(
        "Enable text-to-speech?",
        default=config.tools.tts.enabled,
    )
    if config.tools.tts.enabled:
        config.tools.tts.provider = typer.prompt(
            "TTS provider",
            default=config.tools.tts.provider,
        ).strip()
        if config.tools.tts.provider.lower() == "elevenlabs":
            existing_elevenlabs_key = config.tools.tts.elevenlabs_api_key or ""
            elevenlabs_key_prompt = (
                "ElevenLabs API key (leave blank to keep existing)"
                if existing_elevenlabs_key
                else "ElevenLabs API key"
            )
            elevenlabs_key_input = typer.prompt(
                elevenlabs_key_prompt,
                default="",
                hide_input=True,
            ).strip()
            config.tools.tts.elevenlabs_api_key = (
                elevenlabs_key_input or existing_elevenlabs_key or None
            )
    config.tools.exec_enabled = typer.confirm(
        "Enable shell exec? Only do this on trusted local deployments.",
        default=config.tools.exec_enabled,
    )

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
    created_files = sync_workspace_templates(workspace)
    for created_file in created_files:
        console.print(f"  Created {created_file.relative_to(workspace)}")

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
    if config.tools.web_search_provider and config.tools.web_search_api_key:
        console.print(
            "Web search: [green]configured[/green] "
            f"({config.tools.web_search_provider.value})"
        )
    else:
        console.print("Web search: [dim]not configured[/dim]")
    console.print(
        "Image generation: "
        + (
            "[green]configured[/green] "
            f"({config.tools.fal_model}; "
            f"{'upscaling on' if config.tools.fal_enable_upscaling else 'upscaling off'})"
            if config.tools.fal_api_key
            else "[dim]disabled[/dim]"
        )
    )
    console.print(
        "Browser automation: "
        f"{'[green]enabled[/green]' if config.tools.browser_enabled else '[dim]disabled[/dim]'}"
    )
    tts_status = (
        f"[green]enabled[/green] ({config.tools.tts.provider})"
        if config.tools.tts.enabled
        else "[dim]disabled[/dim]"
    )
    console.print(
        "Text-to-speech: "
        f"{tts_status}"
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
    config = load_config(get_config_path())

    if not config.providers.openrouter:
        console.print("[red]Error: OpenRouter not configured. Run 'sideclaw onboard' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_agent(config, message))


async def _run_agent(config: Config, single_message: str | None = None) -> None:
    """Run the agent loop in CLI mode."""
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.messages import InboundMessage
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService
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
        _cron_store_path(workspace),
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
        console.print()
        console.print(f"[bold yellow]Clarify[/bold yellow] {question}")
        if choices:
            for index, choice in enumerate(choices, start=1):
                console.print(f"  {index}. {choice}")
            console.print("  0. Other")
        return console.input("[bold cyan]? [/bold cyan]").strip()

    if single_message:
        msg = InboundMessage(channel="cli", chat_id="cli", sender_id="cli", text=single_message)
        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            response = await agent_loop.process_message(msg)
        finally:
            reset_clarify_callback(clarify_token)
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
        clarify_token = set_clarify_callback(_cli_clarify)
        try:
            response = await agent_loop.process_message(msg)
        finally:
            reset_clarify_callback(clarify_token)
        console.print()
        console.print(Markdown(response.text))
        console.print()


@app.command()
def gateway() -> None:
    """Run as a long-running gateway with all enabled channels."""
    config = load_config(get_config_path())

    if not config.providers.openrouter:
        console.print("[red]Error: OpenRouter not configured. Run 'sideclaw onboard' first.[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_gateway(config))


async def _run_gateway(config: Config) -> None:
    """Run the gateway with all enabled channels."""
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.messages import InboundMessage
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService
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
        _cron_store_path(workspace),
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
    configure_approval(_approval_config_for_runtime(config.approval, channel_prompt=True))
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
                _handle_message(agent_loop, channels, session_manager, semaphore, msg)
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


async def _handle_message(
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
                _reset_cli_session(session_manager, session_key)
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


@cron_app.command("list")
def cron_list() -> None:
    """List persisted cron jobs."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(_cron_store_path(config.workspace_path))
    jobs = service.list_jobs()

    if not jobs:
        console.print("[dim]No cron jobs configured.[/dim]")
        return

    console.print("[bold]Cron Jobs[/bold]")
    for job in jobs:
        console.print(
            " | ".join(
                [
                    job.job_id,
                    job.name or "-",
                    job.schedule,
                    f"{job.channel}:{job.chat_id}",
                    f"enabled={'yes' if job.enabled else 'no'}",
                    f"next={_format_timestamp(service.next_run_at(job))}",
                    f"last={_format_timestamp(job.last_run_at)}",
                    f"error={job.last_error or '-'}",
                ]
            )
        )


@cron_app.command("add")
def cron_add(
    schedule: str = typer.Option(..., help="Cron expression, for example '0 9 * * *'"),
    prompt: str = typer.Option(..., help="Prompt to send when the job fires"),
    channel: str = typer.Option(..., help="Target channel name, for example 'telegram'"),
    chat_id: str = typer.Option(..., help="Target chat ID for delivery"),
    name: str | None = typer.Option(None, help="Optional human-readable job name"),
) -> None:
    """Add a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(_cron_store_path(config.workspace_path))

    try:
        job = service.add_job(
            schedule=schedule,
            prompt=prompt,
            channel=channel,
            chat_id=chat_id,
            name=name,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]Added cron job {job.job_id}[/green]")


@cron_app.command("remove")
def cron_remove(job_id: str) -> None:
    """Remove a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(_cron_store_path(config.workspace_path))
    if not service.remove_job(job_id):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Removed cron job {job_id}[/green]")


@cron_app.command("enable")
def cron_enable(job_id: str) -> None:
    """Enable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(_cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, True):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Enabled cron job {job_id}[/green]")


@cron_app.command("disable")
def cron_disable(job_id: str) -> None:
    """Disable a persisted cron job."""
    from sideclaw.cron import CronService

    config = load_config(get_config_path())
    service = CronService(_cron_store_path(config.workspace_path))
    if not service.set_enabled(job_id, False):
        console.print(f"[red]Cron job not found: {job_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Disabled cron job {job_id}[/green]")


app.add_typer(cron_app, name="cron")

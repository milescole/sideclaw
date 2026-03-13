"""Shared runtime dependency wiring."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sideclaw.config.schema import Config

if TYPE_CHECKING:
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService
    from sideclaw.providers.base import LLMProvider
    from sideclaw.session.manager import SessionManager


@dataclass(slots=True)
class AppRuntime:
    """Concrete runtime dependencies shared across surfaces."""

    workspace: Path
    bus: "MessageBus"
    provider: "LLMProvider"
    session_manager: "SessionManager"
    cron_service: "CronService"
    agent_loop: "AgentLoop"


def build_runtime(config: Config) -> AppRuntime:
    """Build the common runtime dependencies used by app composition roots."""
    from sideclaw.agent.loop import AgentLoop
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService, cron_store_path
    from sideclaw.providers.openrouter import OpenRouterProvider
    from sideclaw.session.manager import SessionManager

    provider_config = config.providers.openrouter
    if provider_config is None:
        msg = "OpenRouter must be configured before building the runtime"
        raise ValueError(msg)

    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    session_dir = workspace / "sessions"
    session_dir.mkdir(exist_ok=True)

    bus = MessageBus()
    provider = OpenRouterProvider(
        api_key=provider_config.api_key,
        default_model=config.agent.model,
        api_base=provider_config.api_base,
    )
    session_manager = SessionManager(session_dir)
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
    return AppRuntime(
        workspace=workspace,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        cron_service=cron_service,
        agent_loop=agent_loop,
    )

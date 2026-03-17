"""Shared runtime dependency wiring."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sideclaw.config.schema import Config

if TYPE_CHECKING:
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService
    from sideclaw.providers.base import LLMProvider
    from sideclaw.runtime.loop import RuntimeLoop
    from sideclaw.runtime.service import RuntimeService
    from sideclaw.session.manager import SessionManager


@dataclass(slots=True)
class AppRuntime:
    """Concrete runtime dependencies shared across surfaces."""

    workspace: Path
    bus: "MessageBus"
    provider: "LLMProvider"
    session_manager: "SessionManager"
    cron_service: "CronService"
    agent_loop: "RuntimeLoop"
    runtime_service: "RuntimeService"


def _detect_provider(model: str) -> str:
    """Infer the provider name from the model identifier."""
    lower = model.lower()
    if lower.startswith("claude"):
        return "anthropic"
    if any(lower.startswith(p) for p in ("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    if lower.startswith("ollama/"):
        return "ollama"
    return "openrouter"


def _build_provider(config: Config) -> "LLMProvider":
    """Build the appropriate LLM provider based on config."""
    provider_name = config.agent.provider
    model = config.agent.model

    if provider_name == "auto":
        provider_name = _detect_provider(model)

    if provider_name == "anthropic":
        from sideclaw.providers.anthropic import AnthropicProvider

        cfg = config.providers.anthropic
        if cfg is None:
            msg = "Anthropic provider requires providers.anthropic config"
            raise ValueError(msg)
        return AnthropicProvider(api_key=cfg.api_key, default_model=model)

    if provider_name == "openai":
        from sideclaw.providers.openai_provider import OpenAIProvider

        cfg = config.providers.openai
        if cfg is None:
            msg = "OpenAI provider requires providers.openai config"
            raise ValueError(msg)
        return OpenAIProvider(api_key=cfg.api_key, default_model=model, api_base=cfg.api_base)

    if provider_name == "ollama":
        from sideclaw.providers.ollama import OllamaProvider

        cfg = config.providers.ollama
        if cfg is None:
            msg = "Ollama provider requires providers.ollama config"
            raise ValueError(msg)
        resolved = model.removeprefix("ollama/")
        return OllamaProvider(default_model=resolved, api_base=cfg.api_base)

    if provider_name == "openrouter":
        from sideclaw.providers.openrouter import OpenRouterProvider

        cfg = config.providers.openrouter
        if cfg is None:
            msg = "OpenRouter must be configured"
            raise ValueError(msg)
        return OpenRouterProvider(
            api_key=cfg.api_key, default_model=model, api_base=cfg.api_base
        )

    msg = f"Unknown provider: {provider_name}"
    raise ValueError(msg)


def build_runtime(config: Config) -> AppRuntime:
    """Build the common runtime dependencies used by app composition roots."""
    from sideclaw.bus.queue import MessageBus
    from sideclaw.cron import CronService, cron_store_path
    from sideclaw.runtime.loop import RuntimeLoop
    from sideclaw.runtime.service import RuntimeService
    from sideclaw.session.manager import SessionManager

    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)
    session_dir = workspace / "sessions"
    session_dir.mkdir(exist_ok=True)

    bus = MessageBus()
    provider = _build_provider(config)
    session_manager = SessionManager(session_dir)
    cron_service = CronService(
        cron_store_path(workspace),
        poll_interval_seconds=config.cron.poll_interval_seconds,
    )
    agent_loop = RuntimeLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
        cron_service=cron_service,
    )
    runtime_service = RuntimeService(agent_loop=agent_loop, session_manager=session_manager)
    return AppRuntime(
        workspace=workspace,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        cron_service=cron_service,
        agent_loop=agent_loop,
        runtime_service=runtime_service,
    )

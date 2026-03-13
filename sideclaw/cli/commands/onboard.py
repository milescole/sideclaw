"""Onboarding CLI surface."""

from pathlib import Path

import typer

from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import (
    format_created_file_line,
    format_success_message,
    format_warning_message,
)
from sideclaw.config.loader import get_config_path, load_config, save_config
from sideclaw.config.schema import (
    AgentConfig,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    TelegramConfig,
    WebSearchProvider,
)
from sideclaw.tools.image import normalize_fal_model_id
from sideclaw.workspace import sync_workspace_templates

DEFAULT_WORKSPACE = Path.home() / ".sideclaw" / "workspace"


def onboard() -> None:
    """Set up SideClaw for the first time."""
    config_path = get_config_path()
    if config_path.exists():
        print_line(format_warning_message(f"Config exists at {config_path}; merge mode enabled."))
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
        provider_raw = (
            typer.prompt(
                "Web search provider",
                default=provider_default,
            )
            .strip()
            .lower()
        )
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
            print_line(
                format_warning_message(
                    "Web search not configured; leaving web_search disabled."
                )
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
            config.tools.fal_model = normalize_fal_model_id(selected_fal_model)
            config.tools.fal_enable_upscaling = typer.confirm(
                "Enable automatic fal.ai upscaling?",
                default=config.tools.fal_enable_upscaling,
            )
            if config.tools.fal_enable_upscaling:
                config.tools.fal_upscaler_model = (
                    typer.prompt(
                        "fal.ai upscaler model",
                        default=config.tools.fal_upscaler_model,
                    ).strip()
                    or config.tools.fal_upscaler_model
                )
        else:
            print_line(
                format_warning_message(
                    "Image generation not configured; leaving image generation disabled."
                )
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
            print_line(format_warning_message("Telegram token empty; leaving Telegram disabled."))

    save_config(config, config_path)

    workspace = config.workspace_path
    created_files = sync_workspace_templates(workspace)
    for created_file in created_files:
        print_line(format_created_file_line(str(created_file.relative_to(workspace))))

    print_line(format_success_message(f"Config saved to {config_path}"))
    print_line(format_success_message(f"Workspace created at {workspace}"))
    print_line(
        format_warning_message(
            "Shell exec is disabled by default. "
            "Enable tools.exec_enabled only for trusted local deployments."
        )
    )

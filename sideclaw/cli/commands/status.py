"""Status CLI surface."""

from rich.console import Console

from sideclaw.config.loader import get_config_path, load_config

console = Console()


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
            f"Web search: [green]configured[/green] ({config.tools.web_search_provider.value})"
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
    console.print(f"Text-to-speech: {tts_status}")

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

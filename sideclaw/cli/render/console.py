"""Shared Rich console access for CLI rendering."""

from rich.console import Console

_CONSOLE = Console()


def get_console() -> Console:
    """Return the shared CLI console."""
    return _CONSOLE


def print_line(message: object = "") -> None:
    """Print a message through the shared console."""
    get_console().print(message)


def print_streaming_token(text: str) -> None:
    """Print a streaming token without a trailing newline."""
    get_console().print(text, end="")


def prompt_input(prompt: str) -> str:
    """Read input from the shared console."""
    return get_console().input(prompt)

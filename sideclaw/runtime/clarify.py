"""Runtime clarify callback context."""

from collections.abc import Callable
from contextvars import ContextVar, Token

ClarifyCallback = Callable[[str, list[str] | None], str]

_clarify_callback: ContextVar[ClarifyCallback | None] = ContextVar(
    "clarify_callback",
    default=None,
)


def get_clarify_callback() -> ClarifyCallback | None:
    """Return the active clarify callback."""
    return _clarify_callback.get()


def set_clarify_callback(callback: ClarifyCallback | None) -> Token[ClarifyCallback | None]:
    """Bind the active clarify callback."""
    return _clarify_callback.set(callback)


def reset_clarify_callback(token: Token[ClarifyCallback | None]) -> None:
    """Restore the previous clarify callback."""
    _clarify_callback.reset(token)

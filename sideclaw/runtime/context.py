"""Runtime context for tool execution."""

from contextvars import ContextVar, Token
from dataclasses import dataclass

_tool_runtime_context: ContextVar["ToolRuntimeContext | None"] = ContextVar(
    "tool_runtime_context",
    default=None,
)


@dataclass(frozen=True)
class ToolRuntimeContext:
    """Per-message metadata available during tool execution."""

    channel: str
    chat_id: str
    sender_id: str
    session_key: str


def get_tool_runtime_context() -> ToolRuntimeContext | None:
    """Return the current tool runtime context."""
    return _tool_runtime_context.get()


def set_tool_runtime_context(context: ToolRuntimeContext) -> Token[ToolRuntimeContext | None]:
    """Bind the current tool runtime context."""
    return _tool_runtime_context.set(context)


def reset_tool_runtime_context(token: Token[ToolRuntimeContext | None]) -> None:
    """Restore the previous tool runtime context."""
    _tool_runtime_context.reset(token)

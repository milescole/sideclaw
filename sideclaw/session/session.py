"""Session dataclass."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Session:
    """A conversation session."""

    key: str
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_consolidated: int = 0
    approved_approval_keys: set[str] = field(default_factory=set)
    pending_approval: dict | None = None
    deferred_tool_calls: list[dict] = field(default_factory=list)
    title: str | None = None
    title_source: str = "auto"  # "auto" or "user"

    def get_history(self, max_messages: int = 500) -> list[dict]:
        """Get recent unconsolidated messages, aligned to start on a user turn."""
        msgs = self.messages[self.last_consolidated :]
        if len(msgs) > max_messages:
            msgs = msgs[-max_messages:]
        # Align to first user message
        while msgs and msgs[0].get("role") != "user":
            msgs = msgs[1:]
        return msgs

    def clear(self) -> None:
        """Reset session state."""
        self.messages.clear()
        self.last_consolidated = 0
        self.approved_approval_keys.clear()
        self.pending_approval = None
        self.deferred_tool_calls.clear()
        self.title = None
        self.title_source = "auto"

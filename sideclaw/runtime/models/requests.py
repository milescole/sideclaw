"""Run request models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RunTrigger(StrEnum):
    user_message = "user_message"
    approval_reply = "approval_reply"
    scheduled = "scheduled"


@dataclass(frozen=True)
class RunRequest:
    """Surface-agnostic request entering the runtime."""

    input_text: str
    surface: str
    conversation_id: str
    user_id: str | None = None
    trigger: RunTrigger = RunTrigger.user_message
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """Return the stable per-conversation session key."""
        return f"{self.surface}:{self.conversation_id}"

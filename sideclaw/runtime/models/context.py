"""Run context models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sideclaw.runtime.models.requests import RunRequest, RunTrigger


@dataclass(frozen=True)
class RuntimeContext:
    """Resolved execution context for a single run."""

    run_id: str
    surface: str
    conversation_id: str
    session_key: str
    user_id: str | None = None
    trigger: RunTrigger = RunTrigger.user_message
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: RunRequest, *, run_id: str | None = None) -> "RuntimeContext":
        """Build a runtime context from a run request."""
        return cls(
            run_id=run_id or str(uuid4()),
            surface=request.surface,
            conversation_id=request.conversation_id,
            session_key=request.session_key,
            user_id=request.user_id,
            trigger=request.trigger,
            metadata=dict(request.metadata),
        )

"""Run result models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sideclaw.runtime.models.events import RuntimeEvent
from sideclaw.runtime.models.outputs import RuntimeOutput


class RunStatus(StrEnum):
    completed = "completed"
    pending_approval = "pending_approval"
    failed = "failed"


@dataclass(frozen=True)
class RunResult:
    """Stable result for a runtime execution."""

    run_id: str
    status: RunStatus
    output_text: str
    surface: str | None = None
    conversation_id: str | None = None
    events: tuple[RuntimeEvent, ...] = field(default_factory=tuple)
    outputs: tuple[RuntimeOutput, ...] = field(default_factory=tuple)
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

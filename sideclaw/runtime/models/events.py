"""Runtime event models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RuntimeEventKind(StrEnum):
    run_started = "run_started"
    tool_started = "tool_started"
    tool_completed = "tool_completed"
    approval_required = "approval_required"
    output_emitted = "output_emitted"
    run_completed = "run_completed"
    run_failed = "run_failed"
    llm_call_completed = "llm_call_completed"
    consolidation_completed = "consolidation_completed"


@dataclass(frozen=True)
class RuntimeEvent:
    """A typed event emitted during runtime execution."""

    kind: RuntimeEventKind
    run_id: str
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

"""Transient runtime execution state."""

from dataclasses import dataclass, field
from enum import StrEnum

from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent
from sideclaw.runtime.models.outputs import RuntimeOutput
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunResult, RunStatus


class RunPhase(StrEnum):
    """Lifecycle phase for an in-flight runtime run."""

    pending = "pending"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    completed = "completed"
    failed = "failed"


@dataclass
class RuntimeState:
    """In-memory state collected during a single runtime execution."""

    request: RunRequest
    context: RuntimeContext
    phase: RunPhase = RunPhase.pending
    events: list[RuntimeEvent] = field(default_factory=list)
    outputs: list[RuntimeOutput] = field(default_factory=list)

    def add_event(self, event: RuntimeEvent) -> None:
        """Record a runtime event."""
        self.events.append(event)

    def add_output(self, output: RuntimeOutput) -> None:
        """Record a surfaced output."""
        self.outputs.append(output)

    def get_usage_summary(self) -> dict:
        """Aggregate token counts and timing from llm_call_completed events."""
        total_prompt = 0
        total_completion = 0
        total_duration_ms = 0
        llm_calls = 0
        for event in self.events:
            if event.kind.value == "llm_call_completed":
                total_prompt += event.data.get("prompt_tokens", 0)
                total_completion += event.data.get("completion_tokens", 0)
                total_duration_ms += event.data.get("duration_ms", 0)
                llm_calls += 1
        return {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "duration_ms": total_duration_ms,
            "llm_calls": llm_calls,
        }

    def finish(self, *, status: RunStatus, output_text: str) -> RunResult:
        """Build the final run result from collected state."""
        self.phase = RunPhase.completed if status != RunStatus.failed else RunPhase.failed
        return RunResult(
            run_id=self.context.run_id,
            status=status,
            output_text=output_text,
            surface=self.context.surface,
            conversation_id=self.context.conversation_id,
            events=tuple(self.events),
            outputs=tuple(self.outputs),
        )

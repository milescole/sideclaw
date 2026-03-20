"""Tests for execution telemetry: event enrichment and timing."""

from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.state import RuntimeState, RunPhase
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunStatus


class TestRuntimeEventKinds:
    def test_llm_call_completed_exists(self):
        assert RuntimeEventKind.llm_call_completed == "llm_call_completed"

    def test_consolidation_completed_exists(self):
        assert RuntimeEventKind.consolidation_completed == "consolidation_completed"


class TestUsageSummary:
    def _make_state(self) -> RuntimeState:
        request = RunRequest(
            input_text="test",
            surface="cli",
            conversation_id="test",
        )
        context = RuntimeContext.from_request(request)
        return RuntimeState(request=request, context=context, phase=RunPhase.running)

    def test_empty_summary(self):
        state = self._make_state()
        summary = state.get_usage_summary()
        assert summary["llm_calls"] == 0
        assert summary["total_tokens"] == 0

    def test_summary_with_events(self):
        state = self._make_state()
        state.add_event(RuntimeEvent(
            kind=RuntimeEventKind.llm_call_completed,
            run_id="r1",
            data={"prompt_tokens": 100, "completion_tokens": 50, "duration_ms": 500},
        ))
        state.add_event(RuntimeEvent(
            kind=RuntimeEventKind.llm_call_completed,
            run_id="r1",
            data={"prompt_tokens": 200, "completion_tokens": 100, "duration_ms": 300},
        ))
        summary = state.get_usage_summary()
        assert summary["llm_calls"] == 2
        assert summary["prompt_tokens"] == 300
        assert summary["completion_tokens"] == 150
        assert summary["total_tokens"] == 450
        assert summary["duration_ms"] == 800

    def test_non_llm_events_excluded(self):
        state = self._make_state()
        state.add_event(RuntimeEvent(
            kind=RuntimeEventKind.tool_completed,
            run_id="r1",
            data={"duration_ms": 100},
        ))
        summary = state.get_usage_summary()
        assert summary["llm_calls"] == 0

from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.models.outputs import RuntimeOutput
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunStatus
from sideclaw.runtime.state import RunPhase, RuntimeState


def test_runtime_state_collects_events_outputs_and_builds_result():
    request = RunRequest(
        input_text="hello",
        surface="cli",
        conversation_id="chat-1",
        user_id="user-1",
    )
    context = RuntimeContext.from_request(request, run_id="run-1")
    state = RuntimeState(request=request, context=context)

    state.phase = RunPhase.running
    state.add_event(RuntimeEvent(kind=RuntimeEventKind.run_started, run_id="run-1"))
    state.add_output(RuntimeOutput.text("done"))

    result = state.finish(status=RunStatus.completed, output_text="done")

    assert state.phase == RunPhase.completed
    assert result.run_id == "run-1"
    assert result.output_text == "done"
    assert len(result.events) == 1
    assert len(result.outputs) == 1

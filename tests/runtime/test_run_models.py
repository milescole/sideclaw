import sideclaw.runtime.models as runtime_models
from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.models.requests import RunRequest, RunTrigger
from sideclaw.runtime.models.results import RunResult, RunStatus


def test_runtime_models_package_does_not_reexport_approval_types():
    assert not hasattr(runtime_models, "ApprovalRequirement")
    assert not hasattr(runtime_models, "ApprovalRequest")


def test_run_request_defaults_and_session_key():
    request = RunRequest(
        input_text="hello",
        surface="cli",
        conversation_id="chat-1",
        user_id="user-1",
    )

    assert request.trigger == RunTrigger.user_message
    assert request.session_key == "cli:chat-1"


def test_runtime_context_from_request():
    request = RunRequest(
        input_text="schedule this",
        surface="telegram",
        conversation_id="chat-2",
        user_id="user-2",
        metadata={"channel": "telegram"},
    )

    context = RuntimeContext.from_request(request, run_id="run-123")

    assert context.run_id == "run-123"
    assert context.surface == "telegram"
    assert context.conversation_id == "chat-2"
    assert context.user_id == "user-2"
    assert context.session_key == "telegram:chat-2"
    assert context.metadata == {"channel": "telegram"}


def test_runtime_event_captures_kind_message_and_data():
    event = RuntimeEvent(
        kind=RuntimeEventKind.approval_required,
        run_id="run-123",
        message="approval required",
        data={"tool_name": "shell", "requirement": ApprovalRequirement.always.value},
    )

    assert event.kind == RuntimeEventKind.approval_required
    assert event.message == "approval required"
    assert event.data["tool_name"] == "shell"


def test_run_result_tracks_status_output_and_events():
    event = RuntimeEvent(kind=RuntimeEventKind.run_completed, run_id="run-123")
    result = RunResult(
        run_id="run-123",
        status=RunStatus.completed,
        output_text="done",
        surface="cli",
        conversation_id="chat-1",
        events=(event,),
    )

    assert result.status == RunStatus.completed
    assert result.output_text == "done"
    assert result.surface == "cli"
    assert result.conversation_id == "chat-1"
    assert result.events == (event,)

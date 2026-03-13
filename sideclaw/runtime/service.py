"""Runtime service facade."""

from sideclaw.bus.messages import InboundMessage
from sideclaw.runtime.execution.output import build_text_output
from sideclaw.runtime.loop import RuntimeLoop
from sideclaw.runtime.models.approval import ApprovalScope
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunResult, RunStatus
from sideclaw.runtime.state import RunPhase, RuntimeState
from sideclaw.session.manager import SessionManager


class RuntimeService:
    """Thin public facade over the current runtime loop."""

    def __init__(self, *, agent_loop: RuntimeLoop, session_manager: SessionManager) -> None:
        self._agent_loop = agent_loop
        self._session_manager = session_manager

    async def run(self, request: RunRequest) -> RunResult:
        """Execute a new runtime request."""
        context = RuntimeContext.from_request(request)
        state = RuntimeState(request=request, context=context, phase=RunPhase.running)
        state.add_event(RuntimeEvent(kind=RuntimeEventKind.run_started, run_id=context.run_id))

        message = self._request_to_message(request)
        response = await self._agent_loop.process_message(message)

        session = self._session_manager.get_or_create(request.session_key)
        status = (
            RunStatus.pending_approval
            if session.pending_approval is not None
            else RunStatus.completed
        )
        if status == RunStatus.pending_approval:
            state.phase = RunPhase.waiting_for_approval
            state.add_event(
                RuntimeEvent(
                    kind=RuntimeEventKind.approval_required,
                    run_id=context.run_id,
                )
            )

        state.add_output(build_text_output(response.text))
        state.add_event(
            RuntimeEvent(
                kind=RuntimeEventKind.run_completed,
                run_id=context.run_id,
            )
        )
        return state.finish(status=status, output_text=response.text)

    async def resume_pending(
        self,
        request: RunRequest,
        scope: ApprovalScope | None,
    ) -> RunResult:
        """Resume a previously paused approval-gated run."""
        context = RuntimeContext.from_request(request)
        state = RuntimeState(request=request, context=context, phase=RunPhase.running)
        state.add_event(RuntimeEvent(kind=RuntimeEventKind.run_started, run_id=context.run_id))

        output_text = await self._agent_loop.resume_pending_approval(
            self._request_to_message(request),
            scope,
        )
        state.add_output(build_text_output(output_text))
        state.add_event(
            RuntimeEvent(
                kind=RuntimeEventKind.run_completed,
                run_id=context.run_id,
            )
        )
        return state.finish(status=RunStatus.completed, output_text=output_text)

    @staticmethod
    def _request_to_message(request: RunRequest) -> InboundMessage:
        """Adapt a semantic runtime request to the current transport-shaped loop API."""
        return InboundMessage(
            channel=request.surface,
            chat_id=request.conversation_id,
            sender_id=request.user_id or request.surface,
            text=request.input_text,
        )

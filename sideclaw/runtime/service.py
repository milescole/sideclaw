"""Runtime service facade."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sideclaw.bus.messages import InboundMessage
from sideclaw.providers.base import StreamChunk
from sideclaw.runtime.execution.output import build_text_output
from sideclaw.runtime.loop import RuntimeLoop
from sideclaw.runtime.models.approval import ApprovalScope
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunResult, RunStatus
from sideclaw.runtime.state import RunPhase, RuntimeState
from sideclaw.session.manager import SessionManager

if TYPE_CHECKING:
    from sideclaw.metrics.execution_log import ExecutionLogEntry, ExecutionLogger


class RuntimeService:
    """Thin public facade over the current runtime loop."""

    def __init__(
        self,
        *,
        agent_loop: RuntimeLoop,
        session_manager: SessionManager,
        execution_logger: ExecutionLogger | None = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._session_manager = session_manager
        self._execution_logger = execution_logger

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
        result = state.finish(status=status, output_text=response.text)
        self._log_execution(state=state, request=request, status=status)
        return result

    async def run_stream(
        self,
        request: RunRequest,
        on_stream_chunk: Callable[[StreamChunk], None],
    ) -> RunResult:
        """Execute a runtime request with streaming text chunks."""
        context = RuntimeContext.from_request(request)
        state = RuntimeState(request=request, context=context, phase=RunPhase.running)
        state.add_event(RuntimeEvent(kind=RuntimeEventKind.run_started, run_id=context.run_id))

        message = self._request_to_message(request)
        response = await self._agent_loop.process_message_stream(message, on_stream_chunk)

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
        result = state.finish(status=status, output_text=response.text)
        self._log_execution(state=state, request=request, status=status)
        return result

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
        result = state.finish(status=RunStatus.completed, output_text=output_text)
        self._log_execution(state=state, request=request, status=RunStatus.completed)
        return result

    def _log_execution(
        self,
        *,
        state: RuntimeState,
        request: RunRequest,
        status: RunStatus,
    ) -> None:
        """Log the completed run to the execution logger if available."""
        if self._execution_logger is None:
            return
        from sideclaw.metrics.execution_log import ExecutionLogEntry

        summary = state.get_usage_summary()
        entry = ExecutionLogEntry(
            run_id=state.context.run_id,
            session_key=request.session_key,
            started_at=request.created_at.isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=summary.get("duration_ms", 0),
            status=status.value,
            llm_calls=summary.get("llm_calls", 0),
            total_prompt_tokens=summary.get("prompt_tokens", 0),
            total_completion_tokens=summary.get("completion_tokens", 0),
            model="",
            channel=request.surface,
        )
        self._execution_logger.log_run(entry)

    @staticmethod
    def _request_to_message(request: RunRequest) -> InboundMessage:
        """Adapt a semantic runtime request to the current transport-shaped loop API."""
        return InboundMessage(
            channel=request.surface,
            chat_id=request.conversation_id,
            sender_id=request.user_id or request.surface,
            text=request.input_text,
        )

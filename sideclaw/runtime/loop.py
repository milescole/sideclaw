"""Runtime loop: receive message, call LLM, execute tools, respond."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sideclaw.agent.prompt_builder import PromptBuilder
from sideclaw.bus.messages import InboundMessage, OutboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import Config
from sideclaw.memory.store import MemoryStore
from sideclaw.providers.base import LLMProvider, LLMResponse, StreamChunk
from sideclaw.runtime.approval import get_pending
from sideclaw.runtime.context import (
    reset_tool_runtime_context,
)
from sideclaw.runtime.execution.output import build_outbound_message
from sideclaw.runtime.execution.persistence import (
    consolidate_memory,
    parse_consolidated_memory,
    persist_session_state,
    save_session_state,
)
from sideclaw.runtime.execution.prepare import (
    bind_tool_runtime_context,
    prepare_new_run,
    prepare_resume_run,
    runtime_context_for_message,
)
from sideclaw.runtime.execution.tool_runner import (
    build_assistant_tool_message,
    execute_tool_call,
    resume_pending_tool_execution,
    run_provider_tool_loop,
)
from sideclaw.runtime.models.approval import (
    ApprovalScope,
    ToolExecutionResult,
)
from sideclaw.runtime.models.results import RunResult, RunStatus
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session
from sideclaw.session.title import maybe_auto_title
from sideclaw.tools.registry import ToolRegistry, build_default_tool_registry
from sideclaw.workspace.docs import WorkspaceDocs

_CRON_ITERATION_MULTIPLIER = 3

if TYPE_CHECKING:
    from sideclaw.cron.service import CronService


class RuntimeLoop:
    """The shared runtime orchestration loop for inbound requests."""

    def __init__(
        self,
        *,
        config: Config,
        bus: MessageBus,
        provider: LLMProvider,
        session_manager: SessionManager,
        workspace: Path,
        cron_service: "CronService | None" = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._session_manager = session_manager
        self._workspace = Path(workspace)
        self._context = PromptBuilder(
            self._workspace,
            max_context_chars=self._config.memory.max_context_chars,
            per_file_max_chars=self._config.memory.per_file_max_chars,
            max_context_files=self._config.memory.max_context_files,
            always_include=self._config.memory.always_include,
            enable_injection_scan=self._config.memory.enable_injection_scan,
        )
        self._memory = MemoryStore(self._workspace)
        self._workspace_docs = WorkspaceDocs(self._workspace)
        self._registry = ToolRegistry()
        self._cron_service = cron_service

    def _session_history_limit(self) -> int:
        """Return the configured session history limit for prompt construction."""
        return max(1, self._config.memory.keep_recent_messages)

    def register_default_tools(self) -> None:
        """Register the built-in tool set."""
        self._registry = build_default_tool_registry(
            config=self._config,
            workspace=self._workspace,
            session_manager=self._session_manager,
            cron_service=self._cron_service,
        )

    async def process_message(self, msg: InboundMessage) -> OutboundMessage:
        """Process a single inbound message through the runtime loop."""
        prepared = prepare_new_run(
            msg,
            session_manager=self._session_manager,
            prompt_builder=self._context,
            history_limit=self._session_history_limit(),
        )
        runtime_context = prepared.runtime_context
        context_token = bind_tool_runtime_context(runtime_context)
        title_args: tuple[Session, str, str] | None = None

        try:
            async with prepared.lock:
                session = prepared.session
                messages = prepared.messages
                session.messages.append({"role": "user", "content": msg.text})
                text = await self._run_provider_loop(
                    session, messages, channel=msg.channel
                )

                title_args = (session, msg.text, text or "")

                await persist_session_state(
                    session=session,
                    session_manager=self._session_manager,
                    config=self._config,
                    provider=self._provider,
                    memory_store=self._memory,
                    workspace_docs=self._workspace_docs,
                )

                result = RunResult(
                    run_id=runtime_context.run_id,
                    status=RunStatus.completed,
                    output_text=text,
                    surface=runtime_context.surface,
                    conversation_id=runtime_context.conversation_id,
                )
                outbound = build_outbound_message(
                    output_text=result.output_text,
                    surface=result.surface,
                    conversation_id=result.conversation_id,
                    fallback_channel=msg.channel,
                    fallback_chat_id=msg.chat_id,
                )
            if title_args is not None:
                self._schedule_auto_title(*title_args)
            return outbound
        finally:
            reset_tool_runtime_context(context_token)

    async def process_message_stream(
        self,
        msg: InboundMessage,
        on_stream_chunk: Callable[[StreamChunk], None],
    ) -> OutboundMessage:
        """Process a message with streaming text chunks forwarded to the callback."""
        prepared = prepare_new_run(
            msg,
            session_manager=self._session_manager,
            prompt_builder=self._context,
            history_limit=self._session_history_limit(),
        )
        runtime_context = prepared.runtime_context
        context_token = bind_tool_runtime_context(runtime_context)
        title_args: tuple[Session, str, str] | None = None

        try:
            async with prepared.lock:
                session = prepared.session
                messages = prepared.messages
                session.messages.append({"role": "user", "content": msg.text})
                text = await self._run_provider_loop(
                    session, messages, channel=msg.channel,
                    on_stream_chunk=on_stream_chunk,
                )

                title_args = (session, msg.text, text or "")

                await persist_session_state(
                    session=session,
                    session_manager=self._session_manager,
                    config=self._config,
                    provider=self._provider,
                    memory_store=self._memory,
                    workspace_docs=self._workspace_docs,
                )

                result = RunResult(
                    run_id=runtime_context.run_id,
                    status=RunStatus.completed,
                    output_text=text,
                    surface=runtime_context.surface,
                    conversation_id=runtime_context.conversation_id,
                )
                outbound = build_outbound_message(
                    output_text=result.output_text,
                    surface=result.surface,
                    conversation_id=result.conversation_id,
                    fallback_channel=msg.channel,
                    fallback_chat_id=msg.chat_id,
                )
            if title_args is not None:
                self._schedule_auto_title(*title_args)
            return outbound
        finally:
            reset_tool_runtime_context(context_token)

    async def resume_pending_approval(
        self,
        msg: InboundMessage,
        scope: ApprovalScope | None,
    ) -> str:
        """Resume a previously paused approval-gated execution."""
        prepared = prepare_resume_run(
            msg,
            session_manager=self._session_manager,
            prompt_builder=self._context,
            history_limit=self._session_history_limit(),
        )
        runtime_context = prepared.runtime_context
        context_token = bind_tool_runtime_context(runtime_context)

        try:
            async with prepared.lock:
                session = prepared.session
                request = get_pending(session)
                if request is None:
                    return "No pending approval."

                content, should_save = await resume_pending_tool_execution(
                    session=session,
                    scope=scope,
                    messages=prepared.messages,
                    provider=self._provider,
                    registry=self._registry,
                    config=self._config,
                    max_tool_iterations=self._max_tool_iterations(msg.channel),
                )
                if should_save:
                    save_session_state(session=session, session_manager=self._session_manager)
                return content
        finally:
            reset_tool_runtime_context(context_token)

    @staticmethod
    def _runtime_context_for_message(msg: InboundMessage):
        """Convert a transport message into semantic runtime context."""
        _request, runtime_context = runtime_context_for_message(msg)
        return runtime_context

    def _schedule_auto_title(
        self, session: Session, user_message: str, assistant_response: str
    ) -> None:
        """Fire-and-forget background task to auto-title the session."""
        asyncio.create_task(
            self._auto_title(session, user_message, assistant_response)
        )

    async def _auto_title(
        self, session: Session, user_message: str, assistant_response: str
    ) -> None:
        """Generate a title and persist the session if it changed."""
        await maybe_auto_title(
            session=session,
            provider=self._provider,
            model=self._config.agent.model,
            user_message=user_message,
            assistant_response=assistant_response,
        )
        if session.title:
            self._session_manager.save(session)

    def _max_tool_iterations(self, channel: str) -> int:
        """Return the tool iteration limit, multiplied for cron runs."""
        base = self._config.agent.max_tool_iterations
        if channel == "cron":
            return base * _CRON_ITERATION_MULTIPLIER
        return base

    async def _run_provider_loop(
        self,
        session: Session,
        messages: list[dict[str, Any]],
        channel: str = "",
        on_stream_chunk: "Callable[[StreamChunk], None] | None" = None,
    ) -> str:
        """Drive the provider/tool loop until text output or pending approval."""
        return await run_provider_tool_loop(
            session=session,
            messages=messages,
            provider=self._provider,
            registry=self._registry,
            config=self._config,
            max_tool_iterations=self._max_tool_iterations(channel),
            on_stream_chunk=on_stream_chunk,
        )

    async def _execute_tool_call(
        self,
        session: Session,
        name: str,
        arguments: str,
        tool_call_id: str,
        deferred_tool_calls: list[dict[str, str]],
    ) -> ToolExecutionResult:
        """Check approval and execute a tool call if allowed."""
        return await execute_tool_call(
            session=session,
            registry=self._registry,
            name=name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            deferred_tool_calls=deferred_tool_calls,
        )

    def _build_assistant_tool_msg(self, response: LLMResponse) -> dict[str, Any]:
        """Build an assistant message with tool calls for the message history."""
        return build_assistant_tool_message(response)

    def _build_messages_from_session(
        self,
        session: Session,
        *,
        channel: str,
        chat_id: str,
    ) -> list[dict[str, Any]]:
        """Build provider messages from the current saved session history."""
        history = session.get_history(max_messages=self._session_history_limit())
        messages = [
            {
                "role": "system",
                "content": self._context.build_system_prompt(
                    history=history,
                    channel=channel,
                    chat_id=chat_id,
                ),
            }
        ]
        messages.extend(history)
        return messages

    async def _consolidate_memory(self, session: Session) -> None:
        """Consolidate old messages into long-term memory via LLM."""
        await consolidate_memory(
            session=session,
            session_manager=self._session_manager,
            config=self._config,
            provider=self._provider,
            memory_store=self._memory,
            workspace_docs=self._workspace_docs,
        )

    @staticmethod
    def _parse_consolidated_memory(content: str) -> dict[str, str]:
        """Parse the structured long-term memory update returned by the LLM."""
        return parse_consolidated_memory(content)

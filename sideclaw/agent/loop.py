"""Core agent loop: receive message, call LLM, execute tools, respond."""
from pathlib import Path
from typing import Any

import json_repair
from loguru import logger

from sideclaw.agent.context import ContextBuilder
from sideclaw.bus.messages import InboundMessage, OutboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import Config
from sideclaw.memory.store import MemoryStore
from sideclaw.providers.base import LLMProvider, LLMResponse
from sideclaw.runtime.approval import (
    approve_pending,
    check_approval,
    clear_pending,
    format_approval_prompt,
    get_pending,
    set_pending,
)
from sideclaw.runtime.context import (
    ToolRuntimeContext,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)
from sideclaw.runtime.models import ApprovalScope, ToolExecutionOutcome, ToolExecutionResult
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session
from sideclaw.tools.registry import ToolRegistry

MAX_TOOL_ITERATIONS = 20


class AgentLoop:
    """The core agent: processes messages through LLM + tool loop."""

    def __init__(
        self,
        *,
        config: Config,
        bus: MessageBus,
        provider: LLMProvider,
        session_manager: SessionManager,
        workspace: Path,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._session_manager = session_manager
        self._workspace = Path(workspace)
        self._context = ContextBuilder(
            self._workspace,
            max_context_chars=self._config.memory.max_context_chars,
        )
        self._memory = MemoryStore(self._workspace)
        self._registry = ToolRegistry()

    def register_default_tools(self) -> None:
        """Register the built-in tool set."""
        from sideclaw.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
        from sideclaw.tools.memory import SaveMemoryTool
        from sideclaw.tools.shell import ExecTool
        from sideclaw.tools.web import WebFetchTool, WebSearchTool

        self._registry.register(ReadFileTool(self._workspace))
        self._registry.register(WriteFileTool(self._workspace))
        self._registry.register(EditFileTool(self._workspace))
        self._registry.register(ListDirTool(self._workspace))
        if self._config.tools.exec_enabled:
            self._registry.register(
                ExecTool(workspace=self._workspace, timeout=self._config.tools.exec_timeout)
            )
        self._registry.register(WebSearchTool(api_key=self._config.tools.web_search_api_key))
        self._registry.register(WebFetchTool())
        self._registry.register(SaveMemoryTool(self._memory))

    async def process_message(self, msg: InboundMessage) -> OutboundMessage:
        """Process a single inbound message through the agent loop."""
        session_key = f"{msg.channel}:{msg.chat_id}"
        context_token = set_tool_runtime_context(
            ToolRuntimeContext(
                channel=msg.channel,
                chat_id=msg.chat_id,
                sender_id=msg.sender_id,
                session_key=session_key,
            )
        )
        lock = self._session_manager.get_lock(session_key)

        try:
            async with lock:
                session = self._session_manager.get_or_create(session_key)
                messages = self._context.build_messages(
                    session.get_history(max_messages=100),
                    msg.text,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                )

                session.messages.append({"role": "user", "content": msg.text})
                text = await self._run_provider_loop(session, messages)

                self._session_manager.save(session)

                unconsolidated = len(session.messages) - session.last_consolidated
                if unconsolidated >= self._config.agent.memory_window:
                    await self._consolidate_memory(session)

                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, text=text)
        finally:
            reset_tool_runtime_context(context_token)

    async def resume_pending_approval(
        self,
        msg: InboundMessage,
        scope: ApprovalScope | None,
    ) -> str:
        """Resume a previously paused approval-gated execution."""
        session_key = f"{msg.channel}:{msg.chat_id}"
        context_token = set_tool_runtime_context(
            ToolRuntimeContext(
                channel=msg.channel,
                chat_id=msg.chat_id,
                sender_id=msg.sender_id,
                session_key=session_key,
            )
        )
        lock = self._session_manager.get_lock(session_key)

        try:
            async with lock:
                session = self._session_manager.get_or_create(session_key)
                request = get_pending(session)
                if request is None:
                    return "No pending approval."

                decision = approve_pending(session, scope)
                deferred_tool_calls = list(session.deferred_tool_calls)
                if not decision.approved:
                    clear_pending(session)
                    self._session_manager.save(session)
                    return "Denied."

                clear_pending(session)
                messages = self._build_messages_from_session(
                    session,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                )

                approved_result = await self._registry.execute(
                    request.tool_name,
                    request.arguments,
                )
                approved_tool_msg = {
                    "role": "tool",
                    "tool_call_id": request.tool_call_id,
                    "name": request.tool_name,
                    "content": approved_result,
                }
                messages.append(approved_tool_msg)
                session.messages.append(approved_tool_msg)

                for index, deferred in enumerate(deferred_tool_calls):
                    result = await self._execute_tool_call(
                        session,
                        deferred["name"],
                        deferred["arguments"],
                        deferred["id"],
                        deferred_tool_calls[index + 1 :],
                    )
                    if result.outcome == ToolExecutionOutcome.pending:
                        self._session_manager.save(session)
                        return result.content

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": deferred["id"],
                        "name": deferred["name"],
                        "content": result.content,
                    }
                    messages.append(tool_msg)
                    session.messages.append(tool_msg)

                content = await self._run_provider_loop(session, messages)
                self._session_manager.save(session)
                return content
        finally:
            reset_tool_runtime_context(context_token)

    async def _run_provider_loop(
        self,
        session: Session,
        messages: list[dict[str, Any]],
    ) -> str:
        """Drive the provider/tool loop until text output or pending approval."""
        tools = self._registry.get_definitions() or None

        for _iteration in range(MAX_TOOL_ITERATIONS):
            response = await self._provider.chat(
                messages=messages,
                tools=tools,
                model=self._config.agent.model,
                max_tokens=self._config.agent.max_tokens,
                temperature=self._config.agent.temperature,
            )

            if response.finish_reason == "error":
                content = response.content or "An error occurred."
                session.messages.append({"role": "assistant", "content": response.content})
                return content

            if response.tool_calls:
                assistant_msg = self._build_assistant_tool_msg(response)
                messages.append(assistant_msg)
                session.messages.append(assistant_msg)

                for index, tc in enumerate(response.tool_calls):
                    result = await self._execute_tool_call(
                        session,
                        tc.name,
                        tc.arguments,
                        tc.id,
                        [
                            {"id": other.id, "name": other.name, "arguments": other.arguments}
                            for other in response.tool_calls[index + 1 :]
                        ],
                    )

                    if result.outcome == ToolExecutionOutcome.pending:
                        return result.content

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result.content,
                    }
                    messages.append(tool_msg)
                    session.messages.append(tool_msg)
                continue

            content = response.content or ""
            session.messages.append({"role": "assistant", "content": content})
            return content

        content = "(Stopped: too many tool iterations)"
        session.messages.append({"role": "assistant", "content": content})
        return content

    async def _execute_tool_call(
        self,
        session: Session,
        name: str,
        arguments: str,
        tool_call_id: str,
        deferred_tool_calls: list[dict[str, str]],
    ) -> ToolExecutionResult:
        """Check approval and execute a tool call if allowed."""
        try:
            params = json_repair.loads(arguments)
            if not isinstance(params, dict):
                params = {}
        except (TypeError, ValueError):
            params = {}
        logger.debug(f"Executing tool: {name}({params})")

        tool, validation_error = self._registry.resolve_call(name, params)
        if validation_error is not None:
            return ToolExecutionResult(
                outcome=ToolExecutionOutcome.success,
                content=validation_error,
            )
        if tool is None:
            return ToolExecutionResult(
                outcome=ToolExecutionOutcome.denied,
                content=f"Error: Unknown tool '{name}'",
            )
        decision = check_approval(
            session=session,
            tool_name=name,
            action_type=tool.approval_action_type(**params),
            description=tool.approval_description(**params),
            subject=tool.approval_subject(**params),
            approval_key=tool.approval_key(**params),
            requirement=tool.approval_requirement(**params),
            arguments=params,
            display_arguments=tool.display_arguments(**params),
            tool_call_id=tool_call_id,
        )

        if decision.status == "pending" and decision.request is not None:
            set_pending(session, decision.request)
            session.deferred_tool_calls = deferred_tool_calls
            return ToolExecutionResult(
                outcome=ToolExecutionOutcome.pending,
                content=decision.message or format_approval_prompt(decision.request),
                approval_request=decision.request,
            )

        if decision.status == "denied":
            return ToolExecutionResult(
                outcome=ToolExecutionOutcome.denied,
                content=decision.message
                or f"Error: {tool.approval_description(**params)} not approved",
            )

        return ToolExecutionResult(
            outcome=ToolExecutionOutcome.success,
            content=await self._registry.execute(name, params),
        )

    def _build_assistant_tool_msg(self, response: LLMResponse) -> dict[str, Any]:
        """Build an assistant message with tool calls for the message history."""
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ],
        }

    def _build_messages_from_session(
        self,
        session: Session,
        *,
        channel: str,
        chat_id: str,
    ) -> list[dict[str, Any]]:
        """Build provider messages from the current saved session history."""
        messages = [{"role": "system", "content": self._context.build_system_prompt(
            channel=channel,
            chat_id=chat_id,
        )}]
        messages.extend(session.get_history(max_messages=100))
        return messages

    async def _consolidate_memory(self, session: Session) -> None:
        """Consolidate old messages into long-term memory via LLM."""
        old_messages = session.messages[
            session.last_consolidated : -self._config.agent.memory_window
        ]
        if not old_messages:
            return

        current_memory = self._memory.read_long_term()
        summary_prompt = (
            "Summarize the key facts and decisions from these messages. "
            "Merge with existing memory. Return only the updated memory content.\n\n"
            f"## Current Memory\n{current_memory}\n\n"
            f"## Messages to Consolidate\n"
        )
        for msg in old_messages:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                summary_prompt += f"**{msg['role']}**: {msg['content']}\n"

        try:
            response = await self._provider.chat(
                messages=[{"role": "user", "content": summary_prompt}],
                model=self._config.agent.model,
            )
            if response.content:
                self._memory.write_long_term(response.content)
                # Build history entry
                entry_parts = [
                    msg["content"][:100]
                    for msg in old_messages
                    if msg.get("role") == "user" and msg.get("content")
                ]
                if entry_parts:
                    self._memory.append_history(f"Topics: {'; '.join(entry_parts[:3])}")
                session.last_consolidated = len(session.messages) - self._config.agent.memory_window
                self._session_manager.save(session)
                logger.info("Memory consolidated")
        except (RuntimeError, OSError, ValueError, TimeoutError) as e:
            logger.error(f"Memory consolidation failed: {e}")

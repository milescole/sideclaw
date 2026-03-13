"""Preparation helpers for runtime execution."""

import asyncio
from contextvars import Token
from dataclasses import dataclass
from typing import Any

from sideclaw.agent.prompt_builder import PromptBuilder
from sideclaw.bus.messages import InboundMessage
from sideclaw.runtime.context import ToolRuntimeContext, set_tool_runtime_context
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session


@dataclass(frozen=True)
class PreparedRuntimeState:
    """Prepared execution state for a runtime run."""

    request: RunRequest
    runtime_context: RuntimeContext
    session_key: str
    lock: asyncio.Lock
    session: Session
    messages: list[dict[str, Any]]


def runtime_context_for_message(msg: InboundMessage) -> tuple[RunRequest, RuntimeContext]:
    """Convert a transport message into runtime request and context models."""
    request = RunRequest(
        input_text=msg.text,
        surface=msg.channel,
        conversation_id=msg.chat_id,
        user_id=msg.sender_id,
    )
    return request, RuntimeContext.from_request(request)


def bind_tool_runtime_context(runtime_context: RuntimeContext) -> Token[ToolRuntimeContext | None]:
    """Bind tool execution metadata for the current runtime context."""
    return set_tool_runtime_context(
        ToolRuntimeContext(
            channel=runtime_context.surface,
            chat_id=runtime_context.conversation_id,
            sender_id=runtime_context.user_id or "",
            session_key=runtime_context.session_key,
        )
    )


def prepare_new_run(
    msg: InboundMessage,
    *,
    session_manager: SessionManager,
    prompt_builder: PromptBuilder,
    history_limit: int,
) -> PreparedRuntimeState:
    """Prepare session and prompt state for a new inbound message."""
    request, runtime_context = runtime_context_for_message(msg)
    session_key = runtime_context.session_key
    lock = session_manager.get_lock(session_key)
    session = session_manager.get_or_create(session_key)
    messages = prompt_builder.build_messages(
        session.get_history(max_messages=history_limit),
        msg.text,
        channel=runtime_context.surface,
        chat_id=runtime_context.conversation_id,
    )
    return PreparedRuntimeState(
        request=request,
        runtime_context=runtime_context,
        session_key=session_key,
        lock=lock,
        session=session,
        messages=messages,
    )


def prepare_resume_run(
    msg: InboundMessage,
    *,
    session_manager: SessionManager,
    prompt_builder: PromptBuilder,
    history_limit: int,
) -> PreparedRuntimeState:
    """Prepare session and prompt state for a pending-approval resume."""
    request, runtime_context = runtime_context_for_message(msg)
    session_key = runtime_context.session_key
    lock = session_manager.get_lock(session_key)
    session = session_manager.get_or_create(session_key)
    history = session.get_history(max_messages=history_limit)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": prompt_builder.build_system_prompt(
                history=history,
                channel=runtime_context.surface,
                chat_id=runtime_context.conversation_id,
            ),
        },
        *history,
    ]
    return PreparedRuntimeState(
        request=request,
        runtime_context=runtime_context,
        session_key=session_key,
        lock=lock,
        session=session,
        messages=messages,
    )

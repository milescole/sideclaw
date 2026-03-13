"""Tool iteration helpers for runtime execution."""

from typing import Any

import json_repair
from loguru import logger

from sideclaw.config.schema import Config
from sideclaw.providers.base import LLMProvider, LLMResponse
from sideclaw.runtime.approval import (
    approve_pending,
    check_approval,
    clear_pending,
    format_approval_prompt,
    get_pending,
    set_pending,
)
from sideclaw.runtime.execution.llm_driver import invoke_llm
from sideclaw.runtime.models.approval import (
    ApprovalScope,
    ToolExecutionOutcome,
    ToolExecutionResult,
)
from sideclaw.session.session import Session
from sideclaw.tools.registry import ToolRegistry


def build_assistant_tool_message(response: LLMResponse) -> dict[str, Any]:
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


async def execute_tool_call(
    *,
    session: Session,
    registry: ToolRegistry,
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

    tool, validation_error = registry.resolve_call(name, params)
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
        content=await registry.execute(name, params),
    )


async def run_provider_tool_loop(
    *,
    session: Session,
    messages: list[dict[str, Any]],
    provider: LLMProvider,
    registry: ToolRegistry,
    config: Config,
    max_tool_iterations: int,
) -> str:
    """Drive the provider/tool loop until text output or pending approval."""
    tools = registry.get_definitions() or None

    for _iteration in range(max_tool_iterations):
        response = await invoke_llm(
            provider=provider,
            messages=messages,
            tools=tools,
            config=config,
        )

        if response.finish_reason == "error":
            content = response.content or "An error occurred."
            session.messages.append({"role": "assistant", "content": response.content})
            return content

        if response.tool_calls:
            assistant_msg = build_assistant_tool_message(response)
            messages.append(assistant_msg)
            session.messages.append(assistant_msg)

            for index, tc in enumerate(response.tool_calls):
                result = await execute_tool_call(
                    session=session,
                    registry=registry,
                    name=tc.name,
                    arguments=tc.arguments,
                    tool_call_id=tc.id,
                    deferred_tool_calls=[
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


async def resume_pending_tool_execution(
    *,
    session: Session,
    scope: ApprovalScope | None,
    messages: list[dict[str, Any]],
    provider: LLMProvider,
    registry: ToolRegistry,
    config: Config,
    max_tool_iterations: int = 20,
) -> tuple[str, bool]:
    """Resume a previously pending approval-gated tool execution."""
    request = get_pending(session)
    if request is None:
        return "No pending approval.", False

    decision = approve_pending(session, scope)
    deferred_tool_calls = list(session.deferred_tool_calls)
    if not decision.approved:
        clear_pending(session)
        return "Denied.", True

    clear_pending(session)
    approved_result = await registry.execute(
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
        result = await execute_tool_call(
            session=session,
            registry=registry,
            name=deferred["name"],
            arguments=deferred["arguments"],
            tool_call_id=deferred["id"],
            deferred_tool_calls=deferred_tool_calls[index + 1 :],
        )
        if result.outcome == ToolExecutionOutcome.pending:
            return result.content, True

        tool_msg = {
            "role": "tool",
            "tool_call_id": deferred["id"],
            "name": deferred["name"],
            "content": result.content,
        }
        messages.append(tool_msg)
        session.messages.append(tool_msg)

    content = await run_provider_tool_loop(
        session=session,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
        max_tool_iterations=max_tool_iterations,
    )
    return content, True

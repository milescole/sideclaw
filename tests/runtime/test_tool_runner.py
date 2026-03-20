from unittest.mock import AsyncMock

from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
)
from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.runtime.approval import configure
from sideclaw.runtime.execution.tool_runner import (
    execute_tool_call,
    resume_pending_tool_execution,
    run_provider_tool_loop,
)
from sideclaw.runtime.models.approval import ApprovalRequirement, ApprovalScope
from sideclaw.session.session import Session
from sideclaw.tools.base import Tool
from sideclaw.tools.filesystem import WriteFileTool
from sideclaw.tools.registry import ToolRegistry


def _build_config(workspace) -> Config:
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


async def test_execute_tool_call_validates_before_approval(tmp_path):
    registry = ToolRegistry()
    registry.register(WriteFileTool(tmp_path))
    session = Session(key="cli:user1")

    result = await execute_tool_call(
        session=session,
        registry=registry,
        name="write_file",
        arguments='{"content": "hello"}',
        tool_call_id="call_1",
        deferred_tool_calls=[],
    )

    assert result.outcome == "success"
    assert result.content == (
        "Error: Invalid arguments for tool 'write_file': 'path' is a required property"
    )


async def test_execute_tool_call_returns_pending_when_approval_required(tmp_path):
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        registry = ToolRegistry()
        registry.register(WriteFileTool(tmp_path))
        session = Session(key="telegram:chat1")

        result = await execute_tool_call(
            session=session,
            registry=registry,
            name="write_file",
            arguments='{"path": "first.txt", "content": "hello"}',
            tool_call_id="call_1",
            deferred_tool_calls=[{"id": "call_2", "name": "write_file", "arguments": "{}"}],
        )

        assert result.outcome == "pending"
        assert "approval required" in result.content.lower()
        assert session.pending_approval is not None
        assert session.deferred_tool_calls == [
            {"id": "call_2", "name": "write_file", "arguments": "{}"}
        ]
    finally:
        configure(ApprovalConfig())


async def test_run_provider_tool_loop_stops_after_max_iterations(tmp_path):
    config = _build_config(tmp_path)
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="call_1", name="echo", arguments='{"text":"loop"}')],
    )
    registry = ToolRegistry()

    class EchoTool(Tool):
        @property
        def name(self) -> str:
            return "echo"

        @property
        def description(self) -> str:
            return "Echo"

        @property
        def parameters(self) -> dict:
            return {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }

        def to_schema(self):
            return {
                "type": "function",
                "function": {"name": "echo", "description": "Echo", "parameters": self.parameters},
            }

        def parameter_schema(self):
            return {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            }

        async def execute(self, **kwargs):
            return kwargs["text"]

        def approval_action_type(self, **kwargs):
            return "write"

        def approval_description(self, **kwargs):
            return "echo"

        def approval_subject(self, **kwargs):
            return "echo"

        def approval_key(self, **kwargs):
            return "echo"

        def approval_requirement(self, **kwargs):
            return ApprovalRequirement.never

        def display_arguments(self, **kwargs):
            return kwargs

    registry.register(EchoTool())
    session = Session(key="cli:user1")
    messages = [{"role": "user", "content": "loop"}]

    content = await run_provider_tool_loop(
        session=session,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
        max_tool_iterations=2,
    )

    assert content == "(Stopped: too many tool iterations)"


async def test_resume_pending_tool_execution_handles_missing_and_denied(tmp_path):
    config = _build_config(tmp_path)
    provider = AsyncMock()
    registry = ToolRegistry()
    registry.register(WriteFileTool(tmp_path))
    messages = [{"role": "system", "content": "test"}]

    session = Session(key="telegram:chat1")
    content, should_save = await resume_pending_tool_execution(
        session=session,
        scope=ApprovalScope.once,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
    )
    assert content == "No pending approval."
    assert should_save is False

    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        pending_result = await execute_tool_call(
            session=session,
            registry=registry,
            name="write_file",
            arguments='{"path": "denied.txt", "content": "hello"}',
            tool_call_id="call_1",
            deferred_tool_calls=[],
        )
        assert pending_result.outcome == "pending"

        denied_content, should_save = await resume_pending_tool_execution(
            session=session,
            scope=None,
            messages=messages,
            provider=provider,
            registry=registry,
            config=config,
        )
        assert denied_content == "Denied."
        assert should_save is True
    finally:
        configure(ApprovalConfig())


async def test_resume_pending_tool_execution_respects_cost_guard(tmp_path):
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        config = _build_config(tmp_path)
        provider = AsyncMock()
        registry = ToolRegistry()
        registry.register(WriteFileTool(tmp_path))
        messages = [{"role": "system", "content": "test"}]
        session = Session(key="telegram:chat1")

        pending_result = await execute_tool_call(
            session=session,
            registry=registry,
            name="write_file",
            arguments='{"path": "blocked.txt", "content": "hello"}',
            tool_call_id="call_1",
            deferred_tool_calls=[],
        )
        assert pending_result.outcome == "pending"

        class DenyingCostGuard:
            def check_allowed(self, model: str = "") -> tuple[bool, str | None]:
                return False, "Budget exceeded."

        content, should_save = await resume_pending_tool_execution(
            session=session,
            scope=ApprovalScope.once,
            messages=messages,
            provider=provider,
            registry=registry,
            config=config,
            cost_guard=DenyingCostGuard(),
        )

        assert content == "Budget exceeded."
        assert should_save is True
        provider.chat.assert_not_called()
    finally:
        configure(ApprovalConfig())

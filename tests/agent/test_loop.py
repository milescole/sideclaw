import asyncio
from unittest.mock import AsyncMock

import pytest

from sideclaw.agent.loop import AgentLoop
from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    ToolsConfig,
)
from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.runtime.approval import configure, get_pending
from sideclaw.runtime.models import ApprovalScope
from sideclaw.session.manager import SessionManager


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def config(workspace):
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="Hello!")
    return provider


@pytest.fixture
def agent(config, bus, mock_provider, workspace):
    return AgentLoop(
        config=config,
        bus=bus,
        provider=mock_provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )


async def test_process_text_message(agent, bus, mock_provider):
    """Agent should call LLM and return an outbound response."""
    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="hello")
    response = await agent.process_message(msg)

    mock_provider.chat.assert_called_once()
    assert response.text == "Hello!"
    assert response.channel == "cli"
    assert response.chat_id == "user1"


async def test_process_tool_call_then_response(agent, bus, mock_provider):
    """Agent should execute tool calls and loop back to LLM."""
    tool_response = LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(id="call_1", name="echo", arguments='{"text": "test"}'),
        ],
    )
    final_response = LLMResponse(content="Done!")

    mock_provider.chat.side_effect = [tool_response, final_response]

    # Register a simple echo tool
    from tests.tools.test_registry import EchoTool

    agent._registry.register(EchoTool())

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="echo test")
    response = await agent.process_message(msg)

    assert mock_provider.chat.call_count == 2
    assert response.text == "Done!"


async def test_session_persistence(agent, bus, mock_provider):
    """Messages should be saved to session."""
    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="hello")
    await agent.process_message(msg)

    session = agent._session_manager.get_or_create("cli:user1")
    assert len(session.messages) >= 2  # user + assistant
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hello"


async def test_max_tool_iterations(agent, bus, mock_provider):
    """Agent should stop after max iterations to prevent infinite loops."""
    # Always return tool calls
    tool_response = LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="call_1", name="echo", arguments='{"text": "loop"}')],
    )
    mock_provider.chat.return_value = tool_response

    from tests.tools.test_registry import EchoTool

    agent._registry.register(EchoTool())

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="loop")
    await agent.process_message(msg)

    # Should stop after max iterations (default 20)
    assert mock_provider.chat.call_count <= 21


def test_register_default_tools_skips_exec_when_disabled(config, bus, mock_provider, workspace):
    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=mock_provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    agent.register_default_tools()

    assert agent._registry.has("read_file")
    assert agent._registry.has("write_file")
    assert agent._registry.has("edit_file")
    assert agent._registry.has("list_dir")
    assert agent._registry.has("exec") is False


def test_register_default_tools_includes_exec_when_enabled(config, bus, mock_provider, workspace):
    config.tools = ToolsConfig(exec_enabled=True)
    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=mock_provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    agent.register_default_tools()

    assert agent._registry.has("exec") is True


async def test_loop_breaks_on_pending_approval(agent, bus, mock_provider):
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        tool_response = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="write_file",
                    arguments='{"path": "test.txt", "content": "hello"}',
                ),
            ],
        )
        mock_provider.chat.side_effect = [tool_response]
        agent.register_default_tools()

        msg = InboundMessage(
            channel="telegram",
            chat_id="chat1",
            sender_id="user1",
            text="write a file",
        )
        response = await agent.process_message(msg)

        assert mock_provider.chat.call_count == 1
        assert "approval required" in response.text.lower()
        session = agent._session_manager.get_or_create("telegram:chat1")
        pending = get_pending(session)
        assert pending is not None
        assert pending.tool_name == "write_file"
    finally:
        configure(ApprovalConfig())


async def test_pending_approval_stops_later_tool_calls(agent, bus, mock_provider, workspace):
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        tool_response = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="write_file",
                    arguments='{"path": "first.txt", "content": "hello"}',
                ),
                ToolCallRequest(
                    id="call_2",
                    name="write_file",
                    arguments='{"path": "second.txt", "content": "world"}',
                ),
            ],
        )
        mock_provider.chat.side_effect = [tool_response]
        agent.register_default_tools()

        msg = InboundMessage(
            channel="telegram",
            chat_id="chat1",
            sender_id="user1",
            text="write files",
        )
        await agent.process_message(msg)

        assert not (workspace / "first.txt").exists()
        assert not (workspace / "second.txt").exists()
        session = agent._session_manager.get_or_create("telegram:chat1")
        assert len(session.deferred_tool_calls) == 1
        assert session.deferred_tool_calls[0]["id"] == "call_2"
    finally:
        configure(ApprovalConfig())


async def test_execute_tool_call_validates_before_approval(agent):
    agent.register_default_tools()
    session = agent._session_manager.get_or_create("cli:user1")

    result = await agent._execute_tool_call(
        session,
        "write_file",
        '{"content": "hello"}',
        "call_1",
        [],
    )

    assert result.outcome == "success"
    assert result.content == (
        "Error: Invalid arguments for tool 'write_file': 'path' is a required property"
    )


async def test_resume_pending_approval_executes_blocked_and_deferred_tools(
    agent,
    bus,
    mock_provider,
    workspace,
):
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    try:
        tool_response = LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="write_file",
                    arguments='{"path": "first.txt", "content": "hello"}',
                ),
                ToolCallRequest(
                    id="call_2",
                    name="write_file",
                    arguments='{"path": "second.txt", "content": "world"}',
                ),
            ],
        )
        final_response = LLMResponse(content="Done!")
        mock_provider.chat.side_effect = [tool_response, final_response]
        agent.register_default_tools()

        first_msg = InboundMessage(
            channel="telegram",
            chat_id="chat1",
            sender_id="user1",
            text="write files",
        )
        first_response = await agent.process_message(first_msg)
        assert "approval required" in first_response.text.lower()

        response_text = await agent.resume_pending_approval(
            InboundMessage(channel="telegram", chat_id="chat1", sender_id="user1", text="yes"),
            ApprovalScope.session,
        )

        assert response_text == "Done!"
        assert (workspace / "first.txt").read_text() == "hello"
        assert (workspace / "second.txt").read_text() == "world"
        session = agent._session_manager.get_or_create("telegram:chat1")
        assert session.pending_approval is None
        assert session.deferred_tool_calls == []
    finally:
        configure(ApprovalConfig())


class BlockingProvider:
    def __init__(self, *, release_after_calls: int = 1) -> None:
        self.release_after_calls = release_after_calls
        self.current_calls = 0
        self.max_concurrent_calls = 0
        self.total_calls = 0
        self.first_entered = asyncio.Event()
        self.target_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature
        self.total_calls += 1
        self.current_calls += 1
        self.max_concurrent_calls = max(self.max_concurrent_calls, self.current_calls)
        if self.total_calls == 1:
            self.first_entered.set()
        if self.total_calls >= self.release_after_calls:
            self.target_entered.set()
        await self.release.wait()
        self.current_calls -= 1
        return LLMResponse(content=f"response-{self.total_calls}")

    def get_default_model(self) -> str:
        return "openai/gpt-4o-mini"


async def test_process_message_serializes_same_session(config, bus, workspace):
    provider = BlockingProvider()
    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    first_msg = InboundMessage(channel="cli", chat_id="shared", sender_id="user1", text="first")
    second_msg = InboundMessage(channel="cli", chat_id="shared", sender_id="user1", text="second")

    first_task = asyncio.create_task(agent.process_message(first_msg))
    await asyncio.wait_for(provider.first_entered.wait(), timeout=1)

    second_task = asyncio.create_task(agent.process_message(second_msg))
    await asyncio.sleep(0.05)

    assert provider.total_calls == 1
    assert provider.max_concurrent_calls == 1

    provider.release.set()
    first_response = await asyncio.wait_for(first_task, timeout=1)
    second_response = await asyncio.wait_for(second_task, timeout=1)

    assert first_response.text == "response-1"
    assert second_response.text == "response-2"


async def test_process_message_allows_parallel_different_sessions(config, bus, workspace):
    provider = BlockingProvider(release_after_calls=2)
    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    first_msg = InboundMessage(channel="cli", chat_id="one", sender_id="user1", text="first")
    second_msg = InboundMessage(channel="cli", chat_id="two", sender_id="user2", text="second")

    first_task = asyncio.create_task(agent.process_message(first_msg))
    await asyncio.wait_for(provider.first_entered.wait(), timeout=1)

    second_task = asyncio.create_task(agent.process_message(second_msg))
    await asyncio.wait_for(provider.target_entered.wait(), timeout=1)

    assert provider.max_concurrent_calls == 2

    provider.release.set()
    responses = await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=1)
    assert {response.chat_id for response in responses} == {"one", "two"}

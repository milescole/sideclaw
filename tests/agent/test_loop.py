from unittest.mock import AsyncMock

import pytest

from sideclaw.agent.loop import AgentLoop
from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import (
    AgentConfig,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    ToolsConfig,
)
from sideclaw.providers.base import LLMResponse, ToolCallRequest
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
    """Agent should call LLM and publish outbound response."""
    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="hello")
    await agent.process_message(msg)

    mock_provider.chat.assert_called_once()
    response = await bus.consume_outbound()
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
    await agent.process_message(msg)

    assert mock_provider.chat.call_count == 2
    response = await bus.consume_outbound()
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


def test_register_default_tools_includes_exec_when_enabled(
    config, bus, mock_provider, workspace
):
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

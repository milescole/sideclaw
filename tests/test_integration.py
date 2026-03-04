"""Integration test: full message flow from inbound to outbound."""

from unittest.mock import AsyncMock

import pytest

from sideclaw.agent.loop import AgentLoop
from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.session.manager import SessionManager


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "sessions").mkdir()
    (ws / "memory").mkdir()
    return ws


@pytest.fixture
def config(workspace):
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


@pytest.fixture
def bus():
    return MessageBus()


async def test_full_text_conversation(workspace, config, bus):
    """Full flow: user message -> LLM -> response."""
    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="Hi! How can I help?")

    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )
    agent.register_default_tools()

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Hello!")
    await agent.process_message(msg)

    response = await bus.consume_outbound()
    assert response.text == "Hi! How can I help?"
    assert response.channel == "cli"
    assert response.chat_id == "user1"


async def test_tool_use_flow(workspace, config, bus):
    """Full flow: user asks to read file -> tool call -> response."""
    (workspace / "test.txt").write_text("secret content")

    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"

    tool_response = LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(
                id="call_1",
                name="read_file",
                arguments='{"path": "test.txt"}',
            )
        ],
    )
    final_response = LLMResponse(content="The file contains: secret content")

    provider.chat.side_effect = [tool_response, final_response]

    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )
    agent.register_default_tools()

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Read test.txt")
    await agent.process_message(msg)

    response = await bus.consume_outbound()
    assert "secret content" in response.text


async def test_multi_turn_conversation(workspace, config, bus):
    """Session persists across multiple messages."""
    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.side_effect = [
        LLMResponse(content="Hello!"),
        LLMResponse(content="I remember you said hello."),
    ]

    session_manager = SessionManager(workspace / "sessions")
    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
    )

    msg1 = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Hello")
    await agent.process_message(msg1)
    await bus.consume_outbound()

    msg2 = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="What did I say?")
    await agent.process_message(msg2)
    await bus.consume_outbound()

    second_call_messages = (
        provider.chat.call_args_list[1][1].get("messages") or provider.chat.call_args_list[1][0][0]
    )
    user_messages = [m for m in second_call_messages if m.get("role") == "user"]
    assert len(user_messages) >= 2


async def test_identity_file_loaded(workspace, config, bus):
    """Bootstrap files should be loaded into system prompt."""
    (workspace / "IDENTITY.md").write_text("You are CodeBot, a coding assistant.")

    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="I'm CodeBot!")

    agent = AgentLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Who are you?")
    await agent.process_message(msg)

    call_messages = (
        provider.chat.call_args_list[0][1].get("messages") or provider.chat.call_args_list[0][0][0]
    )
    system_msg = call_messages[0]["content"]
    assert "CodeBot" in system_msg

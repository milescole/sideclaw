"""Integration test: full message flow from inbound to outbound."""

from unittest.mock import AsyncMock

import pytest

from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.runtime.loop import RuntimeLoop
from sideclaw.session.manager import SessionManager
from sideclaw.workspace import sync_workspace_templates


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    sync_workspace_templates(ws)
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

    agent = RuntimeLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )
    agent.register_default_tools()

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Hello!")
    response = await agent.process_message(msg)

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

    agent = RuntimeLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )
    agent.register_default_tools()

    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Read test.txt")
    response = await agent.process_message(msg)

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
    agent = RuntimeLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
        workspace=workspace,
    )

    msg1 = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="Hello")
    await agent.process_message(msg1)

    msg2 = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="What did I say?")
    await agent.process_message(msg2)

    second_call_messages = (
        provider.chat.call_args_list[1][1].get("messages") or provider.chat.call_args_list[1][0][0]
    )
    user_messages = [m for m in second_call_messages if m.get("role") == "user"]
    assert len(user_messages) >= 2


async def test_agents_file_loaded(workspace, config, bus):
    """Canonical workspace files should be loaded into system prompt."""
    (workspace / "AGENTS.md").write_text("Route coding work through active plans.")

    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="I'm CodeBot!")

    agent = RuntimeLoop(
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
    assert "active plans" in system_msg


async def test_routed_workspace_doc_loaded_from_current_request(workspace, config, bus):
    runbook = workspace / "docs" / "runbooks" / "database.md"
    runbook.write_text(
        "---\n"
        "read_when:\n"
        "  - database migration\n"
        "---\n\n"
        "# Database Runbook\n\n"
        "Use migrations carefully.\n"
    )

    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="Handled.")

    agent = RuntimeLoop(
        config=config,
        bus=bus,
        provider=provider,
        session_manager=SessionManager(workspace / "sessions"),
        workspace=workspace,
    )

    msg = InboundMessage(
        channel="cli",
        chat_id="user1",
        sender_id="user1",
        text="Help with a database migration",
    )
    await agent.process_message(msg)

    call_messages = (
        provider.chat.call_args_list[0][1].get("messages") or provider.chat.call_args_list[0][0][0]
    )
    system_msg = call_messages[0]["content"]
    assert "Use migrations carefully." in system_msg

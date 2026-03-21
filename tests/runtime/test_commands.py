from unittest.mock import AsyncMock

import pytest

from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.memory.store import MemoryStore
from sideclaw.runtime.commands import CommandHandler
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session
from sideclaw.workspace import sync_workspace_templates
from sideclaw.workspace.docs import WorkspaceDocs


@pytest.fixture
def workspace(tmp_path):
    sync_workspace_templates(tmp_path)
    return tmp_path


@pytest.fixture
def config(workspace):
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


@pytest.fixture
def handler(workspace, config):
    return CommandHandler(
        session_manager=SessionManager(workspace / "sessions"),
        config=config,
        provider=AsyncMock(),
        memory_store=MemoryStore(workspace),
        workspace_docs=WorkspaceDocs(workspace),
    )


def test_is_command_recognizes_valid_commands():
    assert CommandHandler.is_command("/new") is True
    assert CommandHandler.is_command("/compact") is True
    assert CommandHandler.is_command("/help") is True
    assert CommandHandler.is_command("/HELP") is True
    assert CommandHandler.is_command("/new some args") is True
    assert CommandHandler.is_command("/model") is True
    assert CommandHandler.is_command("/model openai/gpt-4o") is True


def test_is_command_rejects_non_commands():
    assert CommandHandler.is_command("hello") is False
    assert CommandHandler.is_command("/unknown") is False
    assert CommandHandler.is_command("") is False
    assert CommandHandler.is_command("/ new") is False


async def test_help_lists_commands(handler):
    session = Session(key="test:1")

    result = await handler.handle("/help", session)

    assert "Available commands:" in result
    assert "/new" in result
    assert "/compact" in result
    assert "/help" in result


async def test_new_clears_session(handler):
    session = Session(key="test:1")
    session.messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    session.title = "Old Title"

    result = await handler.handle("/new", session)

    assert "New conversation started" in result
    assert session.messages == []
    assert session.title is None


async def test_unknown_command_returns_error(handler):
    session = Session(key="test:1")

    result = await handler.handle("/bogus", session)

    assert "Unknown command" in result


async def test_model_shows_current(handler, config):
    session = Session(key="test:1")

    result = await handler.handle("/model", session)

    assert config.agent.model in result


async def test_model_switches(handler, config):
    session = Session(key="test:1")

    result = await handler.handle("/model anthropic/claude-3.5-sonnet", session)

    assert "anthropic/claude-3.5-sonnet" in result
    assert config.agent.model == "anthropic/claude-3.5-sonnet"


async def test_model_in_help(handler):
    session = Session(key="test:1")

    result = await handler.handle("/help", session)

    assert "/model" in result


async def test_compact_triggers_consolidation(handler):
    session = Session(key="test:1")
    session.messages = [
        {"role": "user", "content": "remember this"},
        {"role": "assistant", "content": "noted"},
    ]

    result = await handler.handle("/compact", session)

    assert "consolidation" in result.lower()

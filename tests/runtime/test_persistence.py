from unittest.mock import AsyncMock

from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.memory.store import MemoryStore
from sideclaw.providers.base import LLMResponse
from sideclaw.runtime.execution.persistence import persist_session_state
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session
from sideclaw.workspace import sync_workspace_templates
from sideclaw.workspace.docs import WorkspaceDocs


def _build_config(workspace) -> Config:
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


async def test_persistence_saves_session_after_completed_run(tmp_path):
    workspace = tmp_path / "workspace"
    sync_workspace_templates(workspace)
    config = _build_config(workspace)
    provider = AsyncMock()
    session_manager = SessionManager(workspace / "sessions")
    session = session_manager.get_or_create("cli:user1")
    session.messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]

    await persist_session_state(
        session=session,
        session_manager=session_manager,
        config=config,
        provider=provider,
        memory_store=MemoryStore(workspace),
        workspace_docs=WorkspaceDocs(workspace),
    )

    session_manager.invalidate("cli:user1")
    reloaded = session_manager.get_or_create("cli:user1")
    assert reloaded.messages == session.messages


async def test_persistence_saves_pending_approval_and_deferred_calls_for_reload(tmp_path):
    workspace = tmp_path / "workspace"
    sync_workspace_templates(workspace)
    config = _build_config(workspace)
    provider = AsyncMock()
    session_manager = SessionManager(workspace / "sessions")
    session = session_manager.get_or_create("telegram:chat1")
    session.pending_approval = {
        "request_id": "req-1",
        "tool_name": "write_file",
        "action_type": "write_file",
        "description": "write file",
        "subject": "demo.txt",
        "approval_key": "write:demo.txt",
        "requirement": "unless_session_approved",
        "arguments": {"path": "demo.txt", "content": "hello"},
        "display_arguments": {"path": "demo.txt"},
        "tool_call_id": "call_1",
    }
    session.deferred_tool_calls = [
        {"id": "call_2", "name": "write_file", "arguments": '{"path":"later.txt"}'}
    ]

    await persist_session_state(
        session=session,
        session_manager=session_manager,
        config=config,
        provider=provider,
        memory_store=MemoryStore(workspace),
        workspace_docs=WorkspaceDocs(workspace),
    )

    session_manager.invalidate("telegram:chat1")
    reloaded = session_manager.get_or_create("telegram:chat1")
    assert reloaded.pending_approval is not None
    assert reloaded.pending_approval["request_id"] == "req-1"
    assert reloaded.deferred_tool_calls == session.deferred_tool_calls


async def test_persistence_triggers_memory_consolidation_at_threshold(tmp_path):
    workspace = tmp_path / "workspace"
    sync_workspace_templates(workspace)
    config = _build_config(workspace)
    config.agent.memory_window = 2
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content=(
            '{"durable_facts":["- User prefers Python."],'
            '"decisions":["- Use routed markdown context."],'
            '"preferences":["- Keep answers concise."]}'
        )
    )
    session_manager = SessionManager(workspace / "sessions")
    session = Session(
        key="cli:user1",
        messages=[
            {"role": "user", "content": "remember alpha"},
            {"role": "assistant", "content": "noted alpha"},
            {"role": "user", "content": "remember beta"},
            {"role": "assistant", "content": "noted beta"},
        ],
    )

    await persist_session_state(
        session=session,
        session_manager=session_manager,
        config=config,
        provider=provider,
        memory_store=MemoryStore(workspace),
        workspace_docs=WorkspaceDocs(workspace),
    )

    long_term = workspace / "docs" / "memory" / "long-term.md"
    updated = long_term.read_text()
    assert "## Durable Facts" in updated
    assert "- User prefers Python." in updated
    assert "## Decisions" in updated
    assert "## Preferences" in updated
    assert session.last_consolidated == len(session.messages) - config.agent.memory_window

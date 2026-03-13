from unittest.mock import AsyncMock

from sideclaw.agent.prompt_builder import PromptBuilder
from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.providers.base import LLMResponse
from sideclaw.runtime.context import get_tool_runtime_context, reset_tool_runtime_context
from sideclaw.runtime.execution.prepare import (
    bind_tool_runtime_context,
    prepare_new_run,
    prepare_resume_run,
)
from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.session.manager import SessionManager
from sideclaw.workspace import sync_workspace_templates


def _build_config(workspace):
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


def _build_provider():
    provider = AsyncMock()
    provider.get_default_model.return_value = "openai/gpt-4o-mini"
    provider.chat.return_value = LLMResponse(content="Hello!")
    return provider


def test_prepare_new_run_builds_runtime_context_and_messages(tmp_path):
    workspace = tmp_path / "workspace"
    sync_workspace_templates(workspace)
    config = _build_config(workspace)
    provider = _build_provider()
    bus = MessageBus()
    session_manager = SessionManager(workspace / "sessions")
    prompt_builder = PromptBuilder(
        workspace,
        max_context_chars=config.memory.max_context_chars,
        per_file_max_chars=config.memory.per_file_max_chars,
        max_context_files=config.memory.max_context_files,
        always_include=config.memory.always_include,
        enable_injection_scan=config.memory.enable_injection_scan,
    )

    session = session_manager.get_or_create("cli:user1")
    session.messages = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]

    config.memory.keep_recent_messages = 2
    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="current request")

    prepared = prepare_new_run(
        msg,
        session_manager=session_manager,
        prompt_builder=prompt_builder,
        history_limit=max(1, config.memory.keep_recent_messages),
    )

    assert prepared.runtime_context.surface == "cli"
    assert prepared.runtime_context.conversation_id == "user1"
    assert prepared.session.key == "cli:user1"
    assert prepared.lock is session_manager.get_lock("cli:user1")
    rendered = "\n".join(str(message.get("content", "")) for message in prepared.messages)
    assert "old question" not in rendered
    assert "old answer" not in rendered
    assert "recent question" in rendered
    assert "recent answer" in rendered
    assert "current request" in rendered
    assert bus is not None
    assert provider is not None


def test_prepare_resume_uses_saved_session_history(tmp_path):
    workspace = tmp_path / "workspace"
    sync_workspace_templates(workspace)
    config = _build_config(workspace)
    session_manager = SessionManager(workspace / "sessions")
    prompt_builder = PromptBuilder(
        workspace,
        max_context_chars=config.memory.max_context_chars,
        per_file_max_chars=config.memory.per_file_max_chars,
        max_context_files=config.memory.max_context_files,
        always_include=config.memory.always_include,
        enable_injection_scan=config.memory.enable_injection_scan,
    )

    session = session_manager.get_or_create("telegram:chat1")
    session.messages = [
        {"role": "user", "content": "request"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": '{"path":"a.txt"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "write_file",
            "content": "Approval required",
        },
    ]

    msg = InboundMessage(channel="telegram", chat_id="chat1", sender_id="user1", text="yes")
    prepared = prepare_resume_run(
        msg,
        session_manager=session_manager,
        prompt_builder=prompt_builder,
        history_limit=max(1, config.memory.keep_recent_messages),
    )

    assert prepared.runtime_context.surface == "telegram"
    assert prepared.runtime_context.conversation_id == "chat1"
    assert prepared.messages[0]["role"] == "system"
    assert prepared.messages[1]["role"] == "user"
    assert prepared.messages[2]["role"] == "assistant"
    assert prepared.messages[2]["tool_calls"][0]["function"]["name"] == "write_file"
    assert prepared.messages[3]["role"] == "tool"
    assert prepared.messages[3]["tool_call_id"] == "call_1"


def test_bind_tool_runtime_context_uses_runtime_context_fields():
    message = InboundMessage(channel="cli", chat_id="chat-7", sender_id="user-9", text="hello")
    runtime_context = RuntimeContext.from_request(
        RunRequest(
            input_text=message.text,
            surface=message.channel,
            conversation_id=message.chat_id,
            user_id=message.sender_id,
        )
    )

    token = bind_tool_runtime_context(runtime_context)
    try:
        context = get_tool_runtime_context()
        assert context is not None
        assert context.channel == "cli"
        assert context.chat_id == "chat-7"
        assert context.sender_id == "user-9"
        assert context.session_key == "cli:chat-7"
    finally:
        reset_tool_runtime_context(token)

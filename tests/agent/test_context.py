import pytest

from sideclaw.agent.context import ContextBuilder


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def builder(workspace):
    return ContextBuilder(workspace)


def test_build_system_prompt_minimal(builder):
    prompt = builder.build_system_prompt()
    assert "assistant" in prompt.lower() or "sideclaw" in prompt.lower()


def test_build_system_prompt_with_identity(builder, workspace):
    (workspace / "IDENTITY.md").write_text("You are a helpful coding assistant.")
    prompt = builder.build_system_prompt()
    assert "helpful coding assistant" in prompt


def test_build_system_prompt_with_soul(builder, workspace):
    (workspace / "SOUL.md").write_text("Be kind and concise.")
    prompt = builder.build_system_prompt()
    assert "kind and concise" in prompt


def test_build_system_prompt_with_memory(builder, workspace):
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "memory" / "MEMORY.md").write_text("User prefers Python.")
    prompt = builder.build_system_prompt()
    assert "User prefers Python" in prompt


def test_build_messages(builder):
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    messages = builder.build_messages(history, "what's up?")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "what's up?"


def test_build_messages_includes_runtime_context(builder):
    messages = builder.build_messages([], "hello", channel="telegram", chat_id="123")
    system = messages[0]["content"]
    assert "telegram" in system.lower()


def test_build_messages_trims_old_history_to_fit_budget(workspace):
    builder = ContextBuilder(workspace, max_context_chars=400)
    history = [
        {"role": "user", "content": "old question " * 8},
        {"role": "assistant", "content": "old answer " * 8},
        {"role": "user", "content": "recent question " * 4},
        {"role": "assistant", "content": "recent answer " * 4},
    ]

    messages = builder.build_messages(history, "current request")

    assert all("old question" not in str(message.get("content", "")) for message in messages)
    assert any("recent question" in str(message.get("content", "")) for message in messages)
    assert messages[-1]["content"] == "current request"
    assert builder.estimate_context_chars(messages) <= 400
    assert builder.estimate_context_tokens(messages) > 0


def test_build_messages_truncates_system_prompt_when_base_context_exceeds_budget(workspace):
    (workspace / "SOUL.md").write_text("soul " * 200)
    builder = ContextBuilder(workspace, max_context_chars=180)

    messages = builder.build_messages([], "current request")

    assert messages[0]["role"] == "system"
    assert "truncated for context budget" in messages[0]["content"]
    assert messages[-1]["content"] == "current request"
    assert builder.estimate_context_chars(messages) <= 180

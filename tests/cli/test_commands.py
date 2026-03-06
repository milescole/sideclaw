from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.cli.commands import (
    _approval_config_for_runtime,
    _handle_message,
    _reset_cli_session,
    app,
)
from sideclaw.config.loader import load_config, save_config
from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    TelegramConfig,
)
from sideclaw.runtime.approval import check_approval, configure, set_pending
from sideclaw.runtime.models import ApprovalRequirement, ApprovalRequest
from sideclaw.session.manager import SessionManager

runner = CliRunner()


def test_status_command() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "sideclaw" in result.output.lower() or "config" in result.output.lower()


def test_approval_config_for_cli_forces_cli_prompt() -> None:
    approval = ApprovalConfig(mode=ApprovalMode.channel_prompt)
    resolved = _approval_config_for_runtime(approval, channel_prompt=False)
    assert resolved.mode == ApprovalMode.cli_prompt


def test_approval_config_for_gateway_forces_channel_prompt() -> None:
    approval = ApprovalConfig(mode=ApprovalMode.cli_prompt)
    resolved = _approval_config_for_runtime(approval, channel_prompt=True)
    assert resolved.mode == ApprovalMode.channel_prompt


def test_onboard_command(tmp_path: Path) -> None:
    with patch("sideclaw.cli.commands.get_config_path", return_value=tmp_path / "config.json"):
        with patch("sideclaw.cli.commands.DEFAULT_WORKSPACE", tmp_path / "workspace"):
            result = runner.invoke(app, ["onboard"], input="\nopenai/gpt-4o-mini\n\n\n")
            assert result.exit_code == 0


def test_onboard_merge_keeps_existing_when_inputs_skipped(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    existing = Config(
        agent=AgentConfig(model="minimax/minimax-m2.5", workspace=str(tmp_path / "existing-ws")),
        providers=ProvidersConfig(
            openrouter=OpenRouterConfig(api_key="sk-or-v1-existing-key"),
        ),
    )
    existing.channels.telegram = TelegramConfig(token="123:abc", allow_from=["42"])
    save_config(existing, config_path)

    with patch("sideclaw.cli.commands.get_config_path", return_value=config_path):
        result = runner.invoke(app, ["onboard"], input="\n\n\n\n\n\n")
        assert result.exit_code == 0

    merged = load_config(config_path)
    assert merged.agent.model == "minimax/minimax-m2.5"
    assert merged.agent.workspace == str(tmp_path / "existing-ws")
    assert merged.providers.openrouter is not None
    assert merged.providers.openrouter.api_key == "sk-or-v1-existing-key"
    assert merged.channels.telegram is not None
    assert merged.channels.telegram.token == "123:abc"
    assert merged.channels.telegram.allow_from == ["42"]


def test_reset_cli_session_clears_persisted_history(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    manager = SessionManager(session_dir)
    session = manager.get_or_create("cli:cli")
    session.messages.append({"role": "user", "content": "My favorite editor is neovim"})
    session.messages.append({"role": "assistant", "content": "noted"})
    manager.save(session)

    _reset_cli_session(manager, "cli:cli")

    reloaded = SessionManager(session_dir).get_or_create("cli:cli")
    assert reloaded.messages == []
    assert reloaded.last_consolidated == 0


def test_reset_cli_session_clears_approval_state(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "sessions"
    manager = SessionManager(session_dir)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "s")
    session = manager.get_or_create("cli:cli")
    check_approval(
        session=session,
        tool_name="exec",
        action_type="shell_command",
        description="filesystem mutation",
        subject="touch test.txt",
        approval_key="shell:filesystem_mutation",
        requirement=ApprovalRequirement.unless_session_approved,
    )

    _reset_cli_session(manager, "cli:cli")

    reloaded = SessionManager(session_dir).get_or_create("cli:cli")
    assert reloaded.approved_approval_keys == set()
    assert reloaded.pending_approval is None


async def test_handle_message_new_resets_telegram_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    manager = SessionManager(session_dir)

    session = manager.get_or_create("telegram:123")
    session.messages.append({"role": "user", "content": "remember this"})
    session.messages.append({"role": "assistant", "content": "noted"})
    manager.save(session)

    class StubAgentLoop:
        async def process_message(self, _msg):  # pragma: no cover - should not be called
            msg = "process_message should not be called for /new"
            raise AssertionError(msg)

    msg = InboundMessage(channel="telegram", chat_id="123", sender_id="123", text="/new")
    await _handle_message(StubAgentLoop(), MessageBus(), [], manager, msg)

    reloaded = SessionManager(session_dir).get_or_create("telegram:123")
    assert reloaded.messages == []
    assert reloaded.last_consolidated == 0


async def test_handle_message_resolves_pending_approval(tmp_path: Path) -> None:
    class StubChannel:
        channel_name = "telegram"

        def __init__(self) -> None:
            self.sent = []

        async def send(self, msg):
            self.sent.append(msg)

    class StubAgentLoop:
        async def process_message(self, _msg):
            msg = "process_message should not run for approval replies"
            raise AssertionError(msg)

        async def resume_pending_approval(self, _msg, _scope):
            return "Approved."

    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    manager = SessionManager(tmp_path / "sessions")
    session = manager.get_or_create("telegram:123")
    set_pending(
        session,
        ApprovalRequest(
            request_id="req-1",
            tool_name="exec",
            action_type="shell_command",
            description="filesystem mutation",
            subject="touch test.txt",
            approval_key="shell:filesystem_mutation",
            requirement=ApprovalRequirement.unless_session_approved,
            arguments={"command": "touch test.txt"},
            display_arguments={"command": "touch test.txt"},
            tool_call_id="call-1",
        ),
    )

    channel = StubChannel()
    msg = InboundMessage(channel="telegram", chat_id="123", sender_id="123", text="yes")
    try:
        await _handle_message(StubAgentLoop(), MessageBus(), [channel], manager, msg)
    finally:
        configure(ApprovalConfig())

    assert len(channel.sent) == 1
    assert channel.sent[0].text == "Approved."

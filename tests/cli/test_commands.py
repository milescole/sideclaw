from pathlib import Path
from unittest.mock import patch

from sideclaw.bus.messages import InboundMessage
from sideclaw.bus.queue import MessageBus
from typer.testing import CliRunner

from sideclaw.cli.commands import _handle_message, _reset_cli_session, app
from sideclaw.config.loader import load_config, save_config
from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig, TelegramConfig
from sideclaw.session.manager import SessionManager

runner = CliRunner()


def test_status_command() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "sideclaw" in result.output.lower() or "config" in result.output.lower()


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


async def test_handle_message_new_resets_telegram_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    manager = SessionManager(session_dir)

    session = manager.get_or_create("telegram:123")
    session.messages.append({"role": "user", "content": "remember this"})
    session.messages.append({"role": "assistant", "content": "noted"})
    manager.save(session)

    class StubAgentLoop:
        async def process_message(self, _msg):  # pragma: no cover - should not be called
            raise AssertionError("process_message should not be called for /new")

    msg = InboundMessage(channel="telegram", chat_id="123", sender_id="123", text="/new")
    await _handle_message(StubAgentLoop(), MessageBus(), [], manager, msg)

    reloaded = SessionManager(session_dir).get_or_create("telegram:123")
    assert reloaded.messages == []
    assert reloaded.last_consolidated == 0

from pathlib import Path
from unittest.mock import patch

import asyncio
from typer.testing import CliRunner

from sideclaw.bus.messages import InboundMessage
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
            assert (tmp_path / "workspace" / "AGENTS.md").exists()
            assert (tmp_path / "workspace" / "docs" / "index.md").exists()


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


def test_cron_add_list_and_remove_commands(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(workspace)),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    with patch("sideclaw.cli.commands.get_config_path", return_value=config_path):
        add_result = runner.invoke(
            app,
            [
                "cron",
                "add",
                "--schedule",
                "0 9 * * *",
                "--prompt",
                "Morning summary",
                "--channel",
                "telegram",
                "--chat-id",
                "123",
                "--name",
                "daily-summary",
            ],
        )
        assert add_result.exit_code == 0
        assert "Added cron job" in add_result.output

        list_result = runner.invoke(app, ["cron", "list"])
        assert list_result.exit_code == 0
        assert "daily-summary" in list_result.output
        assert "0 9 * * *" in list_result.output

        jobs_path = workspace / "cron" / "jobs.json"
        assert jobs_path.exists()

        from sideclaw.cron import CronService

        job_id = CronService(jobs_path).list_jobs()[0].job_id
        remove_result = runner.invoke(app, ["cron", "remove", job_id])
        assert remove_result.exit_code == 0
        assert "Removed cron job" in remove_result.output


def test_cron_add_rejects_invalid_schedule(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    with patch("sideclaw.cli.commands.get_config_path", return_value=config_path):
        result = runner.invoke(
            app,
            [
                "cron",
                "add",
                "--schedule",
                "bad schedule",
                "--prompt",
                "Morning summary",
                "--channel",
                "telegram",
                "--chat-id",
                "123",
            ],
        )
        assert result.exit_code == 1
        assert "Invalid cron schedule" in result.output


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
    await _handle_message(StubAgentLoop(), [], manager, asyncio.Semaphore(1), msg)

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
        await _handle_message(StubAgentLoop(), [channel], manager, asyncio.Semaphore(1), msg)
    finally:
        configure(ApprovalConfig())

    assert len(channel.sent) == 1
    assert channel.sent[0].text == "Approved."


async def test_handle_message_respects_gateway_semaphore(tmp_path: Path) -> None:
    class StubChannel:
        channel_name = "telegram"

        def __init__(self) -> None:
            self.sent = []

        async def send(self, msg):
            self.sent.append(msg)

    class StubAgentLoop:
        def __init__(self) -> None:
            self.current = 0
            self.max_concurrent = 0
            self.total_calls = 0
            self.first_entered = asyncio.Event()
            self.second_entered = asyncio.Event()
            self.release_first = asyncio.Event()
            self.release_second = asyncio.Event()

        async def process_message(self, msg):
            self.total_calls += 1
            self.current += 1
            self.max_concurrent = max(self.max_concurrent, self.current)

            if self.total_calls == 1:
                self.first_entered.set()
                await self.release_first.wait()
            else:
                self.second_entered.set()
                await self.release_second.wait()

            self.current -= 1

            from sideclaw.bus.messages import OutboundMessage

            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, text=msg.text.upper())

    channel = StubChannel()
    agent_loop = StubAgentLoop()
    manager = SessionManager(tmp_path / "sessions")
    semaphore = asyncio.Semaphore(1)

    first = InboundMessage(channel="telegram", chat_id="1", sender_id="1", text="first")
    second = InboundMessage(channel="telegram", chat_id="2", sender_id="2", text="second")

    first_task = asyncio.create_task(_handle_message(agent_loop, [channel], manager, semaphore, first))
    await asyncio.wait_for(agent_loop.first_entered.wait(), timeout=1)

    second_task = asyncio.create_task(
        _handle_message(agent_loop, [channel], manager, semaphore, second)
    )
    await asyncio.sleep(0.05)

    assert agent_loop.total_calls == 1
    assert agent_loop.max_concurrent == 1

    agent_loop.release_first.set()
    await asyncio.wait_for(agent_loop.second_entered.wait(), timeout=1)
    agent_loop.release_second.set()

    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=1)

    assert [msg.text for msg in channel.sent] == ["FIRST", "SECOND"]
    assert agent_loop.max_concurrent == 1

import asyncio
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from sideclaw.bus.messages import InboundMessage
from sideclaw.cli.main import app
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
from sideclaw.runtime.models.approval import ApprovalRequest, ApprovalRequirement
from sideclaw.session.manager import SessionManager

runner = CliRunner()


def test_status_command() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "sideclaw" in result.output.lower() or "config" in result.output.lower()


def test_status_command_reports_provider_masking(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(
                openrouter=OpenRouterConfig(api_key="sk-or-v1-1234567890abcd")
            ),
        ),
        config_path,
    )

    status_surface = import_module("sideclaw.cli.commands.status")
    with patch.object(status_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "OpenRouter: configured" in result.output
    assert "sk-or-v1" in result.output
    assert "..." in result.output
    assert "7890abcd" not in result.output


def test_approval_config_for_cli_forces_cli_prompt() -> None:
    approval = ApprovalConfig(mode=ApprovalMode.channel_prompt)
    app_cli = import_module("sideclaw.app.cli")
    resolved = app_cli._approval_config_for_cli(approval)
    assert resolved.mode == ApprovalMode.cli_prompt


def test_approval_config_for_gateway_forces_channel_prompt() -> None:
    approval = ApprovalConfig(mode=ApprovalMode.cli_prompt)
    app_gateway = import_module("sideclaw.app.gateway")
    resolved = app_gateway._approval_config_for_gateway(approval)
    assert resolved.mode == ApprovalMode.channel_prompt


def test_onboard_command(tmp_path: Path) -> None:
    onboard_surface = import_module("sideclaw.cli.commands.onboard")
    with patch.object(onboard_surface, "get_config_path", return_value=tmp_path / "config.json"):
        with patch.object(onboard_surface, "DEFAULT_WORKSPACE", tmp_path / "workspace"):
            result = runner.invoke(
                app,
                ["onboard"],
                input="\nn\nn\nn\nn\nn\nopenai/gpt-4o-mini\n\nn\n",
            )
            assert result.exit_code == 0
            assert (tmp_path / "workspace" / "AGENTS.md").exists()
            assert (tmp_path / "workspace" / "docs" / "index.md").exists()


def test_onboard_merge_mode_notice(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    onboard_surface = import_module("sideclaw.cli.commands.onboard")
    with patch.object(onboard_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["onboard"], input="\n" * 11)

    assert result.exit_code == 0
    assert "merge mode enabled" in result.output.lower()


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

    onboard_surface = import_module("sideclaw.cli.commands.onboard")
    with patch.object(onboard_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["onboard"], input="\n" * 11)
        assert result.exit_code == 0

    merged = load_config(config_path)
    assert merged.agent.model == "minimax/minimax-m2.5"
    assert merged.agent.workspace == str(tmp_path / "existing-ws")
    assert merged.providers.openrouter is not None
    assert merged.providers.openrouter.api_key == "sk-or-v1-existing-key"
    assert merged.channels.telegram is not None
    assert merged.channels.telegram.token == "123:abc"
    assert merged.channels.telegram.allow_from == ["42"]


def test_onboard_captures_web_search_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"

    onboard_surface = import_module("sideclaw.cli.commands.onboard")
    with patch.object(onboard_surface, "get_config_path", return_value=config_path):
        with patch.object(onboard_surface, "DEFAULT_WORKSPACE", tmp_path / "workspace"):
            result = runner.invoke(
                app,
                ["onboard"],
                input="sk-or-test\ny\nbrave\nbrave_test_key\nn\nn\nn\nn\nopenai/gpt-4o-mini\n\nn\n",
            )

    assert result.exit_code == 0
    config = load_config(config_path)
    assert config.tools.web_search_provider == "brave"
    assert config.tools.web_search_api_key == "brave_test_key"


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

    cron_surface = import_module("sideclaw.cli.commands.cron")
    with patch.object(cron_surface, "get_config_path", return_value=config_path):
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


def test_cron_list_empty_state(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    cron_surface = import_module("sideclaw.cli.commands.cron")
    with patch.object(cron_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["cron", "list"])

    assert result.exit_code == 0
    assert "No cron jobs configured" in result.output


def test_cron_enable_and_disable_commands(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(workspace)),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    cron_surface = import_module("sideclaw.cli.commands.cron")
    with patch.object(cron_surface, "get_config_path", return_value=config_path):
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

        from sideclaw.cron import CronService

        job_id = CronService(workspace / "cron" / "jobs.json").list_jobs()[0].job_id

        disable_result = runner.invoke(app, ["cron", "disable", job_id])
        assert disable_result.exit_code == 0
        assert f"Disabled cron job {job_id}" in disable_result.output

        enable_result = runner.invoke(app, ["cron", "enable", job_id])
        assert enable_result.exit_code == 0
        assert f"Enabled cron job {job_id}" in enable_result.output


def test_cron_add_rejects_invalid_schedule(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    cron_surface = import_module("sideclaw.cli.commands.cron")
    with patch.object(cron_surface, "get_config_path", return_value=config_path):
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

    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    gateway_surface.reset_cli_session(manager, "cli:cli")

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

    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    gateway_surface.reset_cli_session(manager, "cli:cli")

    reloaded = SessionManager(session_dir).get_or_create("cli:cli")
    assert reloaded.approved_approval_keys == set()
    assert reloaded.pending_approval is None


def test_agent_message_command(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    agent_surface = import_module("sideclaw.cli.commands.agent")
    with patch.object(agent_surface, "get_config_path", return_value=config_path):
        with patch.object(agent_surface, "run_agent", new_callable=AsyncMock) as run_agent:
            result = runner.invoke(app, ["agent", "--message", "hello"])

    assert result.exit_code == 0
    run_agent.assert_awaited_once()
    awaited_config, awaited_message = run_agent.await_args.args
    assert awaited_message == "hello"
    assert awaited_config.agent.workspace == str(tmp_path / "workspace")


def test_agent_requires_openrouter_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(agent=AgentConfig(workspace=str(tmp_path / "workspace"))),
        config_path,
    )

    agent_surface = import_module("sideclaw.cli.commands.agent")
    with patch.object(agent_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["agent", "--message", "hello"])

    assert result.exit_code == 1
    assert "Run 'sideclaw onboard' first" in result.output


def test_gateway_exits_when_no_channels_configured(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "workspace")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    with patch.object(gateway_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["gateway"])

    assert result.exit_code == 1
    assert "No channels configured" in result.output


def test_gateway_requires_openrouter_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(agent=AgentConfig(workspace=str(tmp_path / "workspace"))),
        config_path,
    )

    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    with patch.object(gateway_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["gateway"])

    assert result.exit_code == 1
    assert "Run 'sideclaw onboard' first" in result.output


async def test_handle_message_new_resets_telegram_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    manager = SessionManager(session_dir)

    session = manager.get_or_create("telegram:123")
    session.messages.append({"role": "user", "content": "remember this"})
    session.messages.append({"role": "assistant", "content": "noted"})
    manager.save(session)

    class StubRuntimeService:
        async def run(self, _request):  # pragma: no cover - should not be called
            msg = "run should not be called for /new"
            raise AssertionError(msg)

    msg = InboundMessage(channel="telegram", chat_id="123", sender_id="123", text="/new")
    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    await gateway_surface.handle_message(
        StubRuntimeService(),
        [],
        manager,
        asyncio.Semaphore(1),
        msg,
    )

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

    class StubRuntimeService:
        async def run(self, _request):
            msg = "run should not execute for approval replies"
            raise AssertionError(msg)

        async def resume_pending(self, _request, _scope):
            class Result:
                output_text = "Approved."

            return Result()

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
    gateway_surface = import_module("sideclaw.cli.commands.gateway")
    try:
        await gateway_surface.handle_message(
            StubRuntimeService(), [channel], manager, asyncio.Semaphore(1), msg
        )
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

    class StubRuntimeService:
        def __init__(self) -> None:
            self.current = 0
            self.max_concurrent = 0
            self.total_calls = 0
            self.first_entered = asyncio.Event()
            self.second_entered = asyncio.Event()
            self.release_first = asyncio.Event()
            self.release_second = asyncio.Event()

        async def run(self, request):
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

            class Result:
                output_text = request.input_text.upper()

            return Result()

    channel = StubChannel()
    runtime_service = StubRuntimeService()
    manager = SessionManager(tmp_path / "sessions")
    semaphore = asyncio.Semaphore(1)

    first = InboundMessage(channel="telegram", chat_id="1", sender_id="1", text="first")
    second = InboundMessage(channel="telegram", chat_id="2", sender_id="2", text="second")
    gateway_surface = import_module("sideclaw.cli.commands.gateway")

    first_task = asyncio.create_task(
        gateway_surface.handle_message(runtime_service, [channel], manager, semaphore, first)
    )
    await asyncio.wait_for(runtime_service.first_entered.wait(), timeout=1)

    second_task = asyncio.create_task(
        gateway_surface.handle_message(runtime_service, [channel], manager, semaphore, second)
    )
    await asyncio.sleep(0.05)

    assert runtime_service.total_calls == 1
    assert runtime_service.max_concurrent == 1

    runtime_service.release_first.set()
    await asyncio.wait_for(runtime_service.second_entered.wait(), timeout=1)
    runtime_service.release_second.set()

    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=1)

    assert [msg.text for msg in channel.sent] == ["FIRST", "SECOND"]
    assert runtime_service.max_concurrent == 1


async def test_run_agent_uses_app_runtime_for_single_message(tmp_path: Path) -> None:
    agent_surface = import_module("sideclaw.cli.commands.agent")

    class StubRuntimeService:
        def __init__(self) -> None:
            self.requests = []

        async def run(self, request):
            self.requests.append(request)

            class Result:
                output_text = "hello back"

            return Result()

        async def run_stream(self, request, on_chunk):
            self.requests.append(request)
            on_chunk(type("Chunk", (), {"content": "hello back"})())

            class Result:
                output_text = "hello back"

            return Result()

    runtime = type(
        "StubRuntime",
        (),
        {"runtime_service": StubRuntimeService(), "session_manager": object()},
    )()
    config = Config(
        agent=AgentConfig(workspace=str(tmp_path / "workspace")),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )

    with patch.object(agent_surface, "build_cli_runtime", return_value=runtime) as build_runtime:
        with patch.object(agent_surface, "set_clarify_callback", return_value="token") as set_cb:
            with patch.object(agent_surface, "reset_clarify_callback") as reset_cb:
                with patch.object(agent_surface, "print_streaming_token"):
                    with patch.object(agent_surface, "print_line") as print_line:
                        await agent_surface.run_agent(config, "hello")

    build_runtime.assert_called_once_with(config)
    set_cb.assert_called_once()
    reset_cb.assert_called_once_with("token")
    assert len(runtime.runtime_service.requests) == 1
    assert runtime.runtime_service.requests[0].input_text == "hello"


async def test_run_gateway_uses_app_runtime_for_configured_channels(tmp_path: Path) -> None:
    gateway_surface = import_module("sideclaw.cli.commands.gateway")

    class StubBus:
        async def consume_inbound(self):
            raise asyncio.CancelledError

    class StubCronService:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self, _callback) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    class StubChannel:
        channel_name = "telegram"

        def __init__(self, bus, token, allow_from) -> None:
            self.bus = bus
            self.token = token
            self.allow_from = allow_from
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    runtime = type(
        "StubRuntime",
        (),
        {
            "bus": StubBus(),
            "session_manager": object(),
            "cron_service": StubCronService(),
            "runtime_service": object(),
            "agent_loop": object(),
        },
    )()
    config = Config(
        agent=AgentConfig(workspace=str(tmp_path / "workspace")),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )
    config.channels.telegram = TelegramConfig(token="123:abc", allow_from=["42"])

    with patch.object(
        gateway_surface,
        "build_gateway_runtime",
        return_value=runtime,
    ) as build_runtime:
        with patch("sideclaw.channels.telegram.TelegramChannel", StubChannel):
            await gateway_surface.run_gateway(config)

    build_runtime.assert_called_once_with(config)
    assert runtime.cron_service.started is True
    assert runtime.cron_service.stopped is True

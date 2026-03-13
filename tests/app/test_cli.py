from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
)
from sideclaw.runtime.approval import check_approval, configure
from sideclaw.runtime.models.approval import ApprovalRequirement, ApprovalStatus


def test_build_cli_runtime_configures_cli_approval_and_registers_tools(tmp_path) -> None:
    app_cli = import_module("sideclaw.app.cli")

    class StubAgentLoop:
        def __init__(self) -> None:
            self.registered = False

        def register_default_tools(self) -> None:
            self.registered = True

    runtime = SimpleNamespace(
        workspace=tmp_path / "workspace",
        bus=object(),
        provider=object(),
        session_manager=object(),
        cron_service=object(),
        agent_loop=StubAgentLoop(),
    )
    config = Config(
        agent=AgentConfig(workspace=str(tmp_path / "workspace")),
        approval=ApprovalConfig(mode=ApprovalMode.channel_prompt),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )

    with patch.object(app_cli, "build_runtime", return_value=runtime):
        with patch("builtins.input", return_value="n"):
            try:
                configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
                built = app_cli.build_cli_runtime(config)

                decision = check_approval(
                    session=SimpleNamespace(
                        approved_approval_keys=set(),
                        pending_approval=None,
                        deferred_tool_calls=[],
                    ),
                    tool_name="exec",
                    action_type="shell_command",
                    description="filesystem mutation",
                    subject="touch test.txt",
                    approval_key="shell:filesystem_mutation",
                    requirement=ApprovalRequirement.unless_session_approved,
                )
            finally:
                configure(ApprovalConfig())

    assert built is runtime
    assert runtime.agent_loop.registered is True
    assert decision.status == ApprovalStatus.denied

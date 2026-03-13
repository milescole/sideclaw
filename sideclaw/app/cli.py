"""CLI runtime composition root."""

from sideclaw.app.factory import AppRuntime, build_runtime
from sideclaw.config.schema import ApprovalConfig, ApprovalMode, Config
from sideclaw.runtime.approval import configure


def _approval_config_for_cli(approval: ApprovalConfig) -> ApprovalConfig:
    """Map the configured policy to CLI prompting semantics."""
    if approval.mode == ApprovalMode.auto_deny:
        return approval
    if approval.mode == ApprovalMode.cli_prompt:
        return approval
    return approval.model_copy(update={"mode": ApprovalMode.cli_prompt})


def build_cli_runtime(config: Config) -> AppRuntime:
    """Build the runtime used by the interactive CLI agent surface."""
    runtime = build_runtime(config)
    configure(_approval_config_for_cli(config.approval))
    runtime.agent_loop.register_default_tools()
    return runtime


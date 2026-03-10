"""Tool registry construction for the agent runtime."""

from pathlib import Path
from typing import TYPE_CHECKING

from sideclaw.browser import BrowserService
from sideclaw.config.schema import Config
from sideclaw.session.manager import SessionManager
from sideclaw.tools.base import Tool
from sideclaw.tools.browser import BrowserTool
from sideclaw.tools.clarify import ClarifyTool
from sideclaw.tools.cron import CronTool
from sideclaw.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from sideclaw.tools.image import ImageGenerationTool, UpscalingConfig
from sideclaw.tools.memory import (
    DocsGrepTool,
    MemorySearchTool,
    MemoryWriteTool,
    WorkspaceReadTool,
    WorkspaceTreeTool,
)
from sideclaw.tools.registry import ToolRegistry
from sideclaw.tools.shell import ExecTool
from sideclaw.tools.web import WebFetchTool, WebSearchTool

if TYPE_CHECKING:
    from sideclaw.cron.service import CronService


def build_default_tool_registry(
    *,
    config: Config,
    workspace: Path,
    session_manager: SessionManager,
    cron_service: "CronService | None" = None,
) -> ToolRegistry:
    """Build the default tool registry for an agent runtime."""
    _ = session_manager
    workspace = Path(workspace)
    registry = ToolRegistry()

    for tool in _build_core_tools(workspace=workspace):
        registry.register(tool)

    if config.tools.browser_enabled:
        browser = BrowserService(
            workspace,
            command_timeout=config.tools.browser_command_timeout,
            inactivity_timeout_seconds=config.tools.browser_session_timeout,
        )
        if browser.requirements_met():
            registry.register(BrowserTool(browser))

    if config.tools.fal_api_key:
        registry.register(
            ImageGenerationTool(
                api_key=config.tools.fal_api_key,
                model_id=config.tools.fal_model,
                client_timeout=config.tools.fal_client_timeout,
                upscaling=UpscalingConfig(
                    enabled=config.tools.fal_enable_upscaling,
                    model_id=config.tools.fal_upscaler_model,
                    factor=config.tools.fal_upscale_factor,
                ),
            )
        )

    if config.tools.exec_enabled:
        registry.register(ExecTool(workspace=workspace, timeout=config.tools.exec_timeout))

    if (
        config.tools.web_search_provider is not None
        and config.tools.web_search_api_key is not None
    ):
        registry.register(
            WebSearchTool(
                provider=config.tools.web_search_provider,
                api_key=config.tools.web_search_api_key,
            )
        )

    if cron_service is not None:
        registry.register(CronTool(cron_service))

    return registry


def _build_core_tools(*, workspace: Path) -> list[Tool]:
    """Build tools that are always present."""
    return [
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        EditFileTool(workspace),
        ListDirTool(workspace),
        ClarifyTool(),
        WebFetchTool(),
        DocsGrepTool(workspace),
        MemorySearchTool(workspace),
        WorkspaceReadTool(workspace),
        WorkspaceTreeTool(workspace),
        MemoryWriteTool(workspace),
    ]

"""Tool registry for managing available tools."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from loguru import logger

from sideclaw.tools.base import Tool

if TYPE_CHECKING:
    from sideclaw.config.schema import Config
    from sideclaw.cron.service import CronService
    from sideclaw.session.manager import SessionManager


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> None:
        """Remove a tool."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

    def resolve_call(self, name: str, params: dict[str, Any]) -> tuple[Tool | None, str | None]:
        """Resolve and validate a tool invocation before approval or execution."""
        tool = self._tools.get(name)
        if tool is None:
            return None, f"Error: Unknown tool '{name}'"

        error = self._validate_params(tool, params)
        if error is not None:
            return tool, error
        return tool, None

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name with given parameters."""
        tool, error = self.resolve_call(name, params)
        if error is not None:
            return error
        if tool is None:
            return f"Error: Unknown tool '{name}'"
        try:
            return await tool.execute(**params)
        except Exception as e:  # noqa: BLE001
            # Tool boundary: tools are user-extensible, so trap unexpected failures here.
            logger.error(f"Tool '{name}' failed: {e}")
            return f"Error executing {name}: {e}"

    def _validate_params(self, tool: Tool, params: dict[str, Any]) -> str | None:
        if not isinstance(params, dict):
            return f"Error: Invalid arguments for tool '{tool.name}': expected a JSON object"

        schema = tool.parameter_schema()
        params.update(self._coerce_params(params, schema))
        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(params)
        except SchemaError as e:
            logger.error(f"Tool '{tool.name}' has invalid parameter schema: {e.message}")
            return f"Error: Tool '{tool.name}' has an invalid parameter schema"
        except ValidationError as e:
            message = self._format_validation_error(e)
            return f"Error: Invalid arguments for tool '{tool.name}': {message}"
        return None

    @staticmethod
    def _coerce_params(params: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        """Schema-driven type coercion before validation."""
        props = schema.get("properties", {})
        result: dict[str, Any] = {}
        for key, value in params.items():
            if key in props:
                result[key] = ToolRegistry._coerce_value(value, props[key])
            else:
                result[key] = value
        return result

    @staticmethod
    def _coerce_value(val: Any, prop_schema: dict[str, Any]) -> Any:
        """Coerce a single value to match the declared schema type."""
        target = prop_schema.get("type")
        if target == "integer" and isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return val
        if target == "number" and isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return val
        if target == "boolean" and isinstance(val, str):
            low = val.lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
            return val
        if target == "string" and val is not None and not isinstance(val, str):
            return str(val)
        if target == "array" and isinstance(val, list):
            item_schema = prop_schema.get("items")
            if item_schema:
                return [ToolRegistry._coerce_value(item, item_schema) for item in val]
        if target == "object" and isinstance(val, dict):
            return ToolRegistry._coerce_params(val, prop_schema)
        return val

    @staticmethod
    def _format_validation_error(error: ValidationError) -> str:
        path_parts: list[str] = []
        for segment in error.absolute_path:
            if isinstance(segment, int):
                path_parts.append(f"[{segment}]")
            elif path_parts:
                path_parts.append(f".{segment}")
            else:
                path_parts.append(str(segment))

        location = "".join(path_parts)
        if location:
            return f"{location}: {error.message}"
        return error.message


def build_default_tool_registry(
    *,
    config: "Config",
    workspace: Path,
    session_manager: "SessionManager",
    cron_service: "CronService | None" = None,
) -> ToolRegistry:
    """Build the default tool registry for an agent runtime."""
    from sideclaw.browser import BrowserService
    from sideclaw.tools.browser import BrowserTool
    from sideclaw.tools.cron import CronTool
    from sideclaw.tools.image import ImageGenerationTool, UpscalingConfig
    from sideclaw.tools.messaging import SendMessageTool
    from sideclaw.tools.shell import ExecTool
    from sideclaw.tools.tts import TextToSpeechTool
    from sideclaw.tools.web import WebSearchTool

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

    if config.channels.telegram is not None:
        registry.register(
            SendMessageTool(
                config=config,
                session_manager=session_manager,
            )
        )

    if config.tools.tts.enabled:
        registry.register(
            TextToSpeechTool(
                workspace=workspace,
                config=config.tools.tts,
            )
        )

    if config.tools.exec_enabled:
        registry.register(ExecTool(workspace=workspace, timeout=config.tools.exec_timeout))

    if config.tools.web_search_provider is not None and config.tools.web_search_api_key is not None:
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
    from sideclaw.tools.clarify import ClarifyTool
    from sideclaw.tools.filesystem import (
        EditFileTool,
        ListDirTool,
        ReadFileTool,
        WriteFileTool,
    )
    from sideclaw.tools.memory import (
        DocsGrepTool,
        MemorySearchTool,
        MemoryWriteTool,
        WorkspaceReadTool,
        WorkspaceTreeTool,
    )
    from sideclaw.tools.web import WebFetchTool

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

"""Tool registry for managing available tools."""

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from loguru import logger

from sideclaw.tools.base import Tool


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

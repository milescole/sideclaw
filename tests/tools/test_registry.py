import pytest

from sideclaw.tools.base import Tool
from sideclaw.tools.registry import ToolRegistry


class EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes input text"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to echo"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs) -> str:
        return kwargs["text"]


@pytest.fixture
def registry():
    return ToolRegistry()


def test_register_and_get(registry):
    tool = EchoTool()
    registry.register(tool)
    assert registry.has("echo")
    assert registry.get("echo") is tool


def test_get_definitions(registry):
    registry.register(EchoTool())
    defs = registry.get_definitions()
    assert len(defs) == 1
    assert defs[0]["type"] == "function"
    assert defs[0]["function"]["name"] == "echo"
    assert defs[0]["function"]["parameters"]["additionalProperties"] is False


async def test_execute(registry):
    registry.register(EchoTool())
    result = await registry.execute("echo", {"text": "hello"})
    assert result == "hello"


async def test_execute_rejects_missing_required_param(registry):
    registry.register(EchoTool())
    result = await registry.execute("echo", {})
    assert result == "Error: Invalid arguments for tool 'echo': 'text' is a required property"


async def test_execute_rejects_wrong_param_type(registry):
    registry.register(EchoTool())
    result = await registry.execute("echo", {"text": 123})
    assert result == "Error: Invalid arguments for tool 'echo': text: 123 is not of type 'string'"


async def test_execute_rejects_unexpected_param(registry):
    registry.register(EchoTool())
    result = await registry.execute("echo", {"text": "hello", "extra": True})
    assert result == (
        "Error: Invalid arguments for tool 'echo': Additional properties are not allowed "
        "('extra' was unexpected)"
    )


async def test_execute_unknown_tool(registry):
    result = await registry.execute("nonexistent", {})
    assert "Unknown tool" in result


def test_unregister(registry):
    registry.register(EchoTool())
    registry.unregister("echo")
    assert not registry.has("echo")

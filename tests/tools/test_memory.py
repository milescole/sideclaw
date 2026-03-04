import pytest

from sideclaw.memory.store import MemoryStore
from sideclaw.tools.memory import SaveMemoryTool


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def store(workspace):
    return MemoryStore(workspace)


@pytest.fixture
def tool(store):
    return SaveMemoryTool(store)


async def test_save_memory(tool, store):
    result = await tool.execute(
        memory="User prefers dark mode.", history_entry="Discussed UI preferences."
    )
    assert "saved" in result.lower() or "updated" in result.lower()
    assert store.read_long_term() == "User prefers dark mode."


async def test_save_memory_without_history(tool, store):
    await tool.execute(memory="Some fact.")
    assert store.read_long_term() == "Some fact."


async def test_tool_schema(tool):
    schema = tool.to_schema()
    assert schema["function"]["name"] == "save_memory"
    assert "memory" in schema["function"]["parameters"]["properties"]

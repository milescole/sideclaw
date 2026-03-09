import pytest

from sideclaw.memory.store import MemoryStore


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def store(workspace):
    return MemoryStore(workspace)


def test_read_long_term_empty(store):
    result = store.read_long_term()
    assert result == ""


def test_write_and_read_long_term(store):
    store.write_long_term("User prefers Python.")
    assert store.read_long_term() == "User prefers Python."


def test_append_history(store, workspace):
    store.append_history("Had a conversation about weather.")
    store.append_history("Discussed Python async patterns.")
    content = (workspace / "memory" / "HISTORY.md").read_text()
    assert "weather" in content
    assert "Python async" in content
    leftovers = list((workspace / "memory").glob(".HISTORY.md.*.tmp"))
    assert leftovers == []


def test_get_memory_context_empty(store):
    ctx = store.get_memory_context()
    assert ctx == ""


def test_get_memory_context_with_data(store):
    store.write_long_term("User likes cats.")
    ctx = store.get_memory_context()
    assert "User likes cats" in ctx


def test_write_long_term_cleans_up_temp_file(store, workspace):
    store.write_long_term("User prefers atomic writes.")

    assert (workspace / "memory" / "MEMORY.md").read_text() == "User prefers atomic writes."
    leftovers = list((workspace / "memory").glob(".MEMORY.md.*.tmp"))
    assert leftovers == []

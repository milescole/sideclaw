import pytest

from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.filesystem import (
    AppendFileTool,
    EditFileTool,
    ListDirTool,
    MoveFileTool,
    ReadFileTool,
    SearchFilesTool,
    WriteFileTool,
)


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


async def test_read_file(workspace):
    test_file = workspace / "test.txt"
    test_file.write_text("hello world")
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="test.txt")
    assert "hello world" in result


async def test_read_file_not_found(workspace):
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="nonexistent.txt")
    assert "Error" in result or "not found" in result.lower()


async def test_read_file_blocks_path_traversal(workspace):
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="../../etc/passwd")
    assert "Error" in result or "outside" in result.lower()


async def test_read_file_blocks_absolute_path(workspace):
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="/etc/passwd")
    assert "Error" in result
    assert "absolute" in result.lower()


async def test_read_file_blocks_sibling_prefix_bypass(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sibling = tmp_path / "workspace-admin"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret")

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="../workspace-admin/secret.txt")
    assert "Error" in result
    assert "outside" in result.lower()


async def test_read_file_blocks_symlink_escape(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (workspace / "link.txt").symlink_to(outside / "secret.txt")

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="link.txt")
    assert "Error" in result
    assert "outside" in result.lower()


async def test_read_file_truncates_large_output(workspace):
    tool = ReadFileTool(workspace)
    (workspace / "large.txt").write_text("x" * 12_000)

    result = await tool.execute(path="large.txt")

    assert "omitted" in result.lower()
    assert len(result) < 12_000


async def test_write_file(workspace):
    tool = WriteFileTool(workspace)
    result = await tool.execute(path="output.txt", content="test content")
    assert (
        "output.txt" in result.lower() or "written" in result.lower() or "wrote" in result.lower()
    )
    assert (workspace / "output.txt").read_text() == "test content"


async def test_write_file_creates_directories(workspace):
    tool = WriteFileTool(workspace)
    await tool.execute(path="sub/dir/file.txt", content="nested")
    assert (workspace / "sub/dir/file.txt").read_text() == "nested"


async def test_edit_file(workspace):
    test_file = workspace / "edit.txt"
    test_file.write_text("foo bar baz")
    tool = EditFileTool(workspace)
    await tool.execute(path="edit.txt", old_text="bar", new_text="qux")
    assert (workspace / "edit.txt").read_text() == "foo qux baz"


async def test_list_dir(workspace):
    (workspace / "a.txt").touch()
    (workspace / "b.py").touch()
    (workspace / "subdir").mkdir()
    tool = ListDirTool(workspace)
    result = await tool.execute(path=".")
    assert "a.txt" in result
    assert "b.py" in result
    assert "subdir" in result


def test_write_file_declares_session_approval_requirement(workspace):
    tool = WriteFileTool(workspace)
    assert tool.approval_requirement(path="blocked.txt", content="test") == (
        ApprovalRequirement.unless_session_approved
    )
    assert tool.approval_key(path="blocked.txt", content="test") == "fs:write_file"


def test_edit_file_declares_session_approval_requirement(workspace):
    tool = EditFileTool(workspace)
    assert (
        tool.approval_requirement(
            path="edit.txt",
            old_text="original",
            new_text="changed",
        )
        == ApprovalRequirement.unless_session_approved
    )
    assert (
        tool.approval_key(
            path="edit.txt",
            old_text="original",
            new_text="changed",
        )
        == "fs:edit_file"
    )


async def test_read_file_does_not_require_approval(workspace):
    (workspace / "safe.txt").write_text("safe content")
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="safe.txt")
    assert result == "safe content"


async def test_list_dir_does_not_require_approval(workspace):
    (workspace / "file.txt").touch()
    tool = ListDirTool(workspace)
    result = await tool.execute(path=".")
    assert "file.txt" in result


# --- AppendFileTool ---


async def test_append_creates_file_if_missing(workspace):
    tool = AppendFileTool(workspace)
    result = await tool.execute(path="new.txt", content="hello")
    assert "Appended" in result
    assert (workspace / "new.txt").read_text() == "hello"


async def test_append_adds_to_existing_file(workspace):
    (workspace / "log.txt").write_text("line1\n")
    tool = AppendFileTool(workspace)
    await tool.execute(path="log.txt", content="line2\n")
    assert (workspace / "log.txt").read_text() == "line1\nline2\n"


def test_append_file_requires_session_approval(workspace):
    tool = AppendFileTool(workspace)
    assert tool.approval_requirement(path="f.txt", content="x") == (
        ApprovalRequirement.unless_session_approved
    )


# --- MoveFileTool ---


async def test_move_renames_file(workspace):
    (workspace / "old.txt").write_text("data")
    tool = MoveFileTool(workspace)
    result = await tool.execute(source="old.txt", destination="new.txt")
    assert "Moved" in result
    assert not (workspace / "old.txt").exists()
    assert (workspace / "new.txt").read_text() == "data"


async def test_move_rejects_source_outside_workspace(workspace):
    tool = MoveFileTool(workspace)
    result = await tool.execute(source="../../etc/passwd", destination="stolen.txt")
    assert "Error" in result


async def test_move_rejects_destination_outside_workspace(workspace):
    (workspace / "data.txt").write_text("data")
    tool = MoveFileTool(workspace)
    result = await tool.execute(source="data.txt", destination="../../evil.txt")
    assert "Error" in result


async def test_move_source_not_found(workspace):
    tool = MoveFileTool(workspace)
    result = await tool.execute(source="missing.txt", destination="dest.txt")
    assert "Error" in result
    assert "not found" in result.lower()


# --- SearchFilesTool ---


async def test_search_finds_pattern(workspace):
    (workspace / "a.py").write_text("def hello():\n    pass\n")
    (workspace / "b.py").write_text("def world():\n    pass\n")
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern="hello")
    assert "a.py:1:" in result
    assert "hello" in result


async def test_search_case_insensitive(workspace):
    (workspace / "file.txt").write_text("Hello World\n")
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern="hello", case_sensitive=False)
    assert "file.txt:1:" in result


async def test_search_skips_binary_files(workspace):
    (workspace / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"findme")
    (workspace / "code.py").write_text("findme here\n")
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern="findme")
    assert "code.py" in result
    assert "image.png" not in result


async def test_search_regex_pattern(workspace):
    (workspace / "code.py").write_text("x = 42\ny = 100\nz = 7\n")
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern=r"\d{3}", is_regex=True)
    assert "code.py:2:" in result
    assert "100" in result


async def test_search_truncates_at_max_matches(workspace):
    lines = "\n".join(f"match line {i}" for i in range(250))
    (workspace / "big.txt").write_text(lines)
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern="match")
    assert "truncated at 200 matches" in result


async def test_search_no_matches(workspace):
    (workspace / "empty.txt").write_text("nothing here\n")
    tool = SearchFilesTool(workspace)
    result = await tool.execute(pattern="zzzzzzz")
    assert "No matches found" in result

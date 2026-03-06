import pytest

from sideclaw.runtime.models import ApprovalRequirement
from sideclaw.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool


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
    assert tool.approval_requirement(
        path="edit.txt",
        old_text="original",
        new_text="changed",
    ) == ApprovalRequirement.unless_session_approved
    assert tool.approval_key(
        path="edit.txt",
        old_text="original",
        new_text="changed",
    ) == "fs:edit_file"


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

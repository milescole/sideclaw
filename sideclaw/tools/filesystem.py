"""Filesystem tools: read, write, edit, list."""

from pathlib import Path
from typing import Any

from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.base import Tool, truncate_tool_output


class _FsTool(Tool):
    """Base for filesystem tools with workspace sandboxing."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()

    def _resolve(self, path: str) -> Path:
        """Resolve path within workspace, blocking traversal."""
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {path}")

        resolved = (self._workspace / candidate).resolve()
        if not resolved.is_relative_to(self._workspace):
            raise ValueError(f"Path outside workspace: {path}")
        return resolved


class ReadFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"}
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            p = self._resolve(kwargs["path"])
            if not p.exists():
                return f"Error: File not found: {kwargs['path']}"
            return truncate_tool_output(p.read_text())
        except ValueError as e:
            return f"Error: {e}"


class WriteFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file (creates directories as needed)"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        return ApprovalRequirement.unless_session_approved

    def approval_key(self, **kwargs: Any) -> str:
        return "fs:write_file"

    def approval_subject(self, **kwargs: Any) -> str:
        return kwargs["path"]

    def approval_action_type(self, **kwargs: Any) -> str:
        return "file_write"

    def approval_description(self, **kwargs: Any) -> str:
        return "file write"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            p = self._resolve(kwargs["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(kwargs["content"])
            return f"Wrote {len(kwargs['content'])} bytes to {kwargs['path']}"
        except ValueError as e:
            return f"Error: {e}"


class EditFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Replace text in a file"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        return ApprovalRequirement.unless_session_approved

    def approval_key(self, **kwargs: Any) -> str:
        return "fs:edit_file"

    def approval_subject(self, **kwargs: Any) -> str:
        return kwargs["path"]

    def approval_action_type(self, **kwargs: Any) -> str:
        return "file_edit"

    def approval_description(self, **kwargs: Any) -> str:
        return "file edit"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "old_text": {"type": "string", "description": "Text to find"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            p = self._resolve(kwargs["path"])
            if not p.exists():
                return f"Error: File not found: {kwargs['path']}"
            content = p.read_text()
            if kwargs["old_text"] not in content:
                return f"Error: Text not found in {kwargs['path']}"
            content = content.replace(kwargs["old_text"], kwargs["new_text"], 1)
            p.write_text(content)
            return f"Edited {kwargs['path']}"
        except ValueError as e:
            return f"Error: {e}"


class ListDirTool(_FsTool):
    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List files and directories"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to workspace"}
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            p = self._resolve(kwargs["path"])
            if not p.is_dir():
                return f"Error: Not a directory: {kwargs['path']}"
            entries = []
            for item in sorted(p.iterdir()):
                suffix = "/" if item.is_dir() else ""
                entries.append(f"{item.name}{suffix}")
            return "\n".join(entries) if entries else "(empty directory)"
        except ValueError as e:
            return f"Error: {e}"

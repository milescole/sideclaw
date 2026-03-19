"""Filesystem tools: read, write, edit, list, append, move, search."""

import re
from pathlib import Path
from typing import Any

from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.base import Tool, truncate_tool_output

_BINARY_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".flv", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".o", ".a", ".lib", ".class", ".jar",
})
_MAX_SEARCH_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
_MAX_SEARCH_MATCHES = 200


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


class AppendFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "append_file"

    @property
    def description(self) -> str:
        return "Append content to a file (creates it if missing)"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        return ApprovalRequirement.unless_session_approved

    def approval_key(self, **kwargs: Any) -> str:
        return "fs:append_file"

    def approval_subject(self, **kwargs: Any) -> str:
        return kwargs["path"]

    def approval_action_type(self, **kwargs: Any) -> str:
        return "file_append"

    def approval_description(self, **kwargs: Any) -> str:
        return "file append"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "content": {"type": "string", "description": "Content to append"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            p = self._resolve(kwargs["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as f:
                f.write(kwargs["content"])
            return f"Appended {len(kwargs['content'])} bytes to {kwargs['path']}"
        except ValueError as e:
            return f"Error: {e}"


class MoveFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "move_file"

    @property
    def description(self) -> str:
        return "Move or rename a file within the workspace"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        return ApprovalRequirement.unless_session_approved

    def approval_key(self, **kwargs: Any) -> str:
        return "fs:move_file"

    def approval_subject(self, **kwargs: Any) -> str:
        return f"{kwargs['source']} -> {kwargs['destination']}"

    def approval_action_type(self, **kwargs: Any) -> str:
        return "file_move"

    def approval_description(self, **kwargs: Any) -> str:
        return "file move"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path relative to workspace"},
                "destination": {"type": "string", "description": "Destination path relative to workspace"},
            },
            "required": ["source", "destination"],
        }

    async def execute(self, **kwargs) -> str:
        try:
            src = self._resolve(kwargs["source"])
            dest = self._resolve(kwargs["destination"])
            if not src.exists():
                return f"Error: Source not found: {kwargs['source']}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            return f"Moved {kwargs['source']} to {kwargs['destination']}"
        except ValueError as e:
            return f"Error: {e}"


class SearchFilesTool(_FsTool):
    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "Search for a text pattern across files in the workspace"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
                "path": {
                    "type": "string",
                    "description": "Directory to search in (relative to workspace, default: root)",
                    "default": ".",
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "Treat pattern as regex (default: false)",
                    "default": False,
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive search (default: true)",
                    "default": True,
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, **kwargs) -> str:
        pattern_str = kwargs["pattern"]
        search_path = kwargs.get("path", ".")
        is_regex = kwargs.get("is_regex", False)
        case_sensitive = kwargs.get("case_sensitive", True)

        try:
            root = self._resolve(search_path)
        except ValueError as e:
            return f"Error: {e}"

        if not root.is_dir():
            return f"Error: Not a directory: {search_path}"

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern_str, flags) if is_regex else re.compile(
                re.escape(pattern_str), flags
            )
        except re.error as e:
            return f"Error: Invalid regex: {e}"

        matches: list[str] = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() in _BINARY_EXTENSIONS:
                continue
            try:
                if file_path.stat().st_size > _MAX_SEARCH_FILE_SIZE:
                    continue
            except OSError:
                continue
            try:
                text = file_path.read_text(errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            rel = file_path.relative_to(self._workspace)
            for line_no, line in enumerate(text.splitlines(), 1):
                if compiled.search(line):
                    matches.append(f"{rel}:{line_no}: {line.rstrip()}")
                    if len(matches) >= _MAX_SEARCH_MATCHES:
                        matches.append(f"... (truncated at {_MAX_SEARCH_MATCHES} matches)")
                        return "\n".join(matches)

        if not matches:
            return f"No matches found for: {pattern_str}"
        return "\n".join(matches)

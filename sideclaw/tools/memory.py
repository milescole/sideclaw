"""Structured tools for the canonical markdown workspace."""

from pathlib import Path
from typing import Any

from sideclaw.runtime.models import ApprovalRequirement
from sideclaw.tools.base import Tool, truncate_tool_output
from sideclaw.workspace.docs import WorkspaceDocs


class DocsGrepTool(Tool):
    """Find exact or regex matches across workspace docs."""

    def __init__(self, workspace: Path) -> None:
        self._docs = WorkspaceDocs(workspace)

    @property
    def name(self) -> str:
        return "docs_grep"

    @property
    def description(self) -> str:
        return "Search markdown docs in the workspace by exact text or regex"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text or regex to search for"},
                "path": {
                    "type": "string",
                    "description": "Workspace-relative search root",
                    "default": "docs",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob for markdown files under the search root",
                    "default": "*.md",
                },
                "context_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 2,
                },
                "max_hits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 20,
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat query as a regular expression",
                    "default": False,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            hits = self._docs.grep(
                query=kwargs["query"],
                path=kwargs.get("path", "docs"),
                glob=kwargs.get("glob", "*.md"),
                context_lines=kwargs.get("context_lines", 2),
                max_hits=kwargs.get("max_hits", 20),
                regex=kwargs.get("regex", False),
            )
        except ValueError as exc:
            return f"Error: {exc}"

        if not hits:
            return "No matches found."
        return "\n\n".join(hit.render() for hit in hits)


class MemorySearchTool(Tool):
    """Search routed workspace memory and archives."""

    def __init__(self, workspace: Path) -> None:
        self._docs = WorkspaceDocs(workspace)

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return "Search long-term memory, decisions, runbooks, and archived notes"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Memory topic or keywords to search for",
                },
                "max_hits": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        hits = self._docs.memory_search(
            query=kwargs["query"],
            max_hits=kwargs.get("max_hits", 10),
        )
        if not hits:
            return "No memory hits found."
        return "\n\n".join(hit.render() for hit in hits)


class WorkspaceReadTool(Tool):
    """Read canonical workspace docs without using generic filesystem tools."""

    def __init__(self, workspace: Path) -> None:
        self._docs = WorkspaceDocs(workspace)

    @property
    def name(self) -> str:
        return "workspace_read"

    @property
    def description(self) -> str:
        return "Read a canonical workspace document by target or safe relative path"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "enum": [
                        "agents",
                        "soul",
                        "bootstrap",
                        "index",
                        "core_beliefs",
                        "user",
                        "profile",
                        "tools",
                        "heartbeat",
                        "environment",
                        "long_term",
                    ],
                    "description": "Canonical workspace document to read",
                },
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path to read",
                },
            },
            "oneOf": [
                {"required": ["target"]},
                {"required": ["path"]},
            ],
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            relative_path, content = self._docs.read(
                target=kwargs.get("target"),
                path=kwargs.get("path"),
            )
        except ValueError as exc:
            return f"Error: {exc}"

        rendered = f"# {relative_path}\n\n{content.rstrip()}".rstrip()
        return truncate_tool_output(rendered)


class WorkspaceTreeTool(Tool):
    """List canonical workspace structure without using generic dir listing."""

    def __init__(self, workspace: Path) -> None:
        self._docs = WorkspaceDocs(workspace)

    @property
    def name(self) -> str:
        return "workspace_tree"

    @property
    def description(self) -> str:
        return "Render a bounded tree view of the workspace"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative root to inspect",
                    "default": ".",
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 8,
                    "default": 4,
                },
                "include_files": {
                    "type": "boolean",
                    "description": "Include files as well as directories",
                    "default": True,
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            tree = self._docs.tree(
                path=kwargs.get("path", "."),
                max_depth=kwargs.get("max_depth", 4),
                include_files=kwargs.get("include_files", True),
            )
        except ValueError as exc:
            return f"Error: {exc}"
        return truncate_tool_output(tree)


class MemoryWriteTool(Tool):
    """Write routed updates into the canonical workspace docs."""

    def __init__(self, workspace: Path) -> None:
        self._docs = WorkspaceDocs(workspace)
        self._workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "memory_write"

    @property
    def description(self) -> str:
        return "Write a durable update to a routed workspace document"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        return ApprovalRequirement.unless_session_approved

    def approval_key(self, **kwargs: Any) -> str:
        return f"workspace:memory_write:{kwargs['target']}"

    def approval_subject(self, **kwargs: Any) -> str:
        return kwargs["target"]

    def approval_action_type(self, **kwargs: Any) -> str:
        return "workspace_write"

    def approval_description(self, **kwargs: Any) -> str:
        return f"workspace memory write to {kwargs['target']}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "enum": [
                        "user",
                        "profile",
                        "tools",
                        "heartbeat",
                        "environment",
                        "long_term",
                        "daily_note",
                        "daily_summary",
                        "decision",
                        "runbook",
                        "active_plan",
                    ],
                },
                "content": {"type": "string", "description": "Markdown content to write"},
                "slug": {
                    "type": "string",
                    "description": "Slug for dated multi-file targets like decisions or runbooks",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format; defaults to today",
                },
                "section": {
                    "type": "string",
                    "description": "Optional section heading to upsert in singleton docs",
                },
                "append": {
                    "type": "boolean",
                    "description": "Append to existing content instead of replacing it",
                    "default": True,
                },
            },
            "required": ["target", "content"],
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "target": {"enum": ["decision", "runbook", "active_plan"]},
                        },
                        "required": ["target"],
                    },
                    "then": {"required": ["slug"]},
                }
            ],
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            path = self._docs.write(
                target=kwargs["target"],
                content=kwargs["content"],
                slug=kwargs.get("slug"),
                date=kwargs.get("date"),
                section=kwargs.get("section"),
                append=kwargs.get("append", True),
            )
        except ValueError as exc:
            return f"Error: {exc}"

        return f"Wrote workspace memory to {path.relative_to(self._workspace)}"

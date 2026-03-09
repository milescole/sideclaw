"""Workspace management module.

Owns the canonical markdown workspace layout, prompt-context routing, and
document read/search/write helpers used by the agent and memory tools.

Modules:
    - scaffold: sync_workspace_templates — seed the canonical workspace tree
    - context: WorkspaceContextManager — validate and load prompt-routed docs
    - docs: WorkspaceDocs — inspect, search, and update canonical workspace docs

Example:
    >>> from pathlib import Path
    >>> from sideclaw.workspace import (
    ...     WorkspaceContextManager,
    ...     WorkspaceDocs,
    ...     sync_workspace_templates,
    ... )
    >>>
    >>> workspace = Path("~/.sideclaw/workspace").expanduser()
    >>> sync_workspace_templates(workspace)
    >>> docs = WorkspaceDocs(workspace)
    >>> bundle = WorkspaceContextManager(
    ...     workspace,
    ...     max_context_chars=14_000,
    ...     per_file_max_chars=2_500,
    ...     max_context_files=8,
    ...     always_include=["AGENTS.md", "SOUL.md", "docs/index.md"],
    ...     enable_injection_scan=True,
    ... ).build_bundle(current_message="What should I work on next?")
"""

from sideclaw.workspace.context import WorkspaceContextManager, WorkspaceFormatError
from sideclaw.workspace.docs import SearchHit, WorkspaceDocs
from sideclaw.workspace.scaffold import sync_workspace_templates

__all__ = [
    "SearchHit",
    "WorkspaceContextManager",
    "WorkspaceDocs",
    "WorkspaceFormatError",
    "sync_workspace_templates",
]

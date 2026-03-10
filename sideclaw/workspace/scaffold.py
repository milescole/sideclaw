"""Workspace scaffold utilities."""

import shutil
from pathlib import Path

WORKSPACE_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "workspace"
BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def sync_workspace_templates(workspace: Path) -> list[Path]:
    """Create the canonical workspace scaffold without overwriting existing files."""
    workspace = workspace.expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    for source in sorted(WORKSPACE_TEMPLATE_DIR.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(WORKSPACE_TEMPLATE_DIR)
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue
        shutil.copy2(source, destination)
        created.append(destination)

    if BUILTIN_SKILLS_DIR.exists():
        for source in sorted(BUILTIN_SKILLS_DIR.rglob("SKILL.md")):
            relative = source.relative_to(BUILTIN_SKILLS_DIR)
            destination = workspace / "skills" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue
            shutil.copy2(source, destination)
            created.append(destination)

    for relative_dir in (
        "artifacts",
        "artifacts/exports",
        "artifacts/images",
        "artifacts/media",
        "artifacts/reports",
        "artifacts/tmp",
        "docs/architecture",
        "docs/domain",
        "docs/runbooks",
        "docs/decisions",
        "docs/exec-plans/active",
        "docs/exec-plans/completed",
        "docs/memory/daily",
        "docs/memory/daily-summaries",
        "docs/memory/session-summaries",
        "docs/memory/snapshots",
        "skills",
        "sessions",
    ):
        (workspace / relative_dir).mkdir(parents=True, exist_ok=True)

    return created

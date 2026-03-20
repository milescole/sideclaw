"""CLI commands for inspecting memory files and token budgets."""

from __future__ import annotations

from sideclaw.cli.render.console import print_line
from sideclaw.config.loader import get_config_path, load_config
from sideclaw.utils.tokens import count_tokens, format_token_count


def memory_show() -> None:
    """Display memory file contents and sizes."""
    config = load_config(get_config_path())
    workspace = config.workspace_path
    memory_dir = workspace / "docs" / "memory"

    print_line("Memory Files")

    if not memory_dir.exists():
        print_line("  No memory directory found.")
        return

    files = sorted(memory_dir.rglob("*.md"))
    if not files:
        print_line("  No memory files found.")
        return

    for f in files:
        content = f.read_text(encoding="utf-8").strip()
        tokens = count_tokens(content) if content else 0
        line_count = content.count("\n") + 1 if content else 0
        rel = f.relative_to(memory_dir)
        print_line(f"  {rel}: {line_count} lines, {format_token_count(tokens)} tokens")


def memory_usage() -> None:
    """Display per-file token usage against the context budget."""
    config = load_config(get_config_path())
    workspace = config.workspace_path
    memory_dir = workspace / "docs" / "memory"
    budget = config.memory.max_context_chars // 4  # rough token budget

    print_line("Memory Budget Usage")

    total_tokens = 0
    seen: set[str] = set()

    # Memory directory files
    if memory_dir.exists():
        for f in sorted(memory_dir.rglob("*.md")):
            content = f.read_text(encoding="utf-8").strip()
            if not content:
                continue
            tokens = count_tokens(content)
            total_tokens += tokens
            pct = (tokens / budget * 100) if budget > 0 else 0
            rel = f.relative_to(workspace)
            seen.add(str(rel))
            print_line(
                f"  {rel}: {format_token_count(tokens)} tokens ({pct:.1f}% of budget)"
            )

    # Hot-path singleton docs (skip if already counted above)
    for rel_path in config.memory.always_include:
        if rel_path in seen:
            continue
        doc = workspace / rel_path
        if doc.exists():
            content = doc.read_text(encoding="utf-8").strip()
            if not content:
                continue
            tokens = count_tokens(content)
            total_tokens += tokens
            pct = (tokens / budget * 100) if budget > 0 else 0
            print_line(
                f"  {rel_path}: {format_token_count(tokens)} tokens ({pct:.1f}% of budget)"
            )

    if budget > 0:
        total_pct = total_tokens / budget * 100
        print_line(
            f"  Total: {format_token_count(total_tokens)} tokens "
            f"({total_pct:.1f}% of {format_token_count(budget)} budget)"
        )
    else:
        print_line(f"  Total: {format_token_count(total_tokens)} tokens")

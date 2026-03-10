"""Build role snapshots and refs from Playwright ARIA snapshots."""

# ruff: noqa: PLR0911

import re
from typing import Any

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)

CONTENT_ROLES = frozenset(
    {
        "article",
        "cell",
        "columnheader",
        "gridcell",
        "heading",
        "listitem",
        "main",
        "navigation",
        "region",
        "rowheader",
    }
)

STRUCTURAL_ROLES = frozenset(
    {
        "application",
        "directory",
        "document",
        "generic",
        "grid",
        "group",
        "list",
        "menu",
        "menubar",
        "none",
        "presentation",
        "row",
        "rowgroup",
        "table",
        "tablist",
        "toolbar",
        "tree",
        "treegrid",
    }
)


def _get_indent_level(line: str) -> int:
    match = re.match(r"^(\s*)", line)
    return int(len(match.group(1)) / 2) if match else 0


def _create_tracker() -> dict[str, Any]:
    counts: dict[str, int] = {}
    refs_by_key: dict[str, list[str]] = {}

    def get_key(role: str, name: str | None) -> str:
        return f"{role}:{name or ''}"

    def get_next_index(role: str, name: str | None) -> int:
        key = get_key(role, name)
        current = counts.get(key, 0)
        counts[key] = current + 1
        return current

    def track_ref(role: str, name: str | None, ref: str) -> None:
        key = get_key(role, name)
        refs_by_key.setdefault(key, []).append(ref)

    def get_duplicate_keys() -> set[str]:
        return {key for key, refs in refs_by_key.items() if len(refs) > 1}

    return {
        "get_duplicate_keys": get_duplicate_keys,
        "get_key": get_key,
        "get_next_index": get_next_index,
        "track_ref": track_ref,
    }


def _remove_nth_from_non_duplicates(
    refs: dict[str, dict[str, Any]], tracker: dict[str, Any]
) -> None:
    duplicate_keys = tracker["get_duplicate_keys"]()
    for ref_data in refs.values():
        key = tracker["get_key"](ref_data["role"], ref_data.get("name"))
        if key not in duplicate_keys and "nth" in ref_data:
            del ref_data["nth"]


def _compact_tree(tree: str) -> str:
    lines = tree.split("\n")
    result: list[str] = []
    for index, line in enumerate(lines):
        if "[ref=" in line:
            result.append(line)
            continue
        if ":" in line and not line.rstrip().endswith(":"):
            result.append(line)
            continue
        current_indent = _get_indent_level(line)
        has_relevant_child = False
        for candidate in lines[index + 1 :]:
            if _get_indent_level(candidate) <= current_indent:
                break
            if "[ref=" in candidate:
                has_relevant_child = True
                break
        if has_relevant_child:
            result.append(line)
    return "\n".join(result)


def _process_line(
    line: str,
    refs: dict[str, dict[str, Any]],
    options: dict[str, Any],
    tracker: dict[str, Any],
    next_ref: Any,
) -> str | None:
    depth = _get_indent_level(line)
    max_depth = options.get("max_depth")
    if max_depth is not None and depth > max_depth:
        return None

    match = re.match(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$', line)
    if not match:
        return None if options.get("interactive") else line

    prefix, role_raw, name, suffix = match.groups()
    if role_raw.startswith("/"):
        return None if options.get("interactive") else line

    role = role_raw.lower()
    is_interactive = role in INTERACTIVE_ROLES
    is_content = role in CONTENT_ROLES
    is_structural = role in STRUCTURAL_ROLES

    if options.get("interactive") and not is_interactive:
        return None
    if options.get("compact") and is_structural and not name:
        return None

    should_have_ref = is_interactive or (is_content and name)
    if not should_have_ref:
        return line

    ref = next_ref()
    nth = tracker["get_next_index"](role, name)
    tracker["track_ref"](role, name, ref)
    refs[ref] = {"role": role, "name": name, "nth": nth}

    enhanced = f"{prefix}{role_raw}"
    if name:
        enhanced += f' "{name}"'
    enhanced += f" [ref={ref}]"
    if nth > 0:
        enhanced += f" [nth={nth}]"
    if suffix:
        enhanced += suffix
    return enhanced


def build_role_snapshot_from_aria(
    aria_snapshot: str,
    *,
    interactive: bool = False,
    compact: bool = False,
    max_depth: int | None = None,
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build a readable tree plus stable refs from Playwright aria output."""
    options = {
        "compact": compact,
        "interactive": interactive,
        "max_depth": max_depth,
    }
    lines = aria_snapshot.split("\n")
    refs: dict[str, dict[str, Any]] = {}
    tracker = _create_tracker()
    counter = [0]

    def next_ref() -> str:
        counter[0] += 1
        return f"e{counter[0]}"

    if interactive:
        result_lines: list[str] = []
        for line in lines:
            depth = _get_indent_level(line)
            if max_depth is not None and depth > max_depth:
                continue
            match = re.match(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$', line)
            if not match:
                continue
            _, role_raw, name, suffix = match.groups()
            if role_raw.startswith("/"):
                continue
            role = role_raw.lower()
            if role not in INTERACTIVE_ROLES:
                continue
            ref = next_ref()
            nth = tracker["get_next_index"](role, name)
            tracker["track_ref"](role, name, ref)
            refs[ref] = {"role": role, "name": name, "nth": nth}
            enhanced = f"- {role_raw}"
            if name:
                enhanced += f' "{name}"'
            enhanced += f" [ref={ref}]"
            if nth > 0:
                enhanced += f" [nth={nth}]"
            if "[" in suffix:
                enhanced += suffix
            result_lines.append(enhanced)
        _remove_nth_from_non_duplicates(refs, tracker)
        snapshot = "\n".join(result_lines) or "(no interactive elements)"
        return snapshot, refs

    result_lines: list[str] = []
    for line in lines:
        processed = _process_line(line, refs, options, tracker, next_ref)
        if processed is not None:
            result_lines.append(processed)
    _remove_nth_from_non_duplicates(refs, tracker)
    tree = "\n".join(result_lines) or "(empty)"
    snapshot = _compact_tree(tree) if compact else tree
    return snapshot, refs

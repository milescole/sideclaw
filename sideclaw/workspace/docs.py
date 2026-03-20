"""Workspace document helpers for search, inspection, and durable updates."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sideclaw.utils.files import atomic_append_text, atomic_write_text
from sideclaw.workspace.context import WorkspaceContextManager

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TARGET_PATHS = {
    "agents": "AGENTS.md",
    "soul": "SOUL.md",
    "bootstrap": "BOOTSTRAP.md",
    "index": "docs/index.md",
    "core_beliefs": "docs/core-beliefs.md",
    "user": "docs/user.md",
    "profile": "docs/profile.md",
    "tools": "docs/tools.md",
    "heartbeat": "docs/heartbeat.md",
    "environment": "docs/environment.md",
    "long_term": "docs/memory/long-term.md",
}
_SEARCH_GLOBS = (
    "docs/memory/long-term.md",
    "docs/user.md",
    "docs/profile.md",
    "docs/tools.md",
    "docs/environment.md",
    "docs/decisions/**/*.md",
    "docs/runbooks/**/*.md",
    "docs/exec-plans/completed/**/*.md",
    "docs/memory/daily/**/*.md",
    "docs/memory/daily-summaries/**/*.md",
    "docs/memory/session-summaries/**/*.md",
)
_PATH_BOOSTS = (
    ("docs/memory/long-term.md", 8),
    ("docs/decisions/", 6),
    ("docs/runbooks/", 5),
    ("docs/user.md", 4),
    ("docs/profile.md", 4),
    ("docs/tools.md", 4),
    ("docs/environment.md", 4),
    ("docs/memory/daily-summaries/", 3),
    ("docs/memory/session-summaries/", 2),
    ("docs/memory/daily/", 1),
)
_HOT_PATH_SINGLETON_TARGETS = {"user", "profile", "tools", "heartbeat", "environment", "long_term"}
_MAX_MEMORY_WRITE_CHARS = 8_000
_MAX_HOT_PATH_WRITE_CHARS = 1_200


@dataclass(frozen=True)
class SearchHit:
    """A text match in the workspace."""

    relative_path: str
    line_number: int
    heading: str | None
    excerpt: str
    score: int = 0

    def render(self) -> str:
        heading = f" | heading: {self.heading}" if self.heading else ""
        return f"{self.relative_path}:{self.line_number}{heading}\n{self.excerpt}"


class WorkspaceDocs:
    """Read, search, and write the canonical workspace docs."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()

    def grep(
        self,
        *,
        query: str,
        path: str = "docs",
        glob: str = "*.md",
        context_lines: int = 2,
        max_hits: int = 20,
        regex: bool = False,
    ) -> list[SearchHit]:
        """Find exact or regex matches across workspace markdown files."""
        root = self._resolve(path)
        if not root.exists():
            return []

        matcher = re.compile(query, re.IGNORECASE) if regex else None
        hits: list[SearchHit] = []
        for file_path in self._iter_markdown_files(root, glob):
            lines = file_path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                matched = bool(matcher.search(line)) if matcher else query.lower() in line.lower()
                if not matched:
                    continue
                hits.append(
                    SearchHit(
                        relative_path=str(file_path.relative_to(self._workspace)),
                        line_number=index + 1,
                        heading=self._find_heading(lines, index),
                        excerpt=self._build_excerpt(lines, index, context_lines),
                    )
                )
                if len(hits) >= max_hits:
                    return hits
        return hits

    def read(
        self,
        *,
        target: str | None = None,
        path: str | None = None,
    ) -> tuple[str, str]:
        """Read a canonical target or workspace-relative file."""
        if bool(target) == bool(path):
            msg = "Provide exactly one of 'target' or 'path'"
            raise ValueError(msg)

        if target:
            resolved = self._target_path(target=target, slug=None, date=None)
        else:
            resolved = self._resolve(path or "")
        if not resolved.exists():
            missing = target or path or ""
            msg = f"File not found: {missing}"
            raise ValueError(msg)
        if not resolved.is_file():
            requested = target or path or ""
            msg = f"Not a file: {requested}"
            raise ValueError(msg)

        relative_path = str(resolved.relative_to(self._workspace))
        return relative_path, resolved.read_text(encoding="utf-8")

    def tree(
        self,
        *,
        path: str = ".",
        max_depth: int = 4,
        include_files: bool = True,
    ) -> str:
        """Render a bounded workspace tree for inspection."""
        if max_depth < 0:
            msg = f"Invalid max_depth: {max_depth}"
            raise ValueError(msg)

        root = self._resolve(path)
        if not root.exists():
            msg = f"Path not found: {path}"
            raise ValueError(msg)

        label = "." if root == self._workspace else str(root.relative_to(self._workspace))
        lines = [f"{label}/" if root.is_dir() else label]
        if root.is_file():
            return "\n".join(lines)

        lines.extend(
            self._tree_lines(
                root=root,
                depth=0,
                max_depth=max_depth,
                include_files=include_files,
            )
        )
        return "\n".join(lines)

    def memory_search(self, *, query: str, max_hits: int = 10) -> list[SearchHit]:
        """Search routed durable memory and archives with simple ranking."""
        terms = [term for term in re.findall(r"[a-z0-9_/-]+", query.lower()) if len(term) >= 2]
        query_lower = query.lower().strip()
        ranked: list[SearchHit] = []

        for file_path in self._iter_search_files():
            text = file_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            line_scores: list[tuple[int, int]] = []
            for index, line in enumerate(lines):
                line_lower = line.lower()
                score = 0
                if query_lower and query_lower in line_lower:
                    score += 10
                score += sum(line_lower.count(term) for term in terms)
                if score:
                    line_scores.append((score, index))

            content_lower = text.lower()
            total_score = sum(score for score, _index in line_scores)
            has_match = bool(line_scores)
            if query_lower and query_lower in content_lower:
                total_score += 5
                has_match = True
            total_score += sum(content_lower.count(term) for term in terms)
            if not has_match and not total_score:
                continue
            if not has_match:
                continue
            total_score += self._path_boost(str(file_path.relative_to(self._workspace)))
            if total_score <= 0:
                continue

            best_index = max(line_scores, key=lambda item: item[0])[1] if line_scores else 0
            ranked.append(
                SearchHit(
                    relative_path=str(file_path.relative_to(self._workspace)),
                    line_number=best_index + 1,
                    heading=self._find_heading(lines, best_index),
                    excerpt=self._build_excerpt(lines, best_index, 2),
                    score=total_score,
                )
            )

        ranked.sort(key=lambda hit: (-hit.score, hit.relative_path, hit.line_number))
        return ranked[:max_hits]

    def write(
        self,
        *,
        target: str,
        content: str,
        slug: str | None = None,
        date: str | None = None,
        section: str | None = None,
        append: bool = True,
    ) -> Path:
        """Write to a routed workspace path."""
        normalized_content = content.strip()
        if not normalized_content:
            msg = "Content is required"
            raise ValueError(msg)
        if len(normalized_content) > _MAX_MEMORY_WRITE_CHARS:
            msg = f"Content too large for workspace memory write ({len(normalized_content)} chars)"
            raise ValueError(msg)

        findings = WorkspaceContextManager._scan_context_content(normalized_content)
        if findings:
            msg = f"Unsafe content for workspace memory: {', '.join(findings)}"
            raise ValueError(msg)

        if target in _HOT_PATH_SINGLETON_TARGETS:
            if section is None:
                msg = f"Section is required for target: {target}"
                raise ValueError(msg)
            if len(normalized_content) > _MAX_HOT_PATH_WRITE_CHARS:
                msg = f"Content too large for hot-path target: {target}"
                raise ValueError(msg)

        target_path = self._target_path(target=target, slug=slug, date=date)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target == "long_term":
            self._snapshot_long_term()

        if target in _TARGET_PATHS:
            self._write_singleton_doc(
                target_path,
                content=normalized_content,
                section=section,
                append=append,
            )
        elif append and target_path.exists():
            existing = target_path.read_text(encoding="utf-8").rstrip()
            new_content = normalized_content
            if new_content and new_content not in existing:
                atomic_append_text(target_path, ("\n\n" if existing else "") + new_content)
        else:
            atomic_write_text(target_path, normalized_content.rstrip() + "\n")

        return target_path

    def update_long_term_sections(self, sections: dict[str, str]) -> Path:
        """Update long-term memory sections in a single structured write."""
        normalized_sections = {
            section: content.strip()
            for section, content in sections.items()
            if content and content.strip()
        }
        if not normalized_sections:
            msg = "At least one long-term memory section is required"
            raise ValueError(msg)

        target_path = self._workspace / _TARGET_PATHS["long_term"]
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_long_term()

        existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        frontmatter, body = self._split_frontmatter(existing)
        next_body = body.strip()
        for section, content in normalized_sections.items():
            next_body = self._upsert_section(next_body, section, content, append=False)

        rendered = f"{frontmatter}{next_body.rstrip()}\n"
        atomic_write_text(target_path, rendered)
        return target_path

    def remove_long_term_section(self, heading: str) -> str | None:
        """Remove a ## section from long-term memory. Returns removed text or None."""
        target_path = self._workspace / _TARGET_PATHS["long_term"]
        if not target_path.exists():
            return None

        self._snapshot_long_term()
        existing = target_path.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(existing)
        lines = body.splitlines()

        section_heading = f"## {heading}"
        start = None
        end = None
        for index, line in enumerate(lines):
            if line.strip() == section_heading:
                start = index
                continue
            if start is not None and line.startswith("## "):
                end = index
                break
        if start is None:
            return None
        if end is None:
            end = len(lines)

        removed = "\n".join(lines[start:end]).strip()
        remaining = lines[:start] + lines[end:]
        rendered = f"{frontmatter}{chr(10).join(remaining).strip()}\n"
        atomic_write_text(target_path, rendered)
        return removed

    def remove_long_term_matching(self, keyword: str) -> list[str]:
        """Remove lines containing *keyword* from long-term memory. Returns removed lines."""
        target_path = self._workspace / _TARGET_PATHS["long_term"]
        if not target_path.exists():
            return []

        self._snapshot_long_term()
        existing = target_path.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(existing)
        keyword_lower = keyword.lower()

        kept: list[str] = []
        removed: list[str] = []
        for line in body.splitlines():
            if keyword_lower in line.lower() and not line.startswith("## "):
                removed.append(line)
            else:
                kept.append(line)

        if not removed:
            return []

        rendered = f"{frontmatter}{chr(10).join(kept).strip()}\n"
        atomic_write_text(target_path, rendered)
        return removed

    def _target_path(self, *, target: str, slug: str | None, date: str | None) -> Path:
        resolved_date = self._resolve_date(date)
        if target in _TARGET_PATHS:
            return self._workspace / _TARGET_PATHS[target]
        if target == "daily_note":
            return self._workspace / "docs" / "memory" / "daily" / f"{resolved_date}.md"
        if target == "daily_summary":
            return self._workspace / "docs" / "memory" / "daily-summaries" / f"{resolved_date}.md"
        safe_slug = self._slugify(slug or "")
        if target == "decision":
            return self._workspace / "docs" / "decisions" / f"{resolved_date}-{safe_slug}.md"
        if target == "runbook":
            return self._workspace / "docs" / "runbooks" / f"{resolved_date}-{safe_slug}.md"
        if target == "active_plan":
            return (
                self._workspace
                / "docs"
                / "exec-plans"
                / "active"
                / f"{resolved_date}-{safe_slug}.md"
            )
        msg = f"Unsupported workspace target: {target}"
        raise ValueError(msg)

    def _write_singleton_doc(
        self,
        path: Path,
        *,
        content: str,
        section: str | None,
        append: bool,
    ) -> None:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        frontmatter, body = self._split_frontmatter(existing)
        if section:
            next_body = self._upsert_section(body.strip(), section, content.strip(), append=append)
        else:
            next_body = body.strip()
            addition = content.strip()
            if addition and addition not in next_body:
                next_body = f"{next_body}\n\n{addition}".strip() if next_body else addition
        rendered = f"{frontmatter}{next_body.rstrip()}\n"
        atomic_write_text(path, rendered)

    def _snapshot_long_term(self) -> None:
        long_term = self._workspace / "docs" / "memory" / "long-term.md"
        if not long_term.exists():
            return
        snapshot_dir = self._workspace / "docs" / "memory" / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        snapshot = snapshot_dir / f"{timestamp}-long-term.md"
        atomic_write_text(snapshot, long_term.read_text(encoding="utf-8"))

    def _iter_markdown_files(self, root: Path, glob: str) -> list[Path]:
        files = [path for path in root.rglob(glob) if path.is_file()]
        files.sort()
        return files

    def _iter_search_files(self) -> list[Path]:
        files: set[Path] = set()
        for pattern in _SEARCH_GLOBS:
            files.update(path for path in self._workspace.glob(pattern) if path.is_file())
        return sorted(files)

    def _tree_lines(
        self,
        *,
        root: Path,
        depth: int,
        max_depth: int,
        include_files: bool,
    ) -> list[str]:
        if depth >= max_depth:
            return []

        entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        visible_entries = [entry for entry in entries if include_files or entry.is_dir()]
        lines: list[str] = []
        for entry in visible_entries:
            indent = "  " * (depth + 1)
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{indent}{entry.name}{suffix}")
            if entry.is_dir():
                lines.extend(
                    self._tree_lines(
                        root=entry,
                        depth=depth + 1,
                        max_depth=max_depth,
                        include_files=include_files,
                    )
                )
        return lines

    def _resolve(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            msg = f"Absolute paths are not allowed: {relative_path}"
            raise ValueError(msg)
        resolved = (self._workspace / candidate).resolve()
        if not resolved.is_relative_to(self._workspace):
            msg = f"Path outside workspace: {relative_path}"
            raise ValueError(msg)
        return resolved

    @staticmethod
    def _resolve_date(date: str | None) -> str:
        value = date or datetime.now(UTC).strftime("%Y-%m-%d")
        if not _DATE_RE.match(value):
            msg = f"Invalid date: {value}"
            raise ValueError(msg)
        return value

    @staticmethod
    def _slugify(slug: str) -> str:
        cleaned = _SLUG_RE.sub("-", slug.lower()).strip("-")
        if not cleaned:
            msg = "Slug is required for this target"
            raise ValueError(msg)
        return cleaned

    @staticmethod
    def _find_heading(lines: list[str], index: int) -> str | None:
        for line in reversed(lines[: index + 1]):
            match = _HEADING_RE.match(line.strip())
            if match:
                return match.group(2).strip()
        return None

    @staticmethod
    def _build_excerpt(lines: list[str], index: int, context_lines: int) -> str:
        start = max(index - context_lines, 0)
        end = min(index + context_lines + 1, len(lines))
        return "\n".join(lines[start:end]).strip()

    @staticmethod
    def _path_boost(relative_path: str) -> int:
        for prefix, boost in _PATH_BOOSTS:
            if relative_path == prefix or relative_path.startswith(prefix):
                return boost
        return 0

    @staticmethod
    def _split_frontmatter(content: str) -> tuple[str, str]:
        match = _FRONTMATTER_RE.match(content)
        if not match:
            return "", content
        return match.group(0), content[match.end() :]

    @staticmethod
    def _upsert_section(content: str, section: str, addition: str, *, append: bool) -> str:
        heading = f"## {section}"
        if heading not in content:
            return f"{content.rstrip()}\n\n{heading}\n\n{addition}".strip()

        lines = content.splitlines()
        start = None
        end = None
        for index, line in enumerate(lines):
            if line.strip() == heading:
                start = index
                continue
            if start is not None and line.startswith("## "):
                end = index
                break
        if start is None:
            return f"{content.rstrip()}\n\n{heading}\n\n{addition}".strip()
        if end is None:
            end = len(lines)

        section_lines = lines[start:end]
        section_body = "\n".join(section_lines[1:]).strip()
        if addition in section_body:
            return content.strip()
        if append and section_body:
            next_body = f"{section_body}\n\n{addition}".strip()
        else:
            next_body = addition
        replacement = [heading, "", next_body]
        updated = lines[:start] + replacement + lines[end:]
        return "\n".join(updated).strip()

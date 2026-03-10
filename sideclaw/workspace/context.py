"""Workspace-aware markdown context loading."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

TRUNCATION_MARKER = "\n... (truncated for context budget)"
CONTEXT_TRUNCATE_HEAD_RATIO = 0.7
CONTEXT_TRUNCATE_TAIL_RATIO = 0.2

_CONTEXT_THREAT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), threat)
    for pattern, threat in (
        (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
        (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
        (r"system\s+prompt\s+override", "sys_prompt_override"),
        (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
        (
            r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don't\s+have)\s+"
            r"(restrictions|limits|rules)",
            "bypass_restrictions",
        ),
        (
            r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->",
            "html_comment_injection",
        ),
        (r"<\s*div\s+style\s*=\s*[\"'].*display\s*:\s*none", "hidden_div"),
        (r"translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)", "translate_execute"),
        (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
        (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)", "read_secrets"),
    )
)
_CONTEXT_INVISIBLE_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}
_SEARCH_ONLY_PREFIXES = (
    "docs/memory/daily/",
    "docs/memory/daily-summaries/",
    "docs/memory/session-summaries/",
    "docs/exec-plans/completed/",
)
_REQUIRED_FILES = (
    "AGENTS.md",
    "SOUL.md",
    "docs/index.md",
    "docs/core-beliefs.md",
    "docs/user.md",
    "docs/profile.md",
    "docs/tools.md",
    "docs/heartbeat.md",
    "docs/environment.md",
    "docs/memory/long-term.md",
)
class WorkspaceFormatError(RuntimeError):
    """Raised when a workspace does not match the canonical markdown layout."""


@dataclass(frozen=True)
class WorkspaceContextSection:
    """A single injected markdown section."""

    relative_path: str
    title: str
    content: str
    frontmatter: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        """Render the section for prompt injection."""
        return f"## {self.title}\n\n{self.content}"


@dataclass(frozen=True)
class WorkspaceContextBundle:
    """Structured markdown context bundle returned to PromptBuilder."""

    sections: list[WorkspaceContextSection]
    warnings: list[str]
    bootstrap_mode: bool

    def render(self) -> str:
        """Render all sections into a single system-prompt block."""
        return "\n\n---\n\n".join(section.render() for section in self.sections if section.content)


class WorkspaceContextManager:
    """Load and route canonical workspace markdown files."""

    def __init__(  # noqa: PLR0913
        self,
        workspace: Path,
        *,
        max_context_chars: int,
        per_file_max_chars: int,
        max_context_files: int,
        always_include: list[str],
        enable_injection_scan: bool,
    ) -> None:
        self._workspace = workspace
        self._max_context_chars = max_context_chars
        self._per_file_max_chars = per_file_max_chars
        self._max_context_files = max_context_files
        self._always_include = always_include
        self._enable_injection_scan = enable_injection_scan

    def build_bundle(  # noqa: C901
        self,
        *,
        current_message: str = "",
        history: list[dict[str, Any]] | None = None,
    ) -> WorkspaceContextBundle:
        """Build the routed workspace context bundle."""
        bootstrap_mode = (self._workspace / "BOOTSTRAP.md").exists()
        self._validate_workspace()

        warnings: list[str] = []
        sections: list[WorkspaceContextSection] = []
        total_chars = 0
        routed_section_count = 0
        seen: set[str] = set()

        baseline_paths = list(self._always_include)
        if bootstrap_mode:
            baseline_paths.append("BOOTSTRAP.md")
        routed_paths, routing_warnings = self._rank_routed_paths(current_message, history or [], seen)
        warnings.extend(routing_warnings)
        for relative_path in [*baseline_paths, *routed_paths]:
            if relative_path in seen:
                continue
            seen.add(relative_path)
            loaded = self._load_section(relative_path)
            if loaded is None:
                continue

            if loaded.content:
                rendered = loaded.render()
                remaining_chars = self._max_context_chars - total_chars
                if remaining_chars <= 0:
                    break
                if len(rendered) > remaining_chars:
                    trimmed_content = self._truncate_to_budget(
                        loaded.content,
                        remaining_chars,
                        loaded.title,
                    )
                    if not trimmed_content:
                        break
                    loaded = WorkspaceContextSection(
                        relative_path=loaded.relative_path,
                        title=loaded.title,
                        content=trimmed_content,
                        frontmatter=loaded.frontmatter,
                    )

            sections.append(loaded)
            total_chars += len(loaded.render())
            is_routed_path = relative_path in routed_paths
            if is_routed_path:
                routed_section_count += 1
            if total_chars >= self._max_context_chars:
                break
            if routed_section_count >= self._max_context_files:
                break

        return WorkspaceContextBundle(
            sections=sections,
            warnings=warnings,
            bootstrap_mode=bootstrap_mode,
        )

    def _validate_workspace(self) -> None:
        missing = [path for path in _REQUIRED_FILES if not (self._workspace / path).exists()]
        if missing:
            missing_files = ", ".join(missing)
            msg = (
                "Workspace is missing canonical markdown context files: "
                f"{missing_files}. Run 'sideclaw onboard' or migrate the workspace "
                "to the AGENTS.md + docs/ layout."
            )
            raise WorkspaceFormatError(msg)

    def _load_section(self, relative_path: str) -> WorkspaceContextSection | None:
        path = self._workspace / relative_path
        if not path.exists() or not path.is_file():
            return None

        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None

        frontmatter, body = self._parse_frontmatter(raw)
        content = body.strip() or raw

        if self._enable_injection_scan:
            findings = self._scan_context_content(content)
            if findings:
                logger.warning(
                    "Blocked workspace context file {} due to {}",
                    relative_path,
                    ", ".join(findings),
                )
                return None

        truncated = self._truncate_text(content, self._per_file_max_chars, relative_path)
        return WorkspaceContextSection(
            relative_path=relative_path,
            title=relative_path,
            content=truncated,
            frontmatter=frontmatter,
        )

    def _list_active_plan_paths(self) -> list[str]:
        active_dir = self._workspace / "docs" / "exec-plans" / "active"
        if not active_dir.exists():
            return []
        return [
            str(path.relative_to(self._workspace))
            for path in sorted(active_dir.glob("*.md"))
            if path.is_file()
        ]

    def _rank_routed_paths(
        self,
        current_message: str,
        history: list[dict[str, Any]],
        seen: set[str],
    ) -> tuple[list[str], list[str]]:
        selection_text = " ".join(
            [current_message, *[str(message.get("content") or "") for message in history[-6:]]]
        ).lower()
        if not selection_text.strip():
            return [], []

        scored: list[tuple[int, str]] = []
        warnings: list[str] = []
        selection_terms = self._extract_terms(selection_text)
        docs_dir = self._workspace / "docs"
        if not docs_dir.exists():
            return [], []
        for path in sorted(docs_dir.rglob("*.md")):
            relative_path = str(path.relative_to(self._workspace))
            if relative_path in seen:
                continue
            if relative_path in self._always_include:
                continue
            if any(relative_path.startswith(prefix) for prefix in _SEARCH_ONLY_PREFIXES):
                continue

            raw = path.read_text(encoding="utf-8").strip()
            frontmatter, body = self._parse_frontmatter(raw)
            has_frontmatter = raw.startswith("---\n")
            has_valid_frontmatter = has_frontmatter and bool(frontmatter)

            score = 0
            score += self._match_terms(frontmatter.get("tags"), selection_text) * 3
            score += self._match_terms(frontmatter.get("read_when"), selection_text) * 4
            score += self._match_terms(frontmatter.get("summary"), selection_text) * 3
            score += self._term_overlap_score(relative_path, selection_terms) * 2

            headings = "\n".join(
                line.strip()[2:].strip()
                for line in body.splitlines()
                if re.match(r"^#{1,6}\s+", line.strip())
            )
            score += self._term_overlap_score(headings, selection_terms) * 2
            score += self._term_overlap_score(body[:4_000], selection_terms)

            if score <= 0:
                continue

            if has_frontmatter and not has_valid_frontmatter:
                warnings.append(f"Malformed frontmatter in routed doc: {relative_path}")
            elif not has_frontmatter:
                warnings.append(f"Missing frontmatter in routed doc: {relative_path}")

            scored.append((score, relative_path))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [relative_path for _score, relative_path in scored], warnings

    @staticmethod
    def _match_terms(value: Any, selection_text: str) -> int:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            return 0
        return sum(
            1 for candidate in candidates if candidate and candidate.lower() in selection_text
        )

    @staticmethod
    def _extract_terms(text: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text.lower())
            if len(term) >= 3
        }

    @staticmethod
    def _term_overlap_score(text: str, selection_terms: set[str]) -> int:
        if not text or not selection_terms:
            return 0
        text_terms = WorkspaceContextManager._extract_terms(text)
        return len(text_terms & selection_terms)

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        lines = content.splitlines()
        closing_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                closing_index = index
                break
        if closing_index is None:
            return {}, content

        metadata: dict[str, Any] = {}
        current_key: str | None = None
        for line in lines[1:closing_index]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- ") and current_key is not None:
                metadata.setdefault(current_key, [])
                metadata[current_key].append(stripped[2:].strip().strip("\"'"))
                continue
            if ":" not in stripped:
                current_key = None
                continue
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            if not value:
                metadata[key] = []
                current_key = key
                continue
            metadata[key] = WorkspaceContextManager._coerce_frontmatter_value(value)
            current_key = key

        body = "\n".join(lines[closing_index + 1 :]).strip()
        return metadata, body

    @staticmethod
    def _coerce_frontmatter_value(value: str) -> Any:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if value.startswith("[") and value.endswith("]"):
            return [item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()]
        return value.strip("\"'")

    @staticmethod
    def _scan_context_content(content: str) -> list[str]:
        findings: list[str] = []
        for char in _CONTEXT_INVISIBLE_CHARS:
            if char in content:
                findings.append(f"invisible unicode U+{ord(char):04X}")
        for pattern, threat in _CONTEXT_THREAT_PATTERNS:
            if pattern.search(content):
                findings.append(threat)
        return findings

    def _truncate_to_budget(self, text: str, remaining_chars: int, title: str) -> str:
        header_chars = len(f"## {title}\n\n")
        budget = remaining_chars - header_chars
        if budget <= 0:
            return ""
        return self._truncate_text(text, budget, title)

    @staticmethod
    def _truncate_text(text: str, max_chars: int, label: str) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= len(TRUNCATION_MARKER):
            return text[:max_chars]
        head_chars = int(max_chars * CONTEXT_TRUNCATE_HEAD_RATIO)
        tail_chars = int(max_chars * CONTEXT_TRUNCATE_TAIL_RATIO)
        if head_chars + tail_chars >= max_chars - len(TRUNCATION_MARKER):
            return text[: max_chars - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
        head = text[:head_chars]
        tail = text[-tail_chars:] if tail_chars else ""
        marker = (
            f"\n\n[...truncated {label}: kept {head_chars}+{tail_chars} of "
            f"{len(text)} chars. Use read_file to inspect the full file.]\n\n"
        )
        combined = head + marker + tail
        if len(combined) <= max_chars:
            return combined
        return combined[: max_chars - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER

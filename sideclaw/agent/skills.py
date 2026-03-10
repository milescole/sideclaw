"""Skills loader for prompt-oriented agent capabilities."""

import re
from pathlib import Path
from typing import Any

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class SkillsLoader:
    """Discover, summarize, and selectively load skills for prompt construction."""

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None) -> None:
        self._workspace = workspace
        self._workspace_skills = workspace / "skills"
        self._builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR

    def list_skills(self) -> list[dict[str, str]]:
        """List available skills with workspace override precedence."""
        skills_by_name: dict[str, dict[str, str]] = {}

        for skill_file, source in self._iter_skill_files():
            frontmatter, _body = self._parse_frontmatter(skill_file.read_text(encoding="utf-8").strip())
            name = str(frontmatter.get("name") or skill_file.parent.name)
            description = str(frontmatter.get("summary") or frontmatter.get("description") or name)
            path = self._relative_display_path(skill_file, source)

            if name in skills_by_name and source == "builtin":
                continue

            skills_by_name[name] = {
                "name": name,
                "path": path,
                "description": description,
                "source": source,
            }

        return [skills_by_name[name] for name in sorted(skills_by_name)]

    def build_skills_summary(self) -> str:
        """Build a compact summary of available skills for the system prompt."""
        skills = self.list_skills()
        if not skills:
            return ""

        lines = [
            "The following skills extend your capabilities. When one clearly matches the task,",
            "follow its instructions and use the required tools.",
            "",
            "<available_skills>",
        ]
        for skill in skills:
            lines.append(
                f'- {skill["name"]}: {skill["description"]} ({skill["path"]})'
            )
        lines.append("</available_skills>")
        return "\n".join(lines)

    def load_relevant_skills(
        self,
        *,
        current_message: str,
        history: list[dict[str, Any]],
        max_skills: int = 4,
    ) -> tuple[str, list[str]]:
        """Load full skill content for the most relevant matching skills."""
        ranked, warnings = self.rank_paths(current_message=current_message, history=history)
        sections: list[str] = []

        for item in ranked[:max_skills]:
            content = item["path_obj"].read_text(encoding="utf-8").strip()
            _frontmatter, body = self._parse_frontmatter(content)
            rendered = body.strip() or content
            if rendered:
                sections.append(f"## {item['display_path']}\n\n{rendered}")

        return "\n\n---\n\n".join(sections), warnings

    def rank_paths(
        self,
        *,
        current_message: str,
        history: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Rank skill files by relevance to the current request."""
        selection_text = " ".join(
            [current_message, *[str(message.get("content") or "") for message in history[-6:]]]
        ).lower()
        if not selection_text.strip():
            return [], []

        selection_terms = self._extract_terms(selection_text)
        scored: list[tuple[int, dict[str, Any]]] = []
        warnings: list[str] = []
        seen_names: set[str] = set()

        for skill_file, source in self._iter_skill_files():
            raw = skill_file.read_text(encoding="utf-8").strip()
            frontmatter, body = self._parse_frontmatter(raw)
            name = str(frontmatter.get("name") or skill_file.parent.name)
            if source == "builtin" and name in seen_names:
                continue

            has_frontmatter = raw.startswith("---\n")
            has_valid_frontmatter = has_frontmatter and bool(frontmatter)
            display_path = self._relative_display_path(skill_file, source)

            score = 0
            score += self._match_terms(frontmatter.get("tags"), selection_text) * 3
            score += self._match_terms(frontmatter.get("read_when"), selection_text) * 4
            score += self._match_terms(frontmatter.get("summary"), selection_text) * 3
            score += self._match_terms(frontmatter.get("description"), selection_text) * 3
            score += self._term_overlap_score(display_path, selection_terms) * 2

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
                warnings.append(f"Malformed frontmatter in skill: {display_path}")
            elif not has_frontmatter:
                warnings.append(f"Missing frontmatter in skill: {display_path}")

            scored.append(
                (
                    score,
                    {
                        "name": name,
                        "path_obj": skill_file,
                        "display_path": display_path,
                        "source": source,
                    },
                )
            )
            seen_names.add(name)

        scored.sort(key=lambda item: (-item[0], item[1]["display_path"]))
        return [item for _score, item in scored], warnings

    def _iter_skill_files(self) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        if self._workspace_skills.exists():
            for skill_file in sorted(self._workspace_skills.rglob("SKILL.md")):
                files.append((skill_file, "workspace"))
        if self._builtin_skills.exists():
            for skill_file in sorted(self._builtin_skills.rglob("SKILL.md")):
                files.append((skill_file, "builtin"))
        return files

    def _relative_display_path(self, skill_file: Path, source: str) -> str:
        if source == "workspace":
            return str(skill_file.relative_to(self._workspace))
        return f"builtin/{skill_file.relative_to(self._builtin_skills)}"

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        end = content.find("\n---\n", 4)
        if end == -1:
            return {}, content

        frontmatter_text = content[4:end].strip()
        body = content[end + 5 :]
        parsed: dict[str, Any] = {}
        current_list_key: str | None = None

        for raw_line in frontmatter_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            if line.startswith("  - ") and current_list_key:
                parsed.setdefault(current_list_key, []).append(line[4:].strip())
                continue
            if ":" not in line:
                current_list_key = None
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                parsed[key] = []
                current_list_key = key
            else:
                parsed[key] = value.strip("\"'")
                current_list_key = None

        return parsed, body

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
        text_terms = SkillsLoader._extract_terms(text)
        return len(text_terms & selection_terms)

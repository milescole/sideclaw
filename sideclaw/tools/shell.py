"""Shell execution tool."""

import asyncio
import os
import re
import shlex
from pathlib import Path
from typing import Any

from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.base import Tool, truncate_tool_output

_SAFE_ENV_PREFIXES = (
    "HOME",
    "LANG",
    "LC_",
    "LOGNAME",
    "PATH",
    "PWD",
    "SHELL",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
)
_SECRET_ENV_SUBSTRINGS = ("AUTH", "CREDENTIAL", "KEY", "PASSWD", "PASSWORD", "SECRET", "TOKEN")
_DEFAULT_DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.IGNORECASE | re.DOTALL), desc)
    for p, desc in (
        (r"\brm\s+-[^\s]*r[^\s]*\b", "recursive delete"),
        (r"\bdel\s+/[fq]\b", "forced delete"),
        (r"\brmdir\s+/s\b", "recursive directory delete"),
        (r"(?:^|[;&|]\s*)format\b", "disk format"),
        (r"\bmkfs\b", "filesystem formatting"),
        (r"\bdd\s+.*if=", "disk copy"),
        (r">\s*/dev/sd", "block device write"),
        (r"\b(shutdown|reboot|poweroff)\b", "system power command"),
        (r":\(\)\s*\{.*\};\s*:", "fork bomb"),
        (r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", "remote script piping"),
        (r"\b(bash|sh|zsh|ksh)\s+<\s*<?\s*\(\s*(curl|wget)\b", "remote script execution"),
    )
)
_APPROVAL_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(p, re.IGNORECASE | re.DOTALL), desc, key)
    for p, desc, key in (
        (
            r"\b(rm|mv|cp|install|touch|mkdir|rmdir|ln|chmod|chown)\b",
            "filesystem mutation",
            "shell:filesystem_mutation",
        ),
        (r"\b(sed|perl)\s+-i\b", "in-place file edit", "shell:filesystem_mutation"),
        (r"\btee\b", "file write via tee", "shell:filesystem_mutation"),
        (
            r"\b(apt|apt-get|brew|pip|pip3|npm|pnpm|yarn|uv|cargo)\s+"
            r"(install|remove|uninstall|add|sync)\b",
            "package manager mutation",
            "shell:package_mutation",
        ),
        (
            r"\bgit\s+(add|commit|push|clean|reset|restore|checkout|switch|stash)\b",
            "git mutation",
            "shell:git_mutation",
        ),
    )
)
_ALWAYS_APPROVAL_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(p, re.IGNORECASE | re.DOTALL), desc, key)
    for p, desc, key in (
        (r"\bgit\s+(clean|reset)\b", "destructive git mutation", "shell:destructive"),
        (
            r"\b(apt|apt-get|brew|pip|pip3|npm|pnpm|yarn|uv|cargo)\s+"
            r"(remove|uninstall)\b",
            "destructive package mutation",
            "shell:destructive",
        ),
    )
)
_SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<", "2>", "2>>", "1>", "1>>", "&>"}


class ExecTool(Tool):
    """Execute shell commands within the workspace."""

    def __init__(self, workspace: Path, timeout: int = 60) -> None:
        self._workspace = workspace.resolve()
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command within the workspace and return its output"

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        lowered = kwargs["command"].strip().lower()
        if self._match_approval_pattern(lowered, _ALWAYS_APPROVAL_PATTERNS) is not None:
            return ApprovalRequirement.always
        if self._match_approval_pattern(lowered, _APPROVAL_PATTERNS) is not None:
            return ApprovalRequirement.unless_session_approved
        return ApprovalRequirement.never

    def approval_key(self, **kwargs: Any) -> str:
        lowered = kwargs["command"].strip().lower()
        match = self._match_approval_pattern(lowered, _ALWAYS_APPROVAL_PATTERNS)
        if match is not None:
            return match[1]
        match = self._match_approval_pattern(lowered, _APPROVAL_PATTERNS)
        if match is not None:
            return match[1]
        return self.name

    def approval_subject(self, **kwargs: Any) -> str:
        return kwargs["command"].strip()

    def approval_action_type(self, **kwargs: Any) -> str:
        return "shell_command"

    def approval_description(self, **kwargs: Any) -> str:
        lowered = kwargs["command"].strip().lower()
        match = self._match_approval_pattern(lowered, _ALWAYS_APPROVAL_PATTERNS)
        if match is not None:
            return match[0]
        match = self._match_approval_pattern(lowered, _APPROVAL_PATTERNS)
        if match is not None:
            return match[0]
        return "shell command"

    def display_arguments(self, **kwargs: Any) -> dict[str, Any] | None:
        return {"command": kwargs["command"].strip()}

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"}
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs["command"]
        normalized = command.strip()
        lowered = normalized.lower()
        guard_error = self._guard_command(normalized, lowered)
        if guard_error:
            return guard_error

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace),
                env=self._build_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            return self._format_output(stdout, stderr, proc.returncode)
        except TimeoutError:
            if proc is not None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except TimeoutError:
                    pass
            return f"Error: Command timed out after {self._timeout}s"
        except (OSError, ValueError) as e:
            return f"Error: {e}"

    def _guard_command(self, normalized: str, lowered: str) -> str | None:
        for pattern, description in _DEFAULT_DENY_PATTERNS:
            if pattern.search(lowered):
                return f"Error: Command blocked by safety guard ({description})"

        for token in self._tokenize_command(normalized):
            path_error = self._validate_path_token(token)
            if path_error:
                return path_error

        return None

    def _validate_path_token(self, token: str) -> str | None:
        if not token or token in _SHELL_OPERATORS:
            return None
        if token.startswith("-") or "$" in token or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", token):
            return None
        if not self._looks_like_path(token):
            return None

        candidate = Path(token).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self._workspace / candidate).resolve()
        if not resolved.is_relative_to(self._workspace):
            return "Error: Command blocked by safety guard (path outside workspace)"
        return None

    @staticmethod
    def _looks_like_path(token: str) -> bool:
        return (
            token in {".", "..", "~"}
            or token.startswith(("/", "./", "../", "~/", ".\\", "..\\"))
            or "/" in token
            or "\\" in token
        )

    @staticmethod
    def _tokenize_command(command: str) -> list[str]:
        try:
            return shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return command.split()

    @staticmethod
    def _match_approval_pattern(
        lowered: str,
        patterns: tuple[tuple[re.Pattern[str], str, str], ...],
    ) -> tuple[str, str] | None:
        for pattern, description, approval_key in patterns:
            if pattern.search(lowered):
                return (description, approval_key)
        return None

    def _build_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key, value in os.environ.items():
            upper = key.upper()
            if any(secret in upper for secret in _SECRET_ENV_SUBSTRINGS):
                continue
            if key in _SAFE_ENV_PREFIXES or any(
                key.startswith(prefix) for prefix in _SAFE_ENV_PREFIXES
            ):
                env[key] = value
        env["PWD"] = str(self._workspace)
        return env

    @staticmethod
    def _format_output(stdout: bytes, stderr: bytes, returncode: int | None) -> str:
        parts = []

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"STDERR:\n{stderr_text}")
        if returncode is not None and returncode != 0:
            parts.append(f"(exit code {returncode})")

        output = "\n".join(parts) if parts else "(no output)"
        return truncate_tool_output(output)

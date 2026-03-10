"""Build system prompts and message lists for the LLM."""

from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any

from sideclaw.agent.skills import SkillsLoader
from sideclaw.workspace.context import WorkspaceContextManager

TRUNCATION_MARKER = "\n... (truncated for context budget)"
CHARS_PER_TOKEN_ESTIMATE = 4
RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

BASE_IDENTITY = """You are a helpful AI assistant powered by SideClaw.
You have access to tools. Use them when needed to help the user.
Be concise and direct. Ask clarifying questions when needed."""


class PromptBuilder:
    """Assembles system prompts and message lists."""

    def __init__(  # noqa: PLR0913
        self,
        workspace: Path,
        *,
        max_context_chars: int = 14_000,
        per_file_max_chars: int = 2_500,
        max_context_files: int = 8,
        always_include: list[str] | None = None,
        enable_injection_scan: bool = True,
    ) -> None:
        self._workspace = workspace
        self._max_context_chars = max_context_chars
        self._skills = SkillsLoader(workspace)
        self._workspace_context = WorkspaceContextManager(
            workspace,
            max_context_chars=max_context_chars,
            per_file_max_chars=per_file_max_chars,
            max_context_files=max_context_files,
            always_include=always_include or ["AGENTS.md", "SOUL.md", "docs/core-beliefs.md"],
            enable_injection_scan=enable_injection_scan,
        )

    def build_system_prompt(
        self,
        *,
        current_message: str = "",
        history: list[dict[str, Any]] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> str:
        """Build the full system prompt."""
        parts = [BASE_IDENTITY]
        skills_summary = self._skills.build_skills_summary()
        if skills_summary:
            parts.append(skills_summary)

        bundle = self._workspace_context.build_bundle(
            current_message=current_message,
            history=history or [],
        )
        rendered = bundle.render()
        if rendered:
            parts.append(rendered)

        loaded_skills, warnings = self._skills.load_relevant_skills(
            current_message=current_message,
            history=history or [],
        )
        if warnings:
            parts.append("Skill warnings:\n" + "\n".join(f"- {warning}" for warning in warnings))
        if loaded_skills:
            parts.append(
                "Relevant skills:\n"
                "The following skill instructions match the current request. "
                "Follow them when using tools.\n\n"
                f"{loaded_skills}"
            )

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        history: list[dict],
        current_message: str,
        *,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict]:
        """Build the full message list for the LLM."""
        system_prompt = self.build_system_prompt(
            current_message=current_message,
            history=history,
            channel=channel,
            chat_id=chat_id,
        )
        system_message = {"role": "system", "content": system_prompt}
        runtime_context = self._build_runtime_context(channel=channel, chat_id=chat_id)
        user_message = {"role": "user", "content": f"{runtime_context}\n\n{current_message}"}
        history_messages = [dict(message) for message in history]

        messages = [system_message, *history_messages, user_message]
        if self.estimate_context_chars(messages) <= self._max_context_chars:
            return messages

        self._trim_history_to_budget(history_messages, system_message, user_message)
        messages = [system_message, *history_messages, user_message]

        if self.estimate_context_chars(messages) <= self._max_context_chars:
            return messages

        self._truncate_message_to_fit(history_messages, system_message, user_message)
        return [system_message, *history_messages, user_message]

    def estimate_context_chars(self, messages: list[dict[str, Any]]) -> int:
        """Estimate the number of prompt characters across all messages."""
        return sum(self._estimate_message_chars(message) for message in messages)

    def estimate_context_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token usage from prompt characters."""
        chars = self.estimate_context_chars(messages)
        return ceil(chars / CHARS_PER_TOKEN_ESTIMATE) if chars else 0

    def _trim_history_to_budget(
        self,
        history_messages: list[dict[str, Any]],
        system_message: dict[str, Any],
        user_message: dict[str, Any],
    ) -> None:
        min_messages_to_keep = self._minimum_history_tail(history_messages)

        while len(history_messages) > min_messages_to_keep:
            messages = [system_message, *history_messages, user_message]
            if self.estimate_context_chars(messages) <= self._max_context_chars:
                return
            history_messages.pop(0)
            while history_messages and history_messages[0].get("role") != "user":
                history_messages.pop(0)

    @staticmethod
    def _minimum_history_tail(history_messages: list[dict[str, Any]]) -> int:
        """Preserve the most recent user turn and any trailing messages."""
        for index in range(len(history_messages) - 1, -1, -1):
            if history_messages[index].get("role") == "user":
                return len(history_messages) - index
        return 0

    def _truncate_message_to_fit(
        self,
        history_messages: list[dict[str, Any]],
        system_message: dict[str, Any],
        user_message: dict[str, Any],
    ) -> None:
        messages = [system_message, *history_messages, user_message]
        overflow = self.estimate_context_chars(messages) - self._max_context_chars
        if overflow <= 0:
            return

        system_content = str(system_message.get("content") or "")
        if system_content:
            target = max(len(system_content) - overflow, 0)
            system_message["content"] = self._truncate_text(system_content, target)
            messages = [system_message, *history_messages, user_message]
            overflow = self.estimate_context_chars(messages) - self._max_context_chars
            if overflow <= 0:
                return

        user_content = str(user_message.get("content") or "")
        target = max(len(user_content) - overflow, 0)
        user_message["content"] = self._truncate_text(user_content, target)

    @staticmethod
    def _build_runtime_context(*, channel: str | None, chat_id: str | None) -> str:
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"Current time: {now}"]
        if channel:
            lines.append(f"Channel: {channel}")
        if chat_id:
            lines.append(f"Chat ID: {chat_id}")
        return RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _estimate_message_chars(self, message: dict[str, Any]) -> int:
        total = len(str(message.get("role") or ""))

        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif content is not None:
            total += len(str(content))

        for tool_call in message.get("tool_calls") or []:
            total += len(str(tool_call.get("id") or ""))
            total += len(str(tool_call.get("type") or ""))
            function = tool_call.get("function") or {}
            total += len(str(function.get("name") or ""))
            total += len(str(function.get("arguments") or ""))

        total += len(str(message.get("name") or ""))
        total += len(str(message.get("tool_call_id") or ""))
        return total

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        if max_chars <= 0:
            return ""
        if max_chars <= len(TRUNCATION_MARKER):
            return text[:max_chars]
        return text[: max_chars - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER

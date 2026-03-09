"""Build system prompts and message lists for the LLM."""

from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any

from sideclaw.memory.store import MemoryStore

BOOTSTRAP_FILES = ["IDENTITY.md", "SOUL.md", "USER.md", "TOOLS.md"]
TRUNCATION_MARKER = "\n... (truncated for context budget)"
CHARS_PER_TOKEN_ESTIMATE = 4

BASE_IDENTITY = """You are a helpful AI assistant powered by SideClaw.
You have access to tools. Use them when needed to help the user.
Be concise and direct. Ask clarifying questions when needed."""


class ContextBuilder:
    """Assembles system prompts and message lists."""

    def __init__(self, workspace: Path, *, max_context_chars: int = 14_000) -> None:
        self._workspace = workspace
        self._memory = MemoryStore(workspace)
        self._max_context_chars = max_context_chars

    def build_system_prompt(
        self,
        *,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> str:
        """Build the full system prompt."""
        parts = [BASE_IDENTITY]

        # Load bootstrap files
        for filename in BOOTSTRAP_FILES:
            path = self._workspace / filename
            if path.exists():
                content = path.read_text().strip()
                if content:
                    parts.append(f"## {filename.replace('.md', '')}\n\n{content}")

        # Long-term memory
        memory_ctx = self._memory.get_memory_context()
        if memory_ctx:
            parts.append(memory_ctx)

        # Runtime context
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        runtime = f"## Runtime\n\nCurrent time: {now}"
        if channel:
            runtime += f"\nChannel: {channel}"
        if chat_id:
            runtime += f"\nChat ID: {chat_id}"
        parts.append(runtime)

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
        system_prompt = self.build_system_prompt(channel=channel, chat_id=chat_id)
        system_message = {"role": "system", "content": system_prompt}
        user_message = {"role": "user", "content": current_message}
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

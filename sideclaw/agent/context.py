"""Build system prompts and message lists for the LLM."""

from datetime import UTC, datetime
from pathlib import Path

from sideclaw.memory.store import MemoryStore

BOOTSTRAP_FILES = ["IDENTITY.md", "SOUL.md", "USER.md", "TOOLS.md"]

BASE_IDENTITY = """You are a helpful AI assistant powered by SideClaw.
You have access to tools. Use them when needed to help the user.
Be concise and direct. Ask clarifying questions when needed."""


class ContextBuilder:
    """Assembles system prompts and message lists."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._memory = MemoryStore(workspace)

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
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": current_message})
        return messages

"""Slash command dispatcher for the runtime loop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from sideclaw.config.schema import Config
    from sideclaw.memory.store import MemoryStore
    from sideclaw.providers.base import LLMProvider
    from sideclaw.session.manager import SessionManager
    from sideclaw.session.session import Session
    from sideclaw.workspace.docs import WorkspaceDocs


_COMMAND_HELP = {
    "new": "Clear session and start a new conversation",
    "compact": "Trigger memory consolidation now",
    "help": "List available slash commands",
}

COMMANDS = frozenset(_COMMAND_HELP)


class CommandHandler:
    """Dispatch slash commands without entering the LLM path."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        config: Config,
        provider: LLMProvider,
        memory_store: MemoryStore,
        workspace_docs: WorkspaceDocs,
    ) -> None:
        self._session_manager = session_manager
        self._config = config
        self._provider = provider
        self._memory_store = memory_store
        self._workspace_docs = workspace_docs

    @staticmethod
    def is_command(text: str) -> bool:
        """Return True if *text* is a recognised slash command."""
        if not text.startswith("/"):
            return False
        cmd = text.strip().lstrip("/").split(" ", maxsplit=1)[0].lower()
        return cmd in COMMANDS

    async def handle(self, text: str, session: Session) -> str:
        """Dispatch to the appropriate command handler."""
        parts = text.strip().lstrip("/").split(" ", maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = getattr(self, f"_process_{command}", None)
        if handler is None:
            return f"Unknown command: /{command}"
        return await handler(args, session)

    async def _process_new(self, args: str, session: Session) -> str:
        """Clear session and start fresh."""
        from sideclaw.runtime.execution.persistence import consolidate_memory

        try:
            await consolidate_memory(
                session=session,
                session_manager=self._session_manager,
                config=self._config,
                provider=self._provider,
                memory_store=self._memory_store,
                workspace_docs=self._workspace_docs,
            )
        except (RuntimeError, OSError, ValueError, TimeoutError) as exc:
            logger.debug(f"Consolidation on /new failed: {exc}")

        session.clear()
        self._session_manager.save(session)
        return "New conversation started."

    async def _process_compact(self, args: str, session: Session) -> str:
        """Trigger memory consolidation immediately."""
        from sideclaw.runtime.execution.persistence import consolidate_memory

        await consolidate_memory(
            session=session,
            session_manager=self._session_manager,
            config=self._config,
            provider=self._provider,
            memory_store=self._memory_store,
            workspace_docs=self._workspace_docs,
        )
        return "Memory consolidation complete."

    async def _process_help(self, args: str, session: Session) -> str:
        """List available commands."""
        lines = ["Available commands:"]
        for cmd in sorted(_COMMAND_HELP):
            lines.append(f"  /{cmd} — {_COMMAND_HELP[cmd]}")
        return "\n".join(lines)

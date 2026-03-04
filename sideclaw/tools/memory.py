"""Memory management tool for agent self-managed memory."""

from typing import Any

from sideclaw.memory.store import MemoryStore
from sideclaw.tools.base import Tool


class SaveMemoryTool(Tool):
    """Allow the agent to save information to long-term memory."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._store = memory_store

    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return (
            "Save important information to long-term memory. "
            "Use this to remember facts, preferences, and decisions across conversations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory": {
                    "type": "string",
                    "description": "Updated memory content (replaces existing memory)",
                },
                "history_entry": {
                    "type": "string",
                    "description": "Optional one-line summary for the searchable history log",
                },
            },
            "required": ["memory"],
        }

    async def execute(self, **kwargs: Any) -> str:
        self._store.write_long_term(kwargs["memory"])
        if kwargs.get("history_entry"):
            self._store.append_history(kwargs["history_entry"])
        return "Memory updated."

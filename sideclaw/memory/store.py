"""Long-term memory storage: MEMORY.md (facts) and HISTORY.md (log)."""

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from sideclaw.utils.files import atomic_append_text, atomic_write_text


class MemoryStore:
    """Two-layer memory: facts file + append-only history log."""

    def __init__(self, workspace: Path) -> None:
        self._dir = workspace / "memory"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory_file = self._dir / "MEMORY.md"
        self._history_file = self._dir / "HISTORY.md"

    def read_long_term(self) -> str:
        """Read long-term memory (MEMORY.md)."""
        if not self._memory_file.exists():
            return ""
        return self._memory_file.read_text().strip()

    def write_long_term(self, content: str) -> None:
        """Overwrite long-term memory."""
        atomic_write_text(self._memory_file, content)
        logger.debug("Updated long-term memory")

    def append_history(self, entry: str) -> None:
        """Append a timestamped entry to HISTORY.md."""
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        atomic_append_text(self._history_file, f"[{ts}] {entry}\n")

    def get_memory_context(self) -> str:
        """Get memory content for system prompt injection."""
        memory = self.read_long_term()
        if not memory:
            return ""
        return f"## Long-term Memory\n\n{memory}"

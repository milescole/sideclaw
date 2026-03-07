"""Session management for conversation history."""

import json
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from sideclaw.session.session import Session


class SessionManager:
    """Manages conversation sessions with JSONL file storage."""

    def __init__(self, session_dir: Path) -> None:
        self._dir = session_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def get_or_create(self, key: str) -> Session:
        """Get an existing session or create a new one."""
        if key in self._cache:
            return self._cache[key]
        path = self._key_to_path(key)
        if path.exists():
            session = self._load(path, key)
        else:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def save(self, session: Session) -> None:
        """Persist session to JSONL file."""
        session.updated_at = datetime.now(UTC)
        path = self._key_to_path(session.key)
        with path.open("w") as f:
            meta = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "last_consolidated": session.last_consolidated,
                "approved_approval_keys": sorted(session.approved_approval_keys),
                "pending_approval": session.pending_approval,
                "deferred_tool_calls": session.deferred_tool_calls,
            }
            f.write(json.dumps(meta) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        logger.debug(f"Session saved: {session.key} ({len(session.messages)} messages)")

    def invalidate(self, key: str) -> None:
        """Remove session from cache."""
        self._cache.pop(key, None)

    def list_sessions(self) -> list[dict]:
        """List all saved sessions."""
        sessions = []
        for path in self._dir.glob("*.jsonl"):
            try:
                first_line = path.read_text().split("\n", 1)[0]
                meta = json.loads(first_line)
                sessions.append({"key": path.stem.replace("__", ":"), **meta})
            except (json.JSONDecodeError, IndexError):
                continue
        return sessions

    def _key_to_path(self, key: str) -> Path:
        """Convert session key to file path (replace : with __)."""
        safe = key.replace(":", "__")
        return self._dir / f"{safe}.jsonl"

    def _load(self, path: Path, key: str) -> Session:
        """Load session from JSONL file. Returns empty session if file is corrupted."""
        try:
            lines = path.read_text().strip().split("\n")
            if not lines:
                return Session(key=key)

            meta = json.loads(lines[0])

            messages = []
            for line in lines[1:]:
                if not line.strip():
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping corrupted message line in session {key}")

            return Session(
                key=key,
                messages=messages,
                created_at=datetime.fromisoformat(
                    meta.get("created_at", datetime.now(UTC).isoformat())
                ),
                updated_at=datetime.fromisoformat(
                    meta.get("updated_at", datetime.now(UTC).isoformat())
                ),
                last_consolidated=meta.get("last_consolidated", 0),
                approved_approval_keys=set(meta.get("approved_approval_keys", [])),
                pending_approval=meta.get("pending_approval"),
                deferred_tool_calls=meta.get("deferred_tool_calls", []),
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            logger.warning(f"Session file corrupted, starting fresh: {path}")
            return Session(key=key)

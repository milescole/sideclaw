"""Session management for conversation history."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger

from sideclaw.session.session import Session
from sideclaw.utils.files import atomic_write_text


class SessionManager:
    """Manages conversation sessions with JSONL file storage."""

    def __init__(self, session_dir: Path) -> None:
        self._dir = session_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._quarantine_dir = self._dir / "quarantine"
        self._cache: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}

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
        """Persist session to JSONL file atomically."""
        session.updated_at = datetime.now(UTC)
        path = self._key_to_path(session.key)

        meta = {
            "_type": "metadata",
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "approved_approval_keys": sorted(session.approved_approval_keys),
            "pending_approval": session.pending_approval,
            "deferred_tool_calls": session.deferred_tool_calls,
            "title": session.title,
            "title_source": session.title_source,
        }
        lines = [json.dumps(meta)] + [json.dumps(msg) for msg in session.messages]
        atomic_write_text(path, "\n".join(lines) + "\n")

        logger.debug(f"Session saved: {session.key} ({len(session.messages)} messages)")

    def get_lock(self, key: str) -> asyncio.Lock:
        """Return the per-session async lock."""
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def delete(self, key: str) -> bool:
        """Delete a session from disk and cache. Returns True if deleted."""
        path = self._key_to_path(key)
        self._cache.pop(key, None)
        if path.exists():
            path.unlink()
            logger.info(f"Session deleted: {key}")
            return True
        return False

    def invalidate(self, key: str) -> None:
        """Remove session from cache."""
        self._cache.pop(key, None)

    def exists(self, key: str) -> bool:
        """Check whether a persisted session file exists for the given key."""
        return self._key_to_path(key).exists()

    def rename(self, key: str, title: str) -> bool:
        """Set a user-defined title. Returns False if the session doesn't exist."""
        if not self.exists(key):
            return False
        session = self.get_or_create(key)
        session.title = title
        session.title_source = "user"
        self.save(session)
        return True

    def get_session_info(self, key: str) -> dict | None:
        """Return metadata dict for a single session, or None if not found."""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            text = path.read_text()
            lines = text.strip().split("\n")
            meta = json.loads(lines[0])
            meta["key"] = key
            meta["message_count"] = sum(1 for line in lines[1:] if line.strip())
            return meta
        except (json.JSONDecodeError, IndexError):
            return None

    def list_sessions(self) -> list[dict]:
        """List all saved sessions with title, message count, and metadata."""
        sessions = []
        for path in self._dir.glob("*.jsonl"):
            try:
                text = path.read_text()
                lines = text.strip().split("\n")
                meta = json.loads(lines[0])
                message_count = sum(1 for line in lines[1:] if line.strip())
                entry = {"key": path.stem.replace("__", ":"), **meta}
                entry["message_count"] = message_count
                sessions.append(entry)
            except (json.JSONDecodeError, IndexError):
                continue
        return sessions

    def _key_to_path(self, key: str) -> Path:
        """Convert session key to file path (replace : with __)."""
        safe = key.replace(":", "__")
        return self._dir / f"{safe}.jsonl"

    def _load(self, path: Path, key: str) -> Session:
        """Load session from JSONL file with quarantine + fallback on corruption."""
        try:
            session, corrupted = self._parse_session_file(path, key)
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError):
            logger.warning(f"Session file corrupted, starting fresh: {path}")
            self._quarantine(path, key, reason="unreadable session file")
            return Session(key=key)

        if corrupted:
            self._quarantine(path, key, reason="corrupted message lines")

        return session

    def _parse_session_file(self, path: Path, key: str) -> tuple[Session, bool]:
        """Parse a persisted session file and report whether any lines were corrupt."""
        lines = path.read_text().strip().split("\n")
        if not lines:
            return Session(key=key), False

        meta = json.loads(lines[0])
        corrupted = False
        messages = []

        for line in lines[1:]:
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                corrupted = True
                logger.warning(f"Skipping corrupted message line in session {key}")

        session = Session(
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
            title=meta.get("title"),
            title_source=meta.get("title_source", "auto"),
        )
        return session, corrupted

    def _quarantine(self, path: Path, key: str, *, reason: str) -> None:
        """Move a corrupted session file aside so future loads start cleanly."""
        if not path.exists():
            return

        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        quarantine_name = f"{path.stem}-{timestamp}-{uuid4().hex[:8]}.jsonl"
        quarantine_path = self._quarantine_dir / quarantine_name

        try:
            path.replace(quarantine_path)
            logger.warning(
                "Quarantined corrupted session file for {}: {} ({})",
                key,
                quarantine_path,
                reason,
            )
        except OSError as exc:
            logger.warning(
                "Failed to quarantine corrupted session file for {}: {} ({})",
                key,
                exc,
                reason,
            )

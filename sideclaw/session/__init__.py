"""Session management module.

Handles conversation state and JSONL-based persistence across turns.

Modules:
    - session: Session dataclass — messages, metadata, and consolidation pointer
    - manager: SessionManager — file-backed storage with in-memory cache

Example:
    >>> from sideclaw.session import Session, SessionManager
    >>> from pathlib import Path
    >>>
    >>> manager = SessionManager(Path("~/.sideclaw/workspace/sessions"))
    >>> session = manager.get_or_create("telegram:12345")
    >>> session.messages.append({"role": "user", "content": "Hello"})
    >>> manager.save(session)
"""

from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session

__all__ = ["Session", "SessionManager"]

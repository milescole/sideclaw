"""Filesystem helpers for atomic text persistence."""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text via a temp file in the target directory and atomically replace."""
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def atomic_append_text(path: Path, chunk: str, *, encoding: str = "utf-8") -> None:
    """Append text by rewriting the full file through the atomic write helper."""
    existing = path.read_text(encoding=encoding) if path.exists() else ""
    atomic_write_text(path, existing + chunk, encoding=encoding)

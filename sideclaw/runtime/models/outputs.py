"""Runtime output models."""

from dataclasses import dataclass
from enum import StrEnum


class RuntimeOutputKind(StrEnum):
    """Kinds of user-visible runtime outputs."""

    text = "text"
    attachment = "attachment"


@dataclass(frozen=True)
class RuntimeOutput:
    """A surfaced output artifact emitted by a runtime run."""

    kind: RuntimeOutputKind
    text: str | None = None
    path: str | None = None


def _text_output(cls, value: str) -> RuntimeOutput:
    """Build a plain-text output."""
    return cls(kind=RuntimeOutputKind.text, text=value)


RuntimeOutput.text = classmethod(_text_output)

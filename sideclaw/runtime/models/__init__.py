"""Runtime model package.

Owns the semantic run-level data shapes used by the runtime boundary instead of
transport-specific DTOs.

Modules:
    - approval: approval requests, decisions, and tool execution outcomes
    - context: RuntimeContext for resolved run metadata
    - events: RuntimeEvent and RuntimeEventKind for progress reporting
    - outputs: RuntimeOutput and RuntimeOutputKind for surfaced artifacts
    - requests: RunRequest and RunTrigger
    - results: RunResult and RunStatus

Example:
    >>> from sideclaw.runtime.models import RunRequest, RunResult
"""

from sideclaw.runtime.models.context import RuntimeContext
from sideclaw.runtime.models.events import RuntimeEvent, RuntimeEventKind
from sideclaw.runtime.models.outputs import RuntimeOutput, RuntimeOutputKind
from sideclaw.runtime.models.requests import RunRequest, RunTrigger
from sideclaw.runtime.models.results import RunResult, RunStatus

__all__ = [
    "RunRequest",
    "RunResult",
    "RunStatus",
    "RunTrigger",
    "RuntimeContext",
    "RuntimeEvent",
    "RuntimeEventKind",
    "RuntimeOutput",
    "RuntimeOutputKind",
]

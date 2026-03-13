"""Runtime module.

Owns SideClaw's run-level execution boundary, approval policy, and transient
runtime state used by CLI, gateway, and scheduled entrypoints.

Modules:
    - approval: runtime approval policy and pending approval helpers
    - clarify: interactive clarification callback management
    - context: tool-execution contextvars
    - models: typed runtime requests, results, events, outputs, and approvals
    - service: RuntimeService facade for `run(...)` and `resume_pending(...)`
    - state: RuntimeState and RunPhase for in-flight runs

Example:
    >>> from sideclaw.runtime import RuntimeService
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sideclaw.runtime.service import RuntimeService
    from sideclaw.runtime.state import RunPhase, RuntimeState

__all__ = [
    "RunPhase",
    "RuntimeService",
    "RuntimeState",
]


def __getattr__(name: str) -> object:
    """Load runtime exports lazily to avoid import cycles."""
    if name == "RuntimeService":
        from sideclaw.runtime.service import RuntimeService

        return RuntimeService
    if name in {"RunPhase", "RuntimeState"}:
        from sideclaw.runtime.state import RunPhase, RuntimeState

        return {"RunPhase": RunPhase, "RuntimeState": RuntimeState}[name]
    msg = f"module 'sideclaw.runtime' has no attribute {name!r}"
    raise AttributeError(msg)

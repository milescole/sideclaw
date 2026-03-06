"""Approval and execution data models."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ApprovalScope(StrEnum):
    once = "once"
    session = "session"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class ApprovalRequirement(StrEnum):
    never = "never"
    unless_session_approved = "unless_session_approved"
    always = "always"


@dataclass(frozen=True)
class ApprovalRequest:
    """A request for user approval before executing a tool action."""

    request_id: str
    tool_name: str
    action_type: str
    description: str
    subject: str
    approval_key: str
    requirement: ApprovalRequirement
    arguments: dict[str, Any] = field(default_factory=dict)
    display_arguments: dict[str, Any] | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ApprovalDecision:
    """The result of an approval check."""

    approved: bool
    status: ApprovalStatus
    scope: ApprovalScope | None = None
    request: ApprovalRequest | None = None
    message: str | None = None


class ToolExecutionOutcome(StrEnum):
    success = "success"
    denied = "denied"
    pending = "pending"


@dataclass(frozen=True)
class ToolExecutionResult:
    """The outcome of executing or gating a tool invocation."""

    outcome: ToolExecutionOutcome
    content: str
    approval_request: ApprovalRequest | None = None

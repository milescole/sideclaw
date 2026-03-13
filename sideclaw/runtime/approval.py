"""Central approval policy module."""

import sys
from dataclasses import asdict
from uuid import uuid4

from sideclaw.config.schema import ApprovalConfig, ApprovalMode
from sideclaw.runtime.models.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequirement,
    ApprovalScope,
    ApprovalStatus,
)

_config = ApprovalConfig()


def configure(config: ApprovalConfig) -> None:
    """Set the approval configuration."""
    global _config
    _config = config


def check_approval(
    *,
    session: object,
    tool_name: str,
    action_type: str,
    description: str,
    subject: str,
    approval_key: str,
    requirement: ApprovalRequirement,
    arguments: dict | None = None,
    display_arguments: dict | None = None,
    tool_call_id: str | None = None,
) -> ApprovalDecision:
    """Check whether an action is approved for the given session."""
    if not _config.enabled or requirement == ApprovalRequirement.never:
        return ApprovalDecision(approved=True, status=ApprovalStatus.approved)

    approved_keys = getattr(session, "approved_approval_keys", set())
    if requirement != ApprovalRequirement.always and approval_key in approved_keys:
        return ApprovalDecision(
            approved=True,
            status=ApprovalStatus.approved,
            scope=ApprovalScope.session,
        )

    request = ApprovalRequest(
        request_id=str(uuid4()),
        tool_name=tool_name,
        action_type=action_type,
        description=description,
        subject=subject,
        approval_key=approval_key,
        requirement=requirement,
        arguments=arguments or {},
        display_arguments=display_arguments,
        tool_call_id=tool_call_id,
    )

    if _config.mode == ApprovalMode.auto_deny:
        return ApprovalDecision(
            approved=False,
            status=ApprovalStatus.denied,
            request=request,
            message=f"Error: {description} not approved ({subject})",
        )

    if _config.mode == ApprovalMode.channel_prompt:
        return ApprovalDecision(
            approved=False,
            status=ApprovalStatus.pending,
            request=request,
            message=format_approval_prompt(request),
        )

    return _cli_prompt(session, request)


def get_pending(session: object) -> ApprovalRequest | None:
    """Return the current pending approval request for a session, if any."""
    raw = getattr(session, "pending_approval", None)
    if not raw:
        return None
    payload = dict(raw)
    payload["requirement"] = ApprovalRequirement(payload["requirement"])
    return ApprovalRequest(**payload)


def set_pending(session: object, request: ApprovalRequest) -> None:
    """Persist a pending approval request on the session."""
    session.pending_approval = asdict(request)


def clear_pending(session: object) -> None:
    """Clear pending approval state from the session."""
    session.pending_approval = None
    session.deferred_tool_calls.clear()


def approve_pending(session: object, scope: ApprovalScope | None) -> ApprovalDecision:
    """Apply an approval decision to the current pending request."""
    request = get_pending(session)
    if request is None:
        return ApprovalDecision(
            approved=False,
            status=ApprovalStatus.denied,
            message="No pending approval",
        )

    if scope is None:
        return ApprovalDecision(
            approved=False,
            status=ApprovalStatus.denied,
            request=request,
            message=f"Error: {request.description} not approved ({request.subject})",
        )

    if scope == ApprovalScope.session and request.requirement != ApprovalRequirement.always:
        session.approved_approval_keys.add(request.approval_key)

    return ApprovalDecision(
        approved=True,
        status=ApprovalStatus.approved,
        scope=scope,
        request=request,
    )


def format_approval_prompt(request: ApprovalRequest) -> str:
    """Render a user-facing approval prompt for non-CLI surfaces."""
    return (
        f"Approval required for {request.tool_name} ({request.description}):\n"
        f"{request.subject}\n"
        "Reply 'yes' to approve once, 'session' to approve for this session, or 'no' to deny."
    )


def _cli_prompt(session: object, request: ApprovalRequest) -> ApprovalDecision:
    """Prompt the CLI user for approval."""
    sys.stdout.write(
        f"\nApproval required for {request.tool_name} ({request.description}):\n"
        f"  {request.subject}\n"
    )
    try:
        choice = input("Approve? [y]es once / [s]ession / [N]o: ").strip().lower()
    except EOFError:
        return ApprovalDecision(
            approved=False,
            status=ApprovalStatus.denied,
            request=request,
            message=f"Error: {request.description} not approved ({request.subject})",
        )

    if choice in {"y", "yes"}:
        return ApprovalDecision(
            approved=True,
            status=ApprovalStatus.approved,
            scope=ApprovalScope.once,
            request=request,
        )
    if choice in {"s", "session"}:
        if request.requirement != ApprovalRequirement.always:
            session.approved_approval_keys.add(request.approval_key)
        return ApprovalDecision(
            approved=True,
            status=ApprovalStatus.approved,
            scope=ApprovalScope.session,
            request=request,
        )
    return ApprovalDecision(
        approved=False,
        status=ApprovalStatus.denied,
        request=request,
        message=f"Error: {request.description} not approved ({request.subject})",
    )

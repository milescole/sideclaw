from sideclaw.runtime.models.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequirement,
    ApprovalScope,
    ApprovalStatus,
    ToolExecutionOutcome,
    ToolExecutionResult,
)


def test_approval_request_is_frozen():
    req = ApprovalRequest(
        request_id="req-1",
        tool_name="exec",
        action_type="shell_command",
        description="filesystem mutation",
        subject="touch foo.txt",
        approval_key="shell:filesystem_mutation",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    assert req.tool_name == "exec"
    assert req.approval_key == "shell:filesystem_mutation"
    assert req.request_id == "req-1"


def test_approved_decision():
    decision = ApprovalDecision(
        approved=True,
        status=ApprovalStatus.approved,
        scope=ApprovalScope.once,
    )
    assert decision.approved is True
    assert decision.scope == ApprovalScope.once


def test_denied_decision():
    decision = ApprovalDecision(approved=False, status=ApprovalStatus.denied)
    assert decision.approved is False
    assert decision.scope is None


def test_pending_decision():
    decision = ApprovalDecision(approved=False, status=ApprovalStatus.pending)
    assert decision.status == ApprovalStatus.pending


def test_tool_execution_result():
    result = ToolExecutionResult(
        outcome=ToolExecutionOutcome.pending,
        content="Approval required",
    )
    assert result.outcome == ToolExecutionOutcome.pending

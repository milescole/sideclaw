from sideclaw.config.schema import ApprovalConfig, ApprovalMode
from sideclaw.runtime.approval import (
    approve_pending,
    check_approval,
    clear_pending,
    configure,
    format_approval_prompt,
    get_pending,
    set_pending,
)
from sideclaw.runtime.models import (
    ApprovalRequest,
    ApprovalRequirement,
    ApprovalScope,
    ApprovalStatus,
)
from sideclaw.session.session import Session


def setup_function() -> None:
    configure(ApprovalConfig())


def test_check_approval_disabled():
    configure(ApprovalConfig(enabled=False))
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="exec",
        action_type="shell_command",
        description="filesystem mutation",
        subject="touch foo.txt",
        approval_key="shell:filesystem_mutation",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    assert decision.approved is True
    assert decision.status == ApprovalStatus.approved


def test_check_approval_never_requirement():
    configure(ApprovalConfig())
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="read_file",
        action_type="read_file",
        description="file read",
        subject="notes.txt",
        approval_key="read_file",
        requirement=ApprovalRequirement.never,
    )
    assert decision.approved is True
    assert decision.status == ApprovalStatus.approved


def test_cli_approve_once(monkeypatch):
    configure(ApprovalConfig(mode=ApprovalMode.cli_prompt))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="exec",
        action_type="shell_command",
        description="filesystem mutation",
        subject="touch foo.txt",
        approval_key="shell:filesystem_mutation",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    assert decision.approved is True
    assert decision.scope == ApprovalScope.once


def test_cli_approve_session(monkeypatch):
    configure(ApprovalConfig(mode=ApprovalMode.cli_prompt))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "s")
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="exec",
        action_type="shell_command",
        description="filesystem mutation",
        subject="touch foo.txt",
        approval_key="shell:filesystem_mutation",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    assert decision.approved is True
    assert decision.scope == ApprovalScope.session
    assert "shell:filesystem_mutation" in session.approved_approval_keys


def test_always_requirement_not_cached_by_session(monkeypatch):
    configure(ApprovalConfig(mode=ApprovalMode.cli_prompt))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "s")
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="exec",
        action_type="shell_command",
        description="destructive git mutation",
        subject="git reset --hard HEAD~1",
        approval_key="shell:destructive",
        requirement=ApprovalRequirement.always,
    )
    assert decision.approved is True
    assert decision.scope == ApprovalScope.session
    assert "shell:destructive" not in session.approved_approval_keys


def test_channel_prompt_creates_request():
    configure(ApprovalConfig(mode=ApprovalMode.channel_prompt))
    session = Session(key="test:test")
    decision = check_approval(
        session=session,
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
        arguments={"path": "notes.txt", "content": "hello"},
        display_arguments={"path": "notes.txt"},
        tool_call_id="call-1",
    )
    assert decision.approved is False
    assert decision.status == ApprovalStatus.pending
    assert decision.request is not None
    assert "reply 'yes'" in decision.message.lower()


def test_set_and_get_pending():
    session = Session(key="test:test")
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
        arguments={"path": "notes.txt", "content": "hello"},
        display_arguments={"path": "notes.txt"},
        tool_call_id="call-1",
    )
    set_pending(session, request)
    pending = get_pending(session)
    assert pending is not None
    assert pending.request_id == "req-1"


def test_approve_pending_session_caches_key():
    session = Session(key="test:test")
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    set_pending(session, request)
    decision = approve_pending(session, ApprovalScope.session)
    assert decision.approved is True
    assert "fs:write_file" in session.approved_approval_keys


def test_approve_pending_none_denies():
    session = Session(key="test:test")
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    set_pending(session, request)
    decision = approve_pending(session, None)
    assert decision.approved is False
    assert decision.status == ApprovalStatus.denied


def test_clear_pending_resets_request_and_deferred_calls():
    session = Session(key="test:test")
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    set_pending(session, request)
    session.deferred_tool_calls = [{"id": "call-2", "name": "list_dir", "arguments": "{}"}]
    clear_pending(session)
    assert get_pending(session) is None
    assert session.deferred_tool_calls == []


def test_format_approval_prompt_includes_subject():
    request = ApprovalRequest(
        request_id="req-1",
        tool_name="write_file",
        action_type="file_write",
        description="file write",
        subject="notes.txt",
        approval_key="fs:write_file",
        requirement=ApprovalRequirement.unless_session_approved,
    )
    prompt = format_approval_prompt(request)
    assert "write_file" in prompt
    assert "notes.txt" in prompt

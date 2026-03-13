from dataclasses import dataclass

import pytest

from sideclaw.bus.messages import OutboundMessage
from sideclaw.runtime.models.approval import ApprovalScope
from sideclaw.runtime.models.requests import RunRequest
from sideclaw.runtime.models.results import RunStatus
from sideclaw.runtime.service import RuntimeService


@dataclass
class _StubSession:
    pending_approval: dict | None = None


class _StubSessionManager:
    def __init__(self, session: _StubSession) -> None:
        self._session = session

    def get_or_create(self, _session_key: str) -> _StubSession:
        return self._session


@pytest.mark.asyncio
async def test_runtime_service_run_wraps_agent_loop_response():
    session = _StubSession()

    class StubAgentLoop:
        async def process_message(self, msg):
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, text=msg.text.upper())

    service = RuntimeService(
        agent_loop=StubAgentLoop(),
        session_manager=_StubSessionManager(session),
    )
    request = RunRequest(
        input_text="hello",
        surface="cli",
        conversation_id="chat-1",
        user_id="user-1",
    )

    result = await service.run(request)

    assert result.status == RunStatus.completed
    assert result.output_text == "HELLO"
    assert result.surface == "cli"
    assert result.conversation_id == "chat-1"
    assert result.outputs[0].text == "HELLO"


@pytest.mark.asyncio
async def test_runtime_service_run_detects_pending_approval():
    session = _StubSession()

    class StubAgentLoop:
        async def process_message(self, msg):
            session.pending_approval = {"request_id": "req-1"}
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                text="Approval required",
            )

    service = RuntimeService(
        agent_loop=StubAgentLoop(),
        session_manager=_StubSessionManager(session),
    )
    request = RunRequest(
        input_text="hello",
        surface="cli",
        conversation_id="chat-1",
        user_id="user-1",
    )

    result = await service.run(request)

    assert result.status == RunStatus.pending_approval


@pytest.mark.asyncio
async def test_runtime_service_resume_pending_uses_approval_scope():
    session = _StubSession()

    class StubAgentLoop:
        def __init__(self) -> None:
            self.scopes = []

        async def resume_pending_approval(self, msg, scope):
            self.scopes.append(scope)
            return f"scope={scope}"

    agent_loop = StubAgentLoop()
    service = RuntimeService(agent_loop=agent_loop, session_manager=_StubSessionManager(session))
    request = RunRequest(
        input_text="yes",
        surface="telegram",
        conversation_id="chat-9",
        user_id="user-9",
    )

    result = await service.resume_pending(request, ApprovalScope.once)

    assert result.status == RunStatus.completed
    assert result.output_text == "scope=once"
    assert agent_loop.scopes == [ApprovalScope.once]

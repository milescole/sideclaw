"""Tests for usage tracking wiring in the provider tool loop."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sideclaw.config.schema import Config
from sideclaw.metrics.usage import UsageTracker
from sideclaw.providers.base import LLMResponse
from sideclaw.runtime.execution.tool_runner import run_provider_tool_loop
from sideclaw.session.session import Session


@pytest.fixture
def tracker(tmp_path: Path) -> UsageTracker:
    return UsageTracker(tmp_path / "usage.jsonl")


@pytest.fixture
def session() -> Session:
    return Session(key="cli:test")


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def provider() -> AsyncMock:
    mock = AsyncMock()
    mock.chat.return_value = LLMResponse(
        content="Hello!",
        tool_calls=[],
        finish_reason="stop",
        usage={"prompt_tokens": 100, "completion_tokens": 50},
    )
    return mock


@pytest.fixture
def registry() -> MagicMock:
    mock = MagicMock()
    mock.get_definitions.return_value = []
    return mock


async def test_usage_recorded_after_llm_call(
    session: Session,
    config: Config,
    provider: AsyncMock,
    registry: MagicMock,
    tracker: UsageTracker,
):
    messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
    await run_provider_tool_loop(
        session=session,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
        max_tool_iterations=5,
        usage_tracker=tracker,
    )
    totals = tracker.get_session_totals("cli:test")
    assert totals.prompt_tokens == 100
    assert totals.completion_tokens == 50
    assert totals.llm_calls == 1
    assert totals.total_duration_ms >= 0


async def test_no_usage_tracker_still_works(
    session: Session,
    config: Config,
    provider: AsyncMock,
    registry: MagicMock,
):
    messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
    result = await run_provider_tool_loop(
        session=session,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
        max_tool_iterations=5,
    )
    assert result == "Hello!"


async def test_empty_usage_dict_skips_recording(
    session: Session,
    config: Config,
    provider: AsyncMock,
    registry: MagicMock,
    tracker: UsageTracker,
):
    provider.chat.return_value = LLMResponse(
        content="Hi!",
        tool_calls=[],
        finish_reason="stop",
        usage={},
    )
    messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "hi"}]
    await run_provider_tool_loop(
        session=session,
        messages=messages,
        provider=provider,
        registry=registry,
        config=config,
        max_tool_iterations=5,
        usage_tracker=tracker,
    )
    totals = tracker.get_session_totals("cli:test")
    assert totals.llm_calls == 0

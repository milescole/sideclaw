"""Tests for /usage slash command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sideclaw.config.schema import Config
from sideclaw.metrics.usage import UsageTracker
from sideclaw.runtime.commands import CommandHandler
from sideclaw.session.session import Session


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def session() -> Session:
    return Session(key="cli:test")


@pytest.fixture
def tracker(tmp_path: Path) -> UsageTracker:
    return UsageTracker(tmp_path / "usage.jsonl")


@pytest.fixture
def handler(config: Config, tracker: UsageTracker) -> CommandHandler:
    return CommandHandler(
        session_manager=MagicMock(),
        config=config,
        provider=AsyncMock(),
        memory_store=MagicMock(),
        workspace_docs=MagicMock(),
        usage_tracker=tracker,
    )


class TestUsageCommand:
    def test_is_command(self):
        assert CommandHandler.is_command("/usage")

    async def test_usage_without_prompt_builder(
        self, handler: CommandHandler, session: Session
    ):
        result = await handler.handle("/usage", session)
        assert "Context usage data not available" in result

    async def test_usage_shows_session_totals(
        self, handler: CommandHandler, session: Session, tracker: UsageTracker
    ):
        tracker.record_from_response(
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            session_key="cli:test",
            model="gpt-4o",
        )
        result = await handler.handle("/usage", session)
        assert "Session totals" in result
        assert "LLM calls: 1" in result

    async def test_usage_in_help(self, handler: CommandHandler, session: Session):
        result = await handler.handle("/help", session)
        assert "/usage" in result

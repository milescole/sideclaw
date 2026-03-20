"""Tests for /insights slash command."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sideclaw.config.schema import Config
from sideclaw.metrics.execution_log import ExecutionLogEntry, ExecutionLogger
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
def exec_logger(tmp_path: Path) -> ExecutionLogger:
    return ExecutionLogger(tmp_path / "runs.jsonl")


@pytest.fixture
def handler(
    config: Config, tracker: UsageTracker, exec_logger: ExecutionLogger
) -> CommandHandler:
    return CommandHandler(
        session_manager=MagicMock(),
        config=config,
        provider=AsyncMock(),
        memory_store=MagicMock(),
        workspace_docs=MagicMock(),
        usage_tracker=tracker,
        execution_logger=exec_logger,
    )


class TestInsightsCommand:
    def test_is_command(self):
        assert CommandHandler.is_command("/insights")

    async def test_insights_no_data(self, handler: CommandHandler, session: Session):
        result = await handler.handle("/insights", session)
        assert "No usage data" in result

    async def test_insights_with_data(
        self, handler: CommandHandler, session: Session, tracker: UsageTracker
    ):
        tracker.record_from_response(
            usage={"prompt_tokens": 500, "completion_tokens": 200},
            session_key="cli:test",
            model="gpt-4o",
            duration_ms=150,
        )
        result = await handler.handle("/insights", session)
        assert "Usage Insights" in result
        assert "Total LLM calls: 1" in result
        assert "gpt-4o" in result

    async def test_insights_custom_days(
        self, handler: CommandHandler, session: Session, tracker: UsageTracker
    ):
        tracker.record_from_response(
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            session_key="cli:test",
            model="gpt-4o",
        )
        result = await handler.handle("/insights --days 30", session)
        assert "last 30 days" in result

    async def test_insights_with_execution_logger(
        self,
        handler: CommandHandler,
        session: Session,
        tracker: UsageTracker,
        exec_logger: ExecutionLogger,
    ):
        tracker.record_from_response(
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            session_key="cli:test",
            model="gpt-4o",
        )
        exec_logger.log_run(
            ExecutionLogEntry(
                run_id="r1",
                session_key="cli:test",
                started_at=datetime.now(UTC).isoformat(),
                completed_at=datetime.now(UTC).isoformat(),
                duration_ms=1000,
                status="completed",
                llm_calls=2,
                total_prompt_tokens=500,
                total_completion_tokens=200,
                model="gpt-4o",
                channel="cli",
            )
        )
        result = await handler.handle("/insights", session)
        assert "Completed runs: 1" in result

    async def test_insights_in_help(self, handler: CommandHandler, session: Session):
        result = await handler.handle("/help", session)
        assert "/insights" in result

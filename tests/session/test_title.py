from unittest.mock import AsyncMock

import pytest

from sideclaw.providers.base import LLMResponse
from sideclaw.session.session import Session
from sideclaw.session.title import (
    _clean_title,
    generate_title,
    maybe_auto_title,
)


@pytest.fixture
def provider():
    return AsyncMock()


def test_clean_title_strips_quotes():
    assert _clean_title('"My Great Chat"') == "My Great Chat"
    assert _clean_title("'Another Chat'") == "Another Chat"


def test_clean_title_strips_prefix():
    assert _clean_title("Title: Session About Python") == "Session About Python"
    assert _clean_title("title: lowercase prefix") == "lowercase prefix"


def test_clean_title_truncates_long_titles():
    long_title = "A " * 50  # 100 chars
    result = _clean_title(long_title)
    assert len(result) <= 80


async def test_generate_title_returns_cleaned_title(provider):
    provider.chat.return_value = LLMResponse(content='"Python Async Patterns"')

    title = await generate_title(provider, "test-model", "How do I use async?", "You can use...")

    assert title == "Python Async Patterns"
    provider.chat.assert_called_once()
    call_kwargs = provider.chat.call_args[1]
    assert call_kwargs["max_tokens"] == 30
    assert call_kwargs["temperature"] == 0.3


async def test_generate_title_returns_none_on_empty_response(provider):
    provider.chat.return_value = LLMResponse(content="")

    title = await generate_title(provider, "test-model", "hello", "hi")

    assert title is None


async def test_generate_title_returns_none_on_error(provider):
    provider.chat.side_effect = RuntimeError("API error")

    title = await generate_title(provider, "test-model", "hello", "hi")

    assert title is None


async def test_generate_title_skips_when_cost_guard_denies(provider):
    class DenyingCostGuard:
        def check_allowed(self, model: str = "") -> tuple[bool, str | None]:
            return False, "Budget exceeded."

    title = await generate_title(
        provider,
        "test-model",
        "hello",
        "hi",
        DenyingCostGuard(),
    )

    assert title is None
    provider.chat.assert_not_called()


async def test_maybe_auto_title_skips_trivial_messages(provider):
    session = Session(key="test:1")
    session.messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await maybe_auto_title(session, provider, "test-model", "hi", "hello")

    assert session.title is None
    provider.chat.assert_not_called()


async def test_maybe_auto_title_generates_on_first_exchange(provider):
    provider.chat.return_value = LLMResponse(content="Python Help Session")
    session = Session(key="test:1")
    session.messages = [
        {"role": "user", "content": "How do I use asyncio?"},
        {"role": "assistant", "content": "You can use async/await..."},
    ]

    await maybe_auto_title(
        session, provider, "test-model",
        "How do I use asyncio?", "You can use async/await...",
    )

    assert session.title == "Python Help Session"
    assert session.title_source == "auto"


async def test_maybe_auto_title_skips_if_user_title_set(provider):
    session = Session(key="test:1", title="My Custom Title", title_source="user")
    session.messages = [
        {"role": "user", "content": "How do I use asyncio?"},
        {"role": "assistant", "content": "You can use async/await..."},
    ]

    await maybe_auto_title(
        session, provider, "test-model",
        "How do I use asyncio?", "You can use async/await...",
    )

    assert session.title == "My Custom Title"
    provider.chat.assert_not_called()


async def test_maybe_auto_title_skips_after_max_exchanges(provider):
    session = Session(key="test:1")
    session.messages = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "msg2"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "msg3"},
        {"role": "assistant", "content": "reply3"},
    ]

    await maybe_auto_title(session, provider, "test-model", "msg3", "reply3")

    assert session.title is None
    provider.chat.assert_not_called()

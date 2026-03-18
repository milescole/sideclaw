"""Tests for the RetryProvider wrapper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from sideclaw.providers.base import LLMResponse
from sideclaw.providers.retry import (
    RetryProvider,
    _strip_image_blocks,
    is_image_unsupported,
    is_transient,
)


def _make_provider(
    *,
    side_effect=None,
    return_value=None,
    max_retries=3,
    base_delay=0.01,
    max_delay=0.05,
):
    inner = MagicMock()
    inner.get_default_model.return_value = "test-model"
    if side_effect is not None:
        inner.chat = AsyncMock(side_effect=side_effect)
    elif return_value is not None:
        inner.chat = AsyncMock(return_value=return_value)
    return RetryProvider(
        inner, max_retries=max_retries, base_delay=base_delay, max_delay=max_delay
    )


# --- is_transient ---


def test_transient_status_code_429():
    err = Exception("rate limited")
    err.status_code = 429
    assert is_transient(err) is True


def test_transient_status_code_500():
    err = Exception("internal server error")
    err.status_code = 500
    assert is_transient(err) is True


def test_transient_status_code_502():
    err = Exception("bad gateway")
    err.status_code = 502
    assert is_transient(err) is True


def test_transient_status_code_503():
    err = Exception("service unavailable")
    err.status_code = 503
    assert is_transient(err) is True


def test_transient_status_code_504():
    err = Exception("gateway timeout")
    err.status_code = 504
    assert is_transient(err) is True


def test_non_transient_status_code_401():
    err = Exception("unauthorized")
    err.status_code = 401
    assert is_transient(err) is False


def test_non_transient_status_code_400():
    err = Exception("bad request")
    err.status_code = 400
    assert is_transient(err) is False


def test_transient_string_marker_rate_limit():
    assert is_transient(Exception("Rate limit exceeded")) is True


def test_transient_string_marker_overloaded():
    assert is_transient(Exception("API overloaded")) is True


def test_transient_string_marker_timeout():
    assert is_transient(Exception("Request timeout")) is True


def test_transient_string_marker_timed_out():
    assert is_transient(Exception("Connection timed out")) is True


def test_transient_string_marker_connection():
    assert is_transient(Exception("Connection error")) is True


def test_transient_string_marker_server_error():
    assert is_transient(Exception("Internal server error")) is True


def test_transient_string_marker_temporarily_unavailable():
    assert is_transient(Exception("Service temporarily unavailable")) is True


def test_non_transient_no_markers():
    assert is_transient(Exception("Invalid API key")) is False


# --- is_image_unsupported ---


def test_image_unsupported_detection():
    assert is_image_unsupported(Exception("image_url is only supported by vision models")) is True
    assert is_image_unsupported(Exception("This model does not support image inputs")) is True
    assert is_image_unsupported(Exception("Images are not supported")) is True
    assert is_image_unsupported(Exception("Image input is not supported")) is True


def test_image_unsupported_negative():
    assert is_image_unsupported(Exception("Rate limit exceeded")) is False


# --- _strip_image_blocks ---


def test_strip_image_blocks_removes_image_url():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        }
    ]
    result = _strip_image_blocks(messages)
    assert len(result[0]["content"]) == 1
    assert result[0]["content"][0]["type"] == "text"


def test_strip_image_blocks_all_images_become_empty_string():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        }
    ]
    result = _strip_image_blocks(messages)
    assert result[0]["content"] == ""


def test_strip_image_blocks_string_content_unchanged():
    messages = [{"role": "user", "content": "hello"}]
    result = _strip_image_blocks(messages)
    assert result[0]["content"] == "hello"


def test_strip_image_blocks_does_not_mutate_original():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        }
    ]
    _strip_image_blocks(messages)
    assert len(messages[0]["content"]) == 2


# --- RetryProvider ---


async def test_retry_success_on_first_attempt():
    ok = LLMResponse(content="ok", finish_reason="stop")
    provider = _make_provider(return_value=ok)
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "ok"
    assert provider._inner.chat.call_count == 1


async def test_retry_transient_then_success():
    err = Exception("temporarily unavailable")
    ok = LLMResponse(content="recovered", finish_reason="stop")
    provider = _make_provider(side_effect=[err, ok])
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "recovered"
    assert provider._inner.chat.call_count == 2


async def test_retry_exhaust_returns_error_response():
    err = Exception("server error persistent")
    provider = _make_provider(side_effect=err, max_retries=2)
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.finish_reason == "error"
    assert "server error persistent" in result.content
    assert provider._inner.chat.call_count == 3  # initial + 2 retries


async def test_retry_non_transient_returns_error_immediately():
    err = Exception("Invalid API key")
    provider = _make_provider(side_effect=err, max_retries=3)
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.finish_reason == "error"
    assert "Invalid API key" in result.content
    assert provider._inner.chat.call_count == 1  # no retries for non-transient


async def test_retry_image_unsupported_strips_and_retries():
    img_err = Exception("image_url is only supported by vision models")
    ok = LLMResponse(content="text only response", finish_reason="stop")
    provider = _make_provider(side_effect=[img_err, ok])

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        }
    ]
    result = await provider.chat(messages=messages)
    assert result.content == "text only response"
    assert provider._inner.chat.call_count == 2

    # Second call should have stripped images
    second_call_messages = provider._inner.chat.call_args_list[1][0][0]
    for msg in second_call_messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                assert block.get("type") != "image_url"


async def test_retry_delegates_get_default_model():
    provider = _make_provider(return_value=LLMResponse(content="ok"))
    assert provider.get_default_model() == "test-model"


async def test_retry_backoff_timing():
    """Verify that retries introduce a delay (not zero-sleep)."""
    err = Exception("rate limit exceeded")
    ok = LLMResponse(content="ok", finish_reason="stop")
    provider = _make_provider(side_effect=[err, ok], base_delay=0.05, max_delay=0.2)

    start = asyncio.get_event_loop().time()
    await provider.chat(messages=[{"role": "user", "content": "hi"}])
    elapsed = asyncio.get_event_loop().time() - start

    # Should have waited at least base_delay * 0.75 (jitter lower bound)
    assert elapsed >= 0.03


async def test_retry_status_code_transient_retries():
    """Error with status_code=429 should be retried."""
    err = Exception("too many requests")
    err.status_code = 429
    ok = LLMResponse(content="recovered", finish_reason="stop")
    provider = _make_provider(side_effect=[err, ok])
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "recovered"
    assert provider._inner.chat.call_count == 2

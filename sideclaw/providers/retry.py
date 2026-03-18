"""Retry wrapper for LLM providers with exponential backoff."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from sideclaw.providers.base import LLMProvider, LLMResponse, StreamChunk

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

_TRANSIENT_MARKERS = (
    "rate limit",
    "overloaded",
    "timeout",
    "timed out",
    "connection",
    "server error",
    "temporarily unavailable",
)

_IMAGE_UNSUPPORTED_MARKERS = (
    "image_url is only supported",
    "does not support image",
    "images are not supported",
    "image input is not supported",
)


def is_transient(error: Exception) -> bool:
    """Check if an error is transient and worth retrying.

    Checks status_code attribute (works for openai/anthropic SDK errors),
    then falls back to string marker matching.
    """
    status = getattr(error, "status_code", None)
    if status is not None and status in TRANSIENT_STATUS_CODES:
        return True
    msg = str(error).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def is_image_unsupported(error: Exception) -> bool:
    """Detect image-unsupported errors for fallback retry."""
    msg = str(error).lower()
    return any(marker in msg for marker in _IMAGE_UNSUPPORTED_MARKERS)


def _strip_image_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of messages with image_url content blocks removed."""
    result = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            filtered = [
                block
                for block in content
                if not (isinstance(block, dict) and block.get("type") == "image_url")
            ]
            msg = {**msg, "content": filtered if filtered else ""}
        result.append(msg)
    return result


class RetryProvider(LLMProvider):
    """Decorator that wraps an inner provider with retry + exponential backoff.

    Retries on transient errors (429, 5xx, connection errors).
    On image-unsupported errors, strips image blocks and retries.
    Non-transient errors are converted to error responses immediately.
    """

    def __init__(
        self,
        inner: LLMProvider,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
    ) -> None:
        self._inner = inner
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call the inner provider with retry logic."""
        for attempt in range(self._max_retries + 1):
            try:
                return await self._inner.chat(
                    messages, tools, model, max_tokens, temperature,
                )
            except Exception as e:  # noqa: BLE001
                if attempt == self._max_retries:
                    logger.error(
                        f"LLM call failed after {self._max_retries + 1} attempts: {e}"
                    )
                    return LLMResponse(content=f"Error: {e}", finish_reason="error")
                if is_image_unsupported(e):
                    logger.warning(f"Image unsupported, stripping image blocks: {e}")
                    messages = _strip_image_blocks(messages)
                    continue
                if not is_transient(e):
                    logger.error(f"Non-transient LLM error: {e}")
                    return LLMResponse(content=f"Error: {e}", finish_reason="error")
                # Exponential backoff with ±25% jitter
                base = min(self._base_delay * 2**attempt, self._max_delay)
                jitter = base * 0.25
                delay = base + random.uniform(-jitter, jitter)
                delay = max(0.1, delay)
                logger.warning(
                    f"Transient error (attempt {attempt + 1}/{self._max_retries + 1}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
        # Unreachable, but satisfies type checker
        return LLMResponse(  # pragma: no cover
            content="Error: max retries exceeded", finish_reason="error"
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream from the inner provider with retry logic.

        On retry, the full stream is restarted from the beginning.
        """
        for attempt in range(self._max_retries + 1):
            try:
                async for chunk in self._inner.chat_stream(
                    messages, tools, model, max_tokens, temperature,
                ):
                    yield chunk
                return
            except Exception as e:  # noqa: BLE001
                if attempt == self._max_retries:
                    logger.error(
                        f"LLM stream failed after {self._max_retries + 1} attempts: {e}"
                    )
                    yield StreamChunk(
                        content=f"Error: {e}", finish_reason="error"
                    )
                    return
                if is_image_unsupported(e):
                    logger.warning(f"Image unsupported, stripping image blocks: {e}")
                    messages = _strip_image_blocks(messages)
                    continue
                if not is_transient(e):
                    logger.error(f"Non-transient LLM stream error: {e}")
                    yield StreamChunk(
                        content=f"Error: {e}", finish_reason="error"
                    )
                    return
                base = min(self._base_delay * 2**attempt, self._max_delay)
                jitter = base * 0.25
                delay = base + random.uniform(-jitter, jitter)
                delay = max(0.1, delay)
                logger.warning(
                    f"Transient stream error (attempt {attempt + 1}/{self._max_retries + 1}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)

    def get_default_model(self) -> str:
        """Delegate to inner provider."""
        return self._inner.get_default_model()

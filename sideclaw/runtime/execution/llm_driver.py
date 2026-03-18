"""Provider invocation helpers for runtime execution."""

from collections.abc import AsyncIterator
from typing import Any

from sideclaw.config.schema import Config
from sideclaw.providers.base import LLMProvider, LLMResponse, StreamChunk


async def invoke_llm(
    *,
    provider: LLMProvider,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    config: Config,
) -> LLMResponse:
    """Invoke the configured provider for a single chat turn."""
    return await provider.chat(
        messages=messages,
        tools=tools,
        model=config.agent.model,
        max_tokens=config.agent.max_tokens,
        temperature=config.agent.temperature,
    )


async def invoke_llm_stream(
    *,
    provider: LLMProvider,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    config: Config,
) -> AsyncIterator[StreamChunk]:
    """Invoke the configured provider in streaming mode."""
    async for chunk in provider.chat_stream(
        messages=messages,
        tools=tools,
        model=config.agent.model,
        max_tokens=config.agent.max_tokens,
        temperature=config.agent.temperature,
    ):
        yield chunk

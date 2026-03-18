"""Ollama LLM provider using the OpenAI-compatible endpoint."""

from collections.abc import AsyncIterator
from typing import Any

import openai

from sideclaw.providers.base import LLMProvider, LLMResponse, StreamChunk, ToolCallRequest


class OllamaProvider(LLMProvider):
    """Ollama provider via its OpenAI-compatible API at localhost:11434/v1.

    No API key required — uses a dummy key for the OpenAI client.
    """

    def __init__(
        self,
        default_model: str = "llama3.2",
        api_base: str = "http://localhost:11434/v1",
    ) -> None:
        self._default_model = default_model
        self._api_base = api_base
        self._client = openai.AsyncOpenAI(api_key="ollama", base_url=api_base)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call Ollama via its OpenAI-compatible endpoint."""
        model = model or self._default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks from Ollama's OpenAI-compatible endpoint."""
        model = model or self._default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await self._client.chat.completions.create(**kwargs)
        tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if delta.content:
                yield StreamChunk(content=delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": tc_delta.function.name or "" if tc_delta.function else "",
                            "arguments": "",
                        }
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_calls[idx]["arguments"] += tc_delta.function.arguments

            if finish_reason:
                final_tool_calls = None
                if tool_calls:
                    final_tool_calls = [
                        ToolCallRequest(
                            id=tc["id"], name=tc["name"], arguments=tc["arguments"]
                        )
                        for tc in tool_calls.values()
                    ]
                usage_data = None
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_data = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                    }
                yield StreamChunk(
                    finish_reason=finish_reason,
                    tool_calls=final_tool_calls,
                    usage=usage_data,
                )

    def get_default_model(self) -> str:
        return self._default_model

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove non-standard keys from messages."""
        allowed_keys = {"role", "content", "name", "tool_calls", "tool_call_id"}
        return [{k: v for k, v in msg.items() if k in allowed_keys} for msg in messages]

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse an OpenAI-compatible response into an LLMResponse."""
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        )

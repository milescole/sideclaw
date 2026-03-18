"""OpenRouter LLM provider using LiteLLM."""

from collections.abc import AsyncIterator
from typing import Any

from litellm import acompletion

from sideclaw.providers.base import LLMProvider, LLMResponse, StreamChunk, ToolCallRequest


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider using LiteLLM for multi-model access."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "minimax/minimax-m2.5",
        api_base: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._api_base = api_base

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call the LLM via OpenRouter."""
        model = model or self._default_model
        resolved = f"openrouter/{model}" if not model.startswith("openrouter/") else model

        kwargs: dict[str, Any] = {
            "model": resolved,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "api_key": self._api_key,
            "api_base": self._api_base,
        }
        if tools:
            kwargs["tools"] = tools

        response = await acompletion(**kwargs)
        return self._parse_response(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks via OpenRouter/LiteLLM."""
        model = model or self._default_model
        resolved = f"openrouter/{model}" if not model.startswith("openrouter/") else model

        kwargs: dict[str, Any] = {
            "model": resolved,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "api_key": self._api_key,
            "api_base": self._api_base,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await acompletion(**kwargs)
        tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if hasattr(delta, "content") and delta.content:
                yield StreamChunk(content=delta.content)

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index if hasattr(tc_delta, "index") else 0
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": getattr(tc_delta, "id", "") or "",
                            "name": getattr(tc_delta.function, "name", "") or ""
                            if hasattr(tc_delta, "function")
                            else "",
                            "arguments": "",
                        }
                    if hasattr(tc_delta, "function") and tc_delta.function:
                        args = getattr(tc_delta.function, "arguments", "")
                        if args:
                            tool_calls[idx]["arguments"] += args

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
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
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
        """Parse LiteLLM response into LLMResponse."""
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

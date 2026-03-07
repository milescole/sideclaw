"""OpenRouter LLM provider using LiteLLM."""

from typing import Any

from litellm import acompletion
from loguru import logger

from sideclaw.providers.base import LLMProvider, LLMResponse, ToolCallRequest


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

        try:
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:  # noqa: BLE001
            # Provider boundary: convert any upstream SDK/network failure into an error response.
            logger.error(f"LLM call failed: {e}")
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

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

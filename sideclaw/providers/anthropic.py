"""Anthropic LLM provider using the official SDK."""

import json
from typing import Any, ClassVar

import anthropic
from loguru import logger

from sideclaw.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class AnthropicProvider(LLMProvider):
    """Direct Anthropic provider via the official SDK.

    Supports system prompt extraction, Anthropic-native tool format,
    and stop_reason mapping to the internal finish_reason vocabulary.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-opus-4-20250918",
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Call the Anthropic Messages API."""
        model = model or self._default_model
        system, converted_messages = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            response = await self._client.messages.create(**kwargs)
            return self._parse_response(response)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Anthropic call failed: {e}")
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

    def get_default_model(self) -> str:
        return self._default_model

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Extract system messages and convert the rest to Anthropic format.

        Anthropic requires system content as a separate parameter and does not
        accept ``role: "system"`` inside the messages list.  Tool-call and
        tool-result messages are converted to Anthropic's block format.
        """
        system_parts: list[str] = []
        result: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")

            if role == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list):
                    system_parts.extend(
                        p["text"]
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                continue

            if role == "assistant" and msg.get("tool_calls"):
                # Convert OpenAI-style tool_calls to Anthropic tool_use blocks.
                content_blocks: list[dict[str, Any]] = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", tc)
                    arguments = fn.get("arguments", "{}")
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(arguments) if isinstance(arguments, str) else arguments,
                    })
                result.append({"role": "assistant", "content": content_blocks})
                continue

            if role == "tool":
                # Convert OpenAI-style tool result to Anthropic tool_result block.
                result.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg.get("content", ""),
                        }
                    ],
                })
                continue

            # Standard user/assistant messages pass through.
            result.append({"role": role, "content": msg.get("content", "")})

        system_text = "\n".join(system_parts) if system_parts else None
        return system_text, result

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI function-call tool definitions to Anthropic format."""
        converted: list[dict[str, Any]] = []
        for tool in tools:
            fn = tool.get("function", {})
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    _STOP_REASON_MAP: ClassVar[dict[str, str]] = {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "stop_sequence": "stop",
    }

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse an Anthropic Messages API response into an LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None
        finish_reason = self._STOP_REASON_MAP.get(response.stop_reason, "stop")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        )

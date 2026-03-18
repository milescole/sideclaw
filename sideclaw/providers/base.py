"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A single chunk from a streaming LLM response."""

    content: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send messages to the LLM and get a response."""
        ...

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks from the LLM.

        Default implementation falls back to non-streaming chat().
        """
        response = await self.chat(messages, tools, model, max_tokens, temperature)
        yield StreamChunk(
            content=response.content,
            tool_calls=response.tool_calls or None,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model name."""
        ...

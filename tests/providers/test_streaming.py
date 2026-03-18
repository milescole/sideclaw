"""Tests for streaming provider support."""

from unittest.mock import AsyncMock, MagicMock

from sideclaw.providers.base import LLMResponse, StreamChunk, ToolCallRequest


async def test_stream_chunk_defaults():
    chunk = StreamChunk()
    assert chunk.content is None
    assert chunk.tool_calls is None
    assert chunk.finish_reason is None
    assert chunk.usage is None


async def test_stream_chunk_with_content():
    chunk = StreamChunk(content="Hello")
    assert chunk.content == "Hello"


async def test_stream_chunk_with_tool_calls():
    tc = ToolCallRequest(id="call_1", name="read_file", arguments='{"path": "x"}')
    chunk = StreamChunk(tool_calls=[tc], finish_reason="tool_calls")
    assert len(chunk.tool_calls) == 1
    assert chunk.finish_reason == "tool_calls"


async def test_base_provider_chat_stream_fallback():
    """The default chat_stream falls back to non-streaming chat."""
    from sideclaw.providers.base import LLMProvider

    class StubProvider(LLMProvider):
        async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
            return LLMResponse(
                content="hello",
                finish_reason="stop",
                usage={"prompt_tokens": 5, "completion_tokens": 3},
            )

        def get_default_model(self):
            return "stub"

    provider = StubProvider()
    chunks = []
    async for chunk in provider.chat_stream(messages=[{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].content == "hello"
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].usage == {"prompt_tokens": 5, "completion_tokens": 3}


async def test_retry_provider_chat_stream_delegates():
    """RetryProvider.chat_stream delegates to inner provider."""
    from sideclaw.providers.retry import RetryProvider

    inner = MagicMock()
    inner.get_default_model.return_value = "test-model"

    async def mock_stream(*args, **kwargs):
        yield StreamChunk(content="Hello ")
        yield StreamChunk(content="world")
        yield StreamChunk(finish_reason="stop", usage={"prompt_tokens": 5, "completion_tokens": 2})

    inner.chat_stream = mock_stream

    provider = RetryProvider(inner, max_retries=1, base_delay=0.01, max_delay=0.05)
    chunks = []
    async for chunk in provider.chat_stream(
        messages=[{"role": "user", "content": "hi"}]
    ):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert chunks[0].content == "Hello "
    assert chunks[1].content == "world"
    assert chunks[2].finish_reason == "stop"


async def test_retry_provider_chat_stream_retries_on_transient():
    """RetryProvider.chat_stream retries on transient errors."""
    from sideclaw.providers.retry import RetryProvider

    inner = MagicMock()
    inner.get_default_model.return_value = "test-model"

    call_count = 0

    async def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("server error")
        yield StreamChunk(content="recovered")
        yield StreamChunk(finish_reason="stop")

    inner.chat_stream = mock_stream

    provider = RetryProvider(inner, max_retries=2, base_delay=0.01, max_delay=0.05)
    chunks = []
    async for chunk in provider.chat_stream(
        messages=[{"role": "user", "content": "hi"}]
    ):
        chunks.append(chunk)

    assert call_count == 2
    assert any(c.content == "recovered" for c in chunks)

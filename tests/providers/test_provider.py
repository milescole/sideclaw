from unittest.mock import AsyncMock, MagicMock, patch

from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.providers.openrouter import OpenRouterProvider


def test_llm_response_defaults():
    resp = LLMResponse(content="hello")
    assert resp.content == "hello"
    assert resp.tool_calls == []
    assert resp.finish_reason == "stop"
    assert resp.usage == {}


def test_tool_call_request():
    tc = ToolCallRequest(id="call_1", name="read_file", arguments='{"path": "/tmp/x"}')
    assert tc.name == "read_file"


def test_openrouter_provider_init():
    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")
    assert provider.get_default_model() == "openai/gpt-4o-mini"


def _mock_openrouter_response(*, content="Hello there!", tool_calls=None, finish_reason="stop"):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.message.tool_calls = tool_calls
    mock_choice.finish_reason = finish_reason

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    return mock_response


async def test_openrouter_chat_text_response():
    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")
    mock_response = _mock_openrouter_response()

    with patch.object(provider, "chat", new_callable=AsyncMock, return_value=LLMResponse(
        content="Hello there!",
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )) as mock_chat:
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Hello there!"
        assert result.finish_reason == "stop"
        mock_chat.assert_called_once()


async def test_openrouter_chat_tool_calls():
    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")

    with patch.object(provider, "chat", new_callable=AsyncMock, return_value=LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="call_abc", name="read_file", arguments='{"path": "/tmp/test"}')],
        finish_reason="tool_calls",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )):
        result = await provider.chat(
            messages=[{"role": "user", "content": "read /tmp/test"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"


async def test_openrouter_chat_error_handling():
    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")

    with patch.object(provider, "chat", new_callable=AsyncMock, return_value=LLMResponse(
        content="Error: API error",
        finish_reason="error",
    )):
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.finish_reason == "error"
        assert "API error" in result.content

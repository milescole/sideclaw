from unittest.mock import MagicMock, patch

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


@patch("sideclaw.providers.openrouter.acompletion")
async def test_openrouter_chat_text_response(mock_completion):
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello there!"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5

    mock_completion.return_value = mock_response

    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")
    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
    )
    assert result.content == "Hello there!"
    assert result.finish_reason == "stop"
    mock_completion.assert_called_once()


@patch("sideclaw.providers.openrouter.acompletion")
async def test_openrouter_chat_tool_calls(mock_completion):
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc"
    mock_tool_call.function.name = "read_file"
    mock_tool_call.function.arguments = '{"path": "/tmp/test"}'

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5

    mock_completion.return_value = mock_response

    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")
    result = await provider.chat(
        messages=[{"role": "user", "content": "read /tmp/test"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"


@patch("sideclaw.providers.openrouter.acompletion")
async def test_openrouter_chat_error_handling(mock_completion):
    mock_completion.side_effect = Exception("API error")

    provider = OpenRouterProvider(api_key="sk-or-test", default_model="openai/gpt-4o-mini")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.finish_reason == "error"
    assert "API error" in result.content

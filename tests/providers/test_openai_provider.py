from unittest.mock import AsyncMock, MagicMock, patch

from sideclaw.providers.openai_provider import OpenAIProvider


@patch("sideclaw.providers.openai_provider.openai")
def test_openai_provider_init(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    provider = OpenAIProvider(api_key="sk-test")
    assert provider.get_default_model() == "gpt-5.4"


@patch("sideclaw.providers.openai_provider.openai")
def test_openai_provider_custom_model(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    provider = OpenAIProvider(api_key="sk-test", default_model="gpt-4o")
    assert provider.get_default_model() == "gpt-4o"


@patch("sideclaw.providers.openai_provider.openai")
def test_openai_provider_custom_api_base(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    OpenAIProvider(api_key="sk-test", api_base="https://custom.api/v1")
    mock_sdk.AsyncOpenAI.assert_called_once_with(
        api_key="sk-test", base_url="https://custom.api/v1"
    )


@patch("sideclaw.providers.openai_provider.openai")
async def test_openai_text_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = "Hello from GPT!"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 12
    mock_response.usage.completion_tokens = 6

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OpenAIProvider(api_key="sk-test")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "Hello from GPT!"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 12, "completion_tokens": 6}
    assert result.tool_calls == []


@patch("sideclaw.providers.openai_provider.openai")
async def test_openai_tool_call_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc"
    mock_tool_call.function.name = "read_file"
    mock_tool_call.function.arguments = '{"path": "test.txt"}'

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 15
    mock_response.usage.completion_tokens = 8

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OpenAIProvider(api_key="sk-test")
    result = await provider.chat(
        messages=[{"role": "user", "content": "read test.txt"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_abc"
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == '{"path": "test.txt"}'


@patch("sideclaw.providers.openai_provider.openai")
async def test_openai_error_handling(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Rate limited"))

    provider = OpenAIProvider(api_key="sk-test")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.finish_reason == "error"
    assert "Rate limited" in result.content


@patch("sideclaw.providers.openai_provider.openai")
def test_openai_sanitize_messages(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    provider = OpenAIProvider(api_key="sk-test")

    messages = [
        {"role": "user", "content": "hi", "extra_field": "should be removed"},
        {"role": "assistant", "content": "hello", "tool_calls": []},
    ]
    sanitized = provider._sanitize_messages(messages)

    assert "extra_field" not in sanitized[0]
    assert sanitized[0] == {"role": "user", "content": "hi"}
    assert "tool_calls" in sanitized[1]

from unittest.mock import AsyncMock, MagicMock, patch

from sideclaw.providers.ollama import OllamaProvider


@patch("sideclaw.providers.ollama.openai")
def test_ollama_provider_init(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    provider = OllamaProvider()
    assert provider.get_default_model() == "llama3.2"


@patch("sideclaw.providers.ollama.openai")
def test_ollama_provider_custom_model(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    provider = OllamaProvider(default_model="mistral")
    assert provider.get_default_model() == "mistral"


@patch("sideclaw.providers.ollama.openai")
def test_ollama_default_api_base(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    OllamaProvider()
    mock_sdk.AsyncOpenAI.assert_called_once_with(
        api_key="ollama", base_url="http://localhost:11434/v1"
    )


@patch("sideclaw.providers.ollama.openai")
def test_ollama_custom_api_base(mock_sdk):
    mock_sdk.AsyncOpenAI.return_value = MagicMock()
    OllamaProvider(api_base="http://remote:11434/v1")
    mock_sdk.AsyncOpenAI.assert_called_once_with(
        api_key="ollama", base_url="http://remote:11434/v1"
    )


@patch("sideclaw.providers.ollama.openai")
async def test_ollama_text_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = "Hello from Llama!"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 8
    mock_response.usage.completion_tokens = 4

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OllamaProvider()
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "Hello from Llama!"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 8, "completion_tokens": 4}
    assert result.tool_calls == []


@patch("sideclaw.providers.ollama.openai")
async def test_ollama_tool_call_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_xyz"
    mock_tool_call.function.name = "read_file"
    mock_tool_call.function.arguments = '{"path": "test.txt"}'

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tool_call]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    provider = OllamaProvider()
    result = await provider.chat(
        messages=[{"role": "user", "content": "read test.txt"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"


@patch("sideclaw.providers.ollama.openai")
async def test_ollama_error_handling(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncOpenAI.return_value = mock_client
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("Connection refused")
    )

    provider = OllamaProvider()
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.finish_reason == "error"
    assert "Connection refused" in result.content

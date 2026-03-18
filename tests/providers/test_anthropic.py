import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sideclaw.providers.anthropic import AnthropicProvider


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_provider_init(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")
    assert provider.get_default_model() == "claude-opus-4-6"


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_provider_custom_model(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test", default_model="claude-haiku-4-5-20251001")
    assert provider.get_default_model() == "claude-haiku-4-5-20251001"


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_text_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Hello from Claude!"

    mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
    mock_usage.input_tokens = 15
    mock_usage.output_tokens = 8

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = mock_usage

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "Hello from Claude!"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 15, "completion_tokens": 8}
    assert result.tool_calls == []


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_tool_call_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "toolu_abc123"
    tool_block.name = "read_file"
    tool_block.input = {"path": "/tmp/test.txt"}

    mock_response = MagicMock()
    mock_response.content = [tool_block]
    mock_response.stop_reason = "tool_use"
    mock_response.usage.input_tokens = 20
    mock_response.usage.output_tokens = 10

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(
        messages=[{"role": "user", "content": "read /tmp/test.txt"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ],
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "toolu_abc123"
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == '{"path": "/tmp/test.txt"}'


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_mixed_text_and_tool_response(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Let me read that file."

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "toolu_xyz"
    tool_block.name = "read_file"
    tool_block.input = {"path": "/tmp/f"}

    mock_response = MagicMock()
    mock_response.content = [text_block, tool_block]
    mock_response.stop_reason = "tool_use"
    mock_response.usage.input_tokens = 25
    mock_response.usage.output_tokens = 12

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(messages=[{"role": "user", "content": "read it"}])

    assert result.content == "Let me read that file."
    assert len(result.tool_calls) == 1
    assert result.finish_reason == "tool_calls"


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_system_message_extraction_with_caching(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    system, converted = provider._convert_messages(messages)

    # With caching enabled (default), system is list-of-blocks with cache_control
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["text"] == "You are helpful."
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert len(converted) == 1
    assert converted[0]["role"] == "user"


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_system_message_extraction_no_caching(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test", prompt_caching=False)

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    system, converted = provider._convert_messages(messages)

    assert system == "You are helpful."
    assert len(converted) == 1
    assert converted[0]["role"] == "user"


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_multiple_system_messages_with_caching(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    messages = [
        {"role": "system", "content": "Rule one."},
        {"role": "system", "content": "Rule two."},
        {"role": "user", "content": "Hello"},
    ]
    system, converted = provider._convert_messages(messages)

    assert isinstance(system, list)
    assert len(system) == 2
    assert system[0]["text"] == "Rule one."
    assert "cache_control" not in system[0]
    assert system[1]["text"] == "Rule two."
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert len(converted) == 1


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_no_system_message(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    messages = [{"role": "user", "content": "Hello"}]
    system, converted = provider._convert_messages(messages)

    assert system is None
    assert len(converted) == 1


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_tool_call_message_conversion(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    messages = [
        {
            "role": "assistant",
            "content": "I'll read that.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "file contents here"},
    ]
    _system, converted = provider._convert_messages(messages)

    # Assistant message → content blocks with text + tool_use
    assert converted[0]["role"] == "assistant"
    blocks = converted[0]["content"]
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["input"] == {"path": "/tmp/x"}

    # Tool result → user message with tool_result block
    assert converted[1]["role"] == "user"
    assert converted[1]["content"][0]["type"] == "tool_result"
    assert converted[1]["content"][0]["tool_use_id"] == "call_1"


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_tool_format_conversion_with_caching(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    result = provider._convert_tools(openai_tools)

    assert len(result) == 1
    assert result[0]["name"] == "read_file"
    assert result[0]["description"] == "Read a file"
    assert result[0]["input_schema"]["type"] == "object"
    assert "path" in result[0]["input_schema"]["properties"]
    assert result[0]["cache_control"] == {"type": "ephemeral"}


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_tool_format_conversion_no_caching(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test", prompt_caching=False)

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }
    ]
    result = provider._convert_tools(openai_tools)

    assert len(result) == 1
    assert "cache_control" not in result[0]


@patch("sideclaw.providers.anthropic.anthropic")
def test_anthropic_multiple_tools_cache_on_last(mock_sdk):
    mock_sdk.AsyncAnthropic.return_value = MagicMock()
    provider = AnthropicProvider(api_key="sk-ant-test")

    openai_tools = [
        {"type": "function", "function": {"name": "tool_a", "description": "A", "parameters": {}}},
        {"type": "function", "function": {"name": "tool_b", "description": "B", "parameters": {}}},
    ]
    result = provider._convert_tools(openai_tools)

    assert len(result) == 2
    assert "cache_control" not in result[0]
    assert result[1]["cache_control"] == {"type": "ephemeral"}


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_error_propagates(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client
    mock_client.messages.create = AsyncMock(side_effect=Exception("API rate limit"))

    provider = AnthropicProvider(api_key="sk-ant-test")
    with pytest.raises(Exception, match="API rate limit"):
        await provider.chat(messages=[{"role": "user", "content": "hi"}])


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_max_tokens_stop_reason(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Truncated resp"

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.stop_reason = "max_tokens"
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 100

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(messages=[{"role": "user", "content": "long response please"}])

    assert result.finish_reason == "length"


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_cache_usage_fields(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Cached response"

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 20
    mock_response.usage.cache_creation_input_tokens = 500
    mock_response.usage.cache_read_input_tokens = 80

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.usage["prompt_tokens"] == 100
    assert result.usage["completion_tokens"] == 20
    assert result.usage["cache_creation_tokens"] == 500
    assert result.usage["cache_read_tokens"] == 80


@patch("sideclaw.providers.anthropic.anthropic")
async def test_anthropic_no_cache_usage_when_absent(mock_sdk):
    mock_client = AsyncMock()
    mock_sdk.AsyncAnthropic.return_value = mock_client

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Response"

    mock_response = MagicMock(spec=["content", "stop_reason", "usage"])
    mock_response.content = [text_block]
    mock_response.stop_reason = "end_turn"
    mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_client.messages.create = AsyncMock(return_value=mock_response)

    provider = AnthropicProvider(api_key="sk-ant-test")
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert "cache_creation_tokens" not in result.usage
    assert "cache_read_tokens" not in result.usage

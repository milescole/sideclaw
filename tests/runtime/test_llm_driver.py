from unittest.mock import AsyncMock

from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig
from sideclaw.providers.base import LLMResponse, ToolCallRequest
from sideclaw.runtime.execution.llm_driver import invoke_llm


def _build_config() -> Config:
    return Config(
        agent=AgentConfig(
            model="openai/gpt-4.1-mini",
            workspace="~/.sideclaw/workspace",
            max_tokens=2048,
            temperature=0.2,
        ),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )


async def test_llm_driver_calls_provider_with_configured_runtime_settings():
    config = _build_config()
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="Hello!")
    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "echo", "parameters": {}}}]

    response = await invoke_llm(
        provider=provider,
        messages=messages,
        tools=tools,
        config=config,
    )

    provider.chat.assert_awaited_once_with(
        messages=messages,
        tools=tools,
        model="openai/gpt-4.1-mini",
        max_tokens=2048,
        temperature=0.2,
    )
    assert response.content == "Hello!"


async def test_llm_driver_preserves_error_finish_reason_content():
    config = _build_config()
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="provider unavailable",
        finish_reason="error",
        tool_calls=[ToolCallRequest(id="call_1", name="echo", arguments='{"text":"x"}')],
    )

    response = await invoke_llm(
        provider=provider,
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        config=config,
    )

    assert response.finish_reason == "error"
    assert response.content == "provider unavailable"
    assert response.tool_calls[0].name == "echo"

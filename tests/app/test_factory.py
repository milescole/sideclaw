import sys
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import pytest

from sideclaw.config.schema import (
    AgentConfig,
    AnthropicConfig,
    Config,
    OpenAIConfig,
    OpenRouterConfig,
    ProvidersConfig,
)


def test_build_runtime_wires_common_dependencies(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config = Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )

    factory = import_module("sideclaw.app.factory")
    runtime = factory.build_runtime(config)

    assert runtime.workspace == workspace
    assert workspace.exists()
    assert (workspace / "sessions").exists()
    assert runtime.agent_loop._workspace == workspace
    assert runtime.agent_loop._bus is runtime.bus
    assert runtime.agent_loop._provider is runtime.provider
    assert runtime.agent_loop._session_manager is runtime.session_manager
    assert runtime.runtime_service._agent_loop is runtime.agent_loop
    assert runtime.runtime_service._session_manager is runtime.session_manager


def test_importing_factory_does_not_eagerly_import_runtime_dependencies() -> None:
    sys.modules.pop("sideclaw.app.factory", None)
    sys.modules.pop("sideclaw.runtime.loop", None)
    sys.modules.pop("sideclaw.providers.openrouter", None)

    import_module("sideclaw.app.factory")

    assert "sideclaw.runtime.loop" not in sys.modules
    assert "sideclaw.providers.openrouter" not in sys.modules


def test_detect_provider_claude_model() -> None:
    from sideclaw.app.factory import _detect_provider

    assert _detect_provider("claude-opus-4-6") == "anthropic"
    assert _detect_provider("claude-haiku-4-5-20251001") == "anthropic"


def test_detect_provider_openai_models() -> None:
    from sideclaw.app.factory import _detect_provider

    assert _detect_provider("gpt-4o-mini") == "openai"
    assert _detect_provider("gpt-4o") == "openai"
    assert _detect_provider("o1-preview") == "openai"
    assert _detect_provider("o3-mini") == "openai"
    assert _detect_provider("o4-mini") == "openai"


def test_detect_provider_defaults_to_openrouter() -> None:
    from sideclaw.app.factory import _detect_provider

    assert _detect_provider("openai/gpt-4o-mini") == "openrouter"
    assert _detect_provider("some-unknown-model") == "openrouter"


@patch("sideclaw.providers.anthropic.anthropic")
def test_build_provider_auto_anthropic(mock_sdk, tmp_path: Path) -> None:
    mock_sdk.AsyncAnthropic.return_value = object()
    from sideclaw.app.factory import _build_provider
    from sideclaw.providers.anthropic import AnthropicProvider

    config = Config(
        agent=AgentConfig(model="claude-opus-4-6", workspace=str(tmp_path)),
        providers=ProvidersConfig(anthropic=AnthropicConfig(api_key="sk-ant-test")),
    )
    provider = _build_provider(config)
    assert isinstance(provider, AnthropicProvider)
    assert provider.get_default_model() == "claude-opus-4-6"


@patch("sideclaw.providers.anthropic.anthropic")
def test_build_provider_explicit_anthropic(mock_sdk, tmp_path: Path) -> None:
    mock_sdk.AsyncAnthropic.return_value = object()
    from sideclaw.app.factory import _build_provider
    from sideclaw.providers.anthropic import AnthropicProvider

    config = Config(
        agent=AgentConfig(
            model="claude-opus-4-6", provider="anthropic", workspace=str(tmp_path)
        ),
        providers=ProvidersConfig(anthropic=AnthropicConfig(api_key="sk-ant-test")),
    )
    provider = _build_provider(config)
    assert isinstance(provider, AnthropicProvider)


def test_build_provider_anthropic_missing_config(tmp_path: Path) -> None:
    from sideclaw.app.factory import _build_provider

    config = Config(
        agent=AgentConfig(model="claude-opus-4-6", workspace=str(tmp_path)),
        providers=ProvidersConfig(),
    )
    with pytest.raises(ValueError, match="Anthropic provider requires"):
        _build_provider(config)


@patch("sideclaw.providers.openai_provider.openai")
def test_build_provider_auto_openai(mock_sdk, tmp_path: Path) -> None:
    mock_sdk.AsyncOpenAI.return_value = object()
    from sideclaw.app.factory import _build_provider
    from sideclaw.providers.openai_provider import OpenAIProvider

    config = Config(
        agent=AgentConfig(model="gpt-4o-mini", workspace=str(tmp_path)),
        providers=ProvidersConfig(openai=OpenAIConfig(api_key="sk-test")),
    )
    provider = _build_provider(config)
    assert isinstance(provider, OpenAIProvider)
    assert provider.get_default_model() == "gpt-4o-mini"


@patch("sideclaw.providers.openai_provider.openai")
def test_build_provider_explicit_openai(mock_sdk, tmp_path: Path) -> None:
    mock_sdk.AsyncOpenAI.return_value = object()
    from sideclaw.app.factory import _build_provider
    from sideclaw.providers.openai_provider import OpenAIProvider

    config = Config(
        agent=AgentConfig(model="gpt-4o", provider="openai", workspace=str(tmp_path)),
        providers=ProvidersConfig(openai=OpenAIConfig(api_key="sk-test")),
    )
    provider = _build_provider(config)
    assert isinstance(provider, OpenAIProvider)


def test_build_provider_openai_missing_config(tmp_path: Path) -> None:
    from sideclaw.app.factory import _build_provider

    config = Config(
        agent=AgentConfig(model="gpt-4o-mini", workspace=str(tmp_path)),
        providers=ProvidersConfig(),
    )
    with pytest.raises(ValueError, match="OpenAI provider requires"):
        _build_provider(config)


def test_build_provider_openrouter_explicit(tmp_path: Path) -> None:
    from sideclaw.app.factory import _build_provider
    from sideclaw.providers.openrouter import OpenRouterProvider

    config = Config(
        agent=AgentConfig(model="openai/gpt-4o-mini", workspace=str(tmp_path)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-or-test")),
    )
    provider = _build_provider(config)
    assert isinstance(provider, OpenRouterProvider)

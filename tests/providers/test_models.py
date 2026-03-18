from sideclaw.providers.models import ModelInfo, ModelRegistry


def test_registry_lookup_known_model():
    registry = ModelRegistry()
    info = registry.get("claude-opus-4-6")
    assert info is not None
    assert info.provider == "anthropic"
    assert info.context_window == 1_000_000
    assert info.max_output_tokens == 128_000


def test_registry_lookup_openai_model():
    registry = ModelRegistry()
    info = registry.get("gpt-4o")
    assert info is not None
    assert info.provider == "openai"
    assert info.context_window == 128_000


def test_registry_lookup_unknown_returns_none():
    registry = ModelRegistry()
    assert registry.get("some-unknown-model") is None


def test_detect_provider_exact_match():
    registry = ModelRegistry()
    assert registry.detect_provider("gpt-4o") == "openai"
    assert registry.detect_provider("claude-opus-4-6") == "anthropic"


def test_detect_provider_prefix_claude():
    registry = ModelRegistry()
    assert registry.detect_provider("claude-future-model") == "anthropic"


def test_detect_provider_prefix_openai():
    registry = ModelRegistry()
    assert registry.detect_provider("gpt-6-turbo") == "openai"
    assert registry.detect_provider("o1-preview") == "openai"
    assert registry.detect_provider("o3-mini") == "openai"
    assert registry.detect_provider("o4-mega") == "openai"


def test_detect_provider_prefix_ollama():
    registry = ModelRegistry()
    assert registry.detect_provider("ollama/llama3.2") == "ollama"
    assert registry.detect_provider("ollama/mistral") == "ollama"


def test_detect_provider_fallback_openrouter():
    registry = ModelRegistry()
    assert registry.detect_provider("openai/gpt-4o-mini") == "openrouter"
    assert registry.detect_provider("some-unknown-model") == "openrouter"


def test_custom_registration():
    registry = ModelRegistry()
    custom = ModelInfo(
        id="custom-model",
        provider="openai",
        context_window=32_000,
        max_output_tokens=4_096,
    )
    registry.register(custom)
    assert registry.get("custom-model") is custom
    assert registry.detect_provider("custom-model") == "openai"


def test_custom_registration_overrides_default():
    registry = ModelRegistry()
    original = registry.get("gpt-4o")
    assert original is not None

    override = ModelInfo(
        id="gpt-4o",
        provider="openai",
        context_window=256_000,
        max_output_tokens=32_000,
    )
    registry.register(override)
    assert registry.get("gpt-4o").context_window == 256_000


def test_list_models_all():
    registry = ModelRegistry()
    models = registry.list_models()
    assert len(models) > 0


def test_list_models_filtered_by_provider():
    registry = ModelRegistry()
    anthropic_models = registry.list_models(provider="anthropic")
    assert all(m.provider == "anthropic" for m in anthropic_models)
    assert len(anthropic_models) >= 3

    openai_models = registry.list_models(provider="openai")
    assert all(m.provider == "openai" for m in openai_models)
    assert len(openai_models) >= 4


def test_model_info_defaults():
    info = ModelInfo(id="test", provider="openai", context_window=100, max_output_tokens=50)
    assert info.supports_tools is True
    assert info.supports_vision is False
    assert info.supports_streaming is True

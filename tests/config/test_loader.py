import json

from sideclaw.config.loader import get_config_path, load_config, save_config


def test_get_config_path():
    path = get_config_path()
    assert path.name == "config.json"
    assert ".sideclaw" in str(path)


def test_load_config_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    cfg = load_config(path)
    assert cfg.agent.model == "openai/gpt-4o-mini"


def test_save_and_load_config(tmp_path):
    path = tmp_path / "config.json"
    from sideclaw.config.schema import Config, OpenRouterConfig, ProvidersConfig

    cfg = Config(providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")))
    save_config(cfg, path)

    loaded = load_config(path)
    assert loaded.providers.openrouter.api_key == "sk-test"


def test_load_config_from_json(tmp_path):
    path = tmp_path / "config.json"
    data = {
        "agent": {"model": "anthropic/claude-3.5-sonnet", "temperature": 0.5},
        "providers": {"openrouter": {"api_key": "sk-or-test"}},
        "tools": {
            "fal_api_key": "fal_test_key",
            "fal_model": "fal-ai/flux-pro/v1.1",
            "fal_client_timeout": 90.0,
            "fal_enable_upscaling": True,
            "fal_upscaler_model": "fal-ai/custom-upscaler",
            "fal_upscale_factor": 3,
        },
    }
    path.write_text(json.dumps(data))
    cfg = load_config(path)
    assert cfg.agent.model == "anthropic/claude-3.5-sonnet"
    assert cfg.agent.temperature == 0.5
    assert cfg.providers.openrouter.api_key == "sk-or-test"
    assert cfg.tools.fal_model == "fal-ai/flux-pro/v1.1"
    assert cfg.tools.fal_client_timeout == 90.0
    assert cfg.tools.fal_enable_upscaling is True
    assert cfg.tools.fal_upscaler_model == "fal-ai/custom-upscaler"
    assert cfg.tools.fal_upscale_factor == 3

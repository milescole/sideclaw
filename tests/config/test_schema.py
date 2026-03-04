from sideclaw.config.schema import (
    AgentConfig,
    ChannelsConfig,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    TelegramConfig,
    ToolsConfig,
)


def test_minimal_config():
    cfg = Config(
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )
    assert cfg.providers.openrouter.api_key == "sk-test"
    assert cfg.agent.model == "openai/gpt-4o-mini"
    assert cfg.agent.max_tokens == 4096
    assert cfg.agent.temperature == 0.7


def test_agent_config_defaults():
    agent = AgentConfig()
    assert agent.memory_window == 50
    assert agent.workspace == "~/.sideclaw/workspace"


def test_telegram_config():
    tg = TelegramConfig(token="bot123:ABC")
    assert tg.token == "bot123:ABC"
    assert tg.allow_from == []


def test_channels_config_defaults():
    ch = ChannelsConfig()
    assert ch.telegram is None
    assert ch.send_progress is True
    assert ch.send_tool_hints is True


def test_tools_config_defaults():
    tools = ToolsConfig()
    assert tools.exec_timeout == 60
    assert tools.web_search_api_key is None


def test_config_workspace_path():
    cfg = Config(
        agent=AgentConfig(workspace="~/custom/workspace"),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )
    assert "custom/workspace" in str(cfg.workspace_path)

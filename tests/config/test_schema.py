from sideclaw.config.schema import (
    AgentConfig,
    ApprovalConfig,
    ApprovalMode,
    ChannelsConfig,
    Config,
    MemoryConfig,
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
    assert tools.exec_enabled is False
    assert tools.exec_timeout == 60
    assert tools.web_search_api_key is None


def test_memory_config_defaults():
    memory = MemoryConfig()
    assert memory.max_context_chars == 14_000
    assert memory.per_file_max_chars == 2_500
    assert memory.max_context_files == 8
    assert memory.keep_recent_messages == 12
    assert memory.always_include == [
        "AGENTS.md",
        "SOUL.md",
        "docs/core-beliefs.md",
    ]
    assert memory.enable_injection_scan is True


def test_approval_config_defaults():
    cfg = ApprovalConfig()
    assert cfg.enabled is True
    assert cfg.mode == ApprovalMode.cli_prompt
    assert cfg.timeout_seconds == 60
    assert cfg.dangerous_patterns == []


def test_config_has_approval_section():
    cfg = Config()
    assert cfg.approval.enabled is True
    assert cfg.memory.max_context_chars == 14_000



def test_approval_mode_auto_deny():
    cfg = ApprovalConfig(mode=ApprovalMode.auto_deny)
    assert cfg.mode == ApprovalMode.auto_deny


def test_config_workspace_path():
    cfg = Config(
        agent=AgentConfig(workspace="~/custom/workspace"),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )
    assert "custom/workspace" in str(cfg.workspace_path)

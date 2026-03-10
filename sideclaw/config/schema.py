"""Configuration schema."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class OpenRouterConfig(BaseModel):
    """OpenRouter provider configuration."""

    api_key: str
    api_base: str = "https://openrouter.ai/api/v1"


class ProvidersConfig(BaseModel):
    """LLM provider configurations."""

    openrouter: OpenRouterConfig | None = None


class AgentConfig(BaseModel):
    """Agent behavior defaults."""

    model: str = "openai/gpt-4o-mini"
    workspace: str = "~/.sideclaw/workspace"
    max_tokens: int = 4096
    temperature: float = 0.7
    memory_window: int = 50


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""

    token: str
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """Channel configurations."""

    telegram: TelegramConfig | None = None
    send_progress: bool = True
    send_tool_hints: bool = True


class WebSearchProvider(StrEnum):
    """Supported web search providers."""

    brave = "brave"


class ToolsConfig(BaseModel):
    """Tool configurations."""

    exec_enabled: bool = False
    exec_timeout: int = 60
    web_search_provider: WebSearchProvider | None = None
    web_search_api_key: str | None = None


class CronConfig(BaseModel):
    """Background scheduler configuration."""

    enabled: bool = True
    poll_interval_seconds: int = Field(default=30, ge=1)


class MemoryConfig(BaseModel):
    """Context and memory budgeting configuration."""

    max_context_chars: int = 14_000
    per_file_max_chars: int = 2_500
    max_context_files: int = 8
    keep_recent_messages: int = 12
    always_include: list[str] = Field(
        default_factory=lambda: [
            "AGENTS.md",
            "SOUL.md",
            "docs/core-beliefs.md",
        ]
    )
    enable_injection_scan: bool = True


class ApprovalMode(StrEnum):
    auto_deny = "auto_deny"
    cli_prompt = "cli_prompt"
    channel_prompt = "channel_prompt"


class ApprovalConfig(BaseModel):
    """Approval gate configuration."""

    enabled: bool = True
    mode: ApprovalMode = ApprovalMode.cli_prompt
    timeout_seconds: int = 60
    dangerous_patterns: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """Root configuration."""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)

    @property
    def workspace_path(self) -> Path:
        return Path(self.agent.workspace).expanduser()

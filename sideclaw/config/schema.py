"""Configuration schema."""

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


class ToolsConfig(BaseModel):
    """Tool configurations."""

    exec_enabled: bool = False
    exec_timeout: int = 60
    web_search_api_key: str | None = None


class Config(BaseModel):
    """Root configuration."""

    agent: AgentConfig = Field(default_factory=AgentConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        return Path(self.agent.workspace).expanduser()

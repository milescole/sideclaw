# sideclaw

SideClaw is a lightweight AI assistant framework for building tool-using chat agents with persistent sessions and optional channel integrations.

It provides:

- A core agent loop with tool calling
- CLI and Telegram channel entry points
- Session persistence and long-term memory
- Config-driven provider/channel/tool setup

## Why SideClaw

The name **SideClaw** comes from the idea of a reliable sidekick: always at your side, ready to help with the next task. It blends that companion feeling with a practical "tooling claw" identity for getting real work done.

SideClaw is designed for fast iteration on practical assistants:

- Small, readable codebase
- Clear component boundaries
- Real tool execution (files, shell, web, memory)
- Easy local development with `uv`, `pytest`, and `typer`

## Architecture At A Glance

```mermaid
flowchart LR
    U[User] --> C[CLI or Telegram Channel]
    C --> B[MessageBus.inbound]
    B --> A[AgentLoop]
    A --> P[LLM Provider<br/>OpenRouter via LiteLLM]
    A --> T[ToolRegistry<br/>filesystem, shell, web, memory]
    A --> S[SessionManager<br/>JSONL sessions]
    A --> M[MemoryStore<br/>MEMORY.md + HISTORY.md]
    A --> BO[MessageBus.outbound]
    BO --> C
    C --> U
```

See [TECHNICAL.md](./TECHNICAL.md) for detailed internals and data flow.

## Project Layout

```text
sideclaw/
  sideclaw/
    agent/         # core orchestration loop + context building
    bus/           # async inbound/outbound message queues
    channels/      # platform adapters (Telegram)
    cli/           # Typer CLI commands
    config/        # pydantic schema + JSON loader/saver
    memory/        # long-term memory store
    providers/     # LLM abstraction + OpenRouter implementation
    session/       # JSONL-backed session persistence
    tools/         # tool base class + built-in tools
    templates/     # bootstrap identity/soul prompt files
  tests/           # unit + integration tests
```

## Requirements

- Python `>=3.13`
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management
- OpenRouter API key for live model calls
- Optional: Telegram bot token for gateway mode

## Quick Start

1. Install dependencies:

```bash
uv sync --dev
```

2. Run interactive onboarding:

```bash
uv run sideclaw onboard
```

3. Check status:

```bash
uv run sideclaw status
```

4. Run the local CLI assistant:

```bash
uv run sideclaw agent
```

5. Single non-interactive message:

```bash
uv run sideclaw agent --message "Summarize this repo"
```

## Gateway Mode (Telegram)

After onboarding with Telegram config values:

```bash
uv run sideclaw gateway
```

The gateway runs continuously, receives inbound channel messages, and routes outbound responses through the matching channel adapter.

## Configuration

Default config path:

```text
~/.sideclaw/config.json
```

Core configuration sections:

- `agent`: model, workspace, token/temperature defaults, memory window
- `providers.openrouter`: API key and base URL
- `channels.telegram`: bot token + allowlist
- `tools`: shell timeout + web search API key

Workspace defaults to:

```text
~/.sideclaw/workspace
```

Onboarding creates:

- `sessions/` for per-chat JSONL transcripts
- `memory/MEMORY.md` for consolidated long-term context
- `memory/HISTORY.md` for timestamped memory events
- `IDENTITY.md` and `SOUL.md` from built-in templates

## Built-in Tools

- `read_file`: read a workspace file
- `write_file`: write a file in workspace
- `edit_file`: single text replacement in a file
- `list_dir`: list directory entries
- `exec`: run shell commands with timeout
- `web_search`: Brave Search API integration
- `web_fetch`: fetch raw URL text
- `save_memory`: update long-term memory store

## Development

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Run format:

```bash
uv run ruff format .
```

## External References

- [Typer](https://typer.tiangolo.com/)
- [Pydantic](https://docs.pydantic.dev/)
- [LiteLLM](https://docs.litellm.ai/)
- [OpenRouter](https://openrouter.ai/docs/api-reference/overview)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)

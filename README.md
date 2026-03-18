# sideclaw

SideClaw is a lightweight AI assistant framework for building tool-using chat agents with persistent sessions and optional channel integrations.

It provides:

- A core agent loop with tool calling
- CLI and Telegram channel entry points
- Session persistence and long-term memory
- Persisted cron scheduling for recurring chat tasks
- Config-driven provider/channel/tool setup

## Why SideClaw

The name **SideClaw** comes from the idea of a reliable sidekick: always at your side, ready to help with the next task. It blends that companion feeling with a practical "tooling claw" identity for getting real work done.

SideClaw is designed for fast iteration on practical assistants:

- Small, readable codebase
- Clear component boundaries
- Real tool execution (files, shell, web, memory)
- Easy local development with `uv`, `pytest`, and `typer`
- A dedicated CLI render layer so command logic stays separate from presentation
- An `app/` composition layer so CLI and gateway share runtime wiring without duplicating startup code
- A `runtime/` boundary so surfaces call a stable run API instead of talking to transport-shaped loop methods directly

## Architecture At A Glance

```mermaid
flowchart LR
    U[User] --> C[CLI or Telegram Channel]
    C --> APP[app/cli.py or app/gateway.py]
    APP --> R[RuntimeService<br/>RunRequest -> RunResult]
    R --> A[RuntimeLoop]
    A --> P[LLM Provider<br/>Anthropic, OpenAI, Ollama, OpenRouter via LiteLLM]
    A --> T[ToolRegistry<br/>filesystem, shell, web, memory]
    A --> S[SessionManager<br/>JSONL sessions]
    A --> M[MemoryStore<br/>MEMORY.md + HISTORY.md]
    R --> C
    C --> U
```

See [TECHNICAL.md](./TECHNICAL.md) for detailed internals and data flow.
See [AGENTS.md](./AGENTS.md) for contributor-facing guidance tailored to coding agents working on this repo.

## Project Layout

```text
sideclaw/
  sideclaw/
    app/           # shared runtime factory + per-surface composition hooks
    agent/         # prompt building + skills
    bus/           # async inbound/outbound message queues
    channels/      # platform adapters (Telegram)
    cli/           # Typer entrypoint, command surfaces, and shared CLI render helpers
    config/        # pydantic schema + JSON loader/saver
    memory/        # long-term memory store
    providers/     # LLM abstraction + Anthropic, OpenAI, Ollama, and OpenRouter implementations
    runtime/       # runtime loop, run models, runtime service, approval policy, and transient run state
    session/       # JSONL-backed session persistence
    skills/        # built-in prompt skills
    cron/          # persisted scheduler service
    tools/         # tool base class, registry, construction, and built-in tools
    templates/     # scaffolded workspace prompt files
  tests/           # unit + integration tests
```

## Requirements

- Python `>=3.13`
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management
- Anthropic API key **or** OpenRouter API key for live model calls
- Optional: [Ollama](https://ollama.ai/) for free local model inference
- Optional: Telegram bot token for gateway mode
- Optional: `playwright` browser install for browser automation (`uv run playwright install`)

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

Scheduled jobs are executed by the same gateway process, so recurring Telegram delivery works while
`sideclaw gateway` is running.

Both CLI and gateway now enter assistant execution through the same runtime boundary:

- surfaces build a `RunRequest`
- `RuntimeService` adapts that request into the `RuntimeLoop`
- the runtime returns a `RunResult`
- surfaces translate the result into terminal or channel output

Example:

```text
Send me a new meal plan every Friday night at 9pm.
```

The agent can map that to a cron job for the current chat.

You can also manage jobs explicitly:

```bash
uv run sideclaw cron add \
  --schedule "0 21 * * 5" \
  --prompt "Send me a new meal plan" \
  --channel telegram \
  --chat-id 123456789 \
  --name "weekly meal plan"

uv run sideclaw cron list
uv run sideclaw cron disable <job-id>
uv run sideclaw cron enable <job-id>
uv run sideclaw cron remove <job-id>
```

## Configuration

Default config path:

```text
~/.sideclaw/config.json
```

Core configuration sections:

- `agent`: model, workspace, token/temperature defaults, memory window, provider selection (`auto`/`anthropic`/`openai`/`ollama`/`openrouter`), retry settings (`retry_max`, `retry_base_delay`, `retry_max_delay`)
- `providers.anthropic`: API key, prompt caching toggle (for direct Anthropic access)
- `providers.openai`: API key and optional base URL (for direct OpenAI access)
- `providers.ollama`: optional base URL (for local Ollama inference, no API key needed)
- `providers.openrouter`: API key and base URL
- `channels.telegram`: bot token + allowlist
- `tools`: browser enablement, fal.ai image key/model/upscaler settings, shell exec, text-to-speech settings, web search provider/key, and other tool-specific flags
- `cron`: scheduler enable flag and polling interval

Workspace defaults to:

```text
~/.sideclaw/workspace
```

Onboarding creates:

- `sessions/` for per-chat JSONL transcripts
- `memory/MEMORY.md` for consolidated long-term context
- `memory/HISTORY.md` for timestamped memory events
- `IDENTITY.md` and `SOUL.md` from built-in templates
- `skills/cron/SKILL.md` for scheduled-task routing guidance

## Built-in Tools

- `read_file`: read a workspace file
- `write_file`: write a file in workspace
- `edit_file`: single text replacement in a file
- `list_dir`: list directory entries
- `exec`: optional shell access, disabled by default and intended only for trusted local deployments
- `browser`: optional Playwright-backed browser automation for navigation, snapshots, screenshots, clicks, typing, and tab control
- `image_generation`: optional fal.ai image generation with model-aware request shaping and optional upscaling, only registered when a fal API key is configured
- `send_message`: optional Telegram delivery tool for sending text or files to known chats
- `text_to_speech`: optional artifact-generating speech synthesis with configurable provider settings
- `web_search`: optional web search integration, only registered when provider + API key are configured
- `web_fetch`: fetch raw URL text
- `save_memory`: update long-term memory store
- `cron`: add/list/remove/enable/disable recurring jobs for the current chat

When enabled, `exec` runs inside the configured workspace, strips secret-like environment
variables, blocks obviously dangerous command patterns, and requires explicit CLI approval for
mutating commands. Gateway/channel usage is denied by default.

## Development

Runtime assembly now lives under `sideclaw/app/`:

- `factory.py`: shared object graph construction for the host process
- `cli.py`: CLI-specific composition, including approval-mode adaptation
- `gateway.py`: gateway-specific composition, including channel approval semantics

Run-level execution lives under `sideclaw/runtime/`:

- `loop.py`: the shared `RuntimeLoop` orchestration shell
- `execution/`: internal execution modules for prepare, LLM driver, tool runner, persistence, and output work
- `models/`: typed shapes such as `RunRequest`, `RuntimeContext`, `RuntimeEvent`, `RuntimeOutput`, and `RunResult`
- `service.py`: the stable facade surfaces call for `run(...)` and `resume_pending(...)`
- `state.py`: transient in-memory run state for the current execution

CLI presentation code lives under `sideclaw/cli/render/`:

- `console.py`: shared Rich console I/O helpers
- `formatting.py`: pure formatting/renderable helpers reused by CLI commands

That keeps `sideclaw/cli/commands/` focused on control flow and config loading while `sideclaw/app/` owns runtime wiring and `sideclaw/cli/render/` owns presentation.

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
- [Anthropic SDK](https://docs.anthropic.com/en/api/client-sdks)
- [OpenAI SDK](https://platform.openai.com/docs/libraries)
- [OpenRouter](https://openrouter.ai/docs/api-reference/overview)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)

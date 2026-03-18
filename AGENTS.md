# SideClaw Development Guide

**SideClaw** is a lightweight, message-driven AI assistant framework. The current runtime boundary accepts run-level requests from CLI, gateway, and scheduled entrypoints, then delegates to the runtime loop for prompt building, LLM calls, tool execution, and session/memory persistence.

## Build, Test, and Run

```bash
uv sync --dev                 # install runtime + dev dependencies
uv run ruff format .          # format
uv run ruff check .           # lint
uv run pytest                 # full test suite
uv run sideclaw onboard       # interactive setup
uv run sideclaw status        # inspect current config/workspace state
uv run sideclaw agent         # local interactive agent
uv run sideclaw gateway       # long-running channel + cron runtime
```

Use targeted tests while iterating, for example `uv run pytest tests/tools/test_shell.py` or
`uv run pytest tests/agent/test_prompt_builder.py`.

## Contributor Rules

- Prefer small, local changes that follow the current module boundaries over introducing new abstractions early.
- Run `uv run ruff check .` and the most relevant `uv run pytest ...` coverage after behavior changes. Run the full suite before wrapping substantial work.
- Treat prompt construction, workspace-doc routing, approval flows, and tool safety checks as core behavior. Regressions there change the whole system.
- Keep the hot-path prompt files concise. `AGENTS.md`, `SOUL.md`, and `docs/core-beliefs.md` are injected by default.
- Preserve the split between transient session history and durable workspace memory. Do not collapse them into one store.
- Keep channel-specific behavior out of the core agent loop when an adapter or runtime boundary already exists.
- Keep host-specific dependency wiring in `sideclaw/app/`; command surfaces should not quietly become composition roots again.
- Gate risky or mutating execution through the approval/runtime model instead of adding one-off prompts or bypasses.
- Prefer `pathlib.Path`, typed Pydantic models, and existing helper utilities over ad hoc string/path handling.
- Comments should explain non-obvious intent, not restate the code.

## Code Style

- Python version is `>=3.13`; follow the existing async-first style and current project patterns.
- Ruff enforces formatting and linting. Line length is `100`.
- Use `str | None`, `list[str]`, and other modern built-in type syntax already used in the repo.
- Keep public surfaces explicit and small. Most modules expose a few clear entry points rather than deep inheritance trees.
- Prefer constructor injection for runtime dependencies like `Config`, `SessionManager`, `MessageBus`, provider implementations, and workspace paths.
- Use dataclasses or Pydantic models where the codebase already uses them for structured runtime state.
- Avoid hidden global behavior except where the project already centralizes process-wide policy, such as `sideclaw/runtime/approval.py`.

## Architecture Principles

- SideClaw is message-driven, but surfaces should prefer the runtime boundary over direct loop calls. CLI, gateway, and scheduled entrypoints should create `RunRequest` values and receive `RunResult` values.
- Prompt assembly is a first-class subsystem, not a string concatenation detail. `sideclaw/agent/prompt_builder.py` and `sideclaw/workspace/context.py` decide what context enters the model.
- Workspace docs are part of runtime behavior. Canonical files and routed docs influence model behavior, memory, and safety.
- Tool registration is config-driven. Core tools are always present; browser, image, messaging, TTS, shell, web search, and cron are conditional.
- Session storage and long-term memory serve different purposes:
  - sessions preserve turn-by-turn transcripts per `channel:chat_id`
  - memory/workspace docs preserve curated durable context
- Approval is a runtime policy surface, not just UI. CLI and channel approval modes must remain behaviorally consistent across `RuntimeService`, gateway handling, and direct loop resume paths.
- Skills are prompt extensions selected by frontmatter and request matching. Changes to loading or ranking affect agent behavior broadly.

## Runtime Flow

```text
channel/CLI input
  -> runtime service
  -> runtime loop
  -> execution/prepare + prompt builder + workspace context + skill loading
  -> execution/llm_driver provider call
  -> optional execution/tool_runner loop
  -> execution/persistence save + optional memory consolidation
  -> execution/output result shaping
  -> run result
  -> channel adapter
```

The underlying orchestration now lives in `sideclaw/runtime/loop.py`, and surfaces should route through `sideclaw/runtime/service.py`. If a change affects multiple steps in this flow, verify the full interaction, not just the local function.

## Project Structure

```text
sideclaw/
├── app/           # shared runtime factory plus CLI/gateway composition hooks
├── agent/         # prompt building and skill loading
├── browser/       # Playwright-backed browser session management and snapshots
├── bus/           # async inbound/outbound queue abstractions
├── channels/      # channel adapters; Telegram is the current external gateway
├── cli/           # Typer entry points, command surfaces, and CLI rendering helpers
├── config/        # Pydantic config schema plus load/save helpers
├── cron/          # persisted scheduler service and due-job execution
├── memory/        # long-term memory store built on workspace markdown files
├── providers/     # LLM abstraction with retry wrapper, Anthropic, OpenAI, Ollama, and OpenRouter implementations
├── runtime/       # approval policy, clarify flow, run models, runtime service, and transient run state
├── session/       # JSONL-backed per-chat session persistence and locking
├── skills/        # built-in skill prompts copied into workspaces and loaded by relevance
├── tools/         # tool interfaces, registry, construction, and built-in tools
├── utils/         # shared file and redaction helpers
└── workspace/     # scaffold, canonical doc helpers, prompt-context routing

tests/
├── app/           # composition-layer coverage for shared runtime assembly
├── agent/         # loop and prompt-builder behavior
├── bus/           # queue semantics
├── channels/      # Telegram adapter behavior
├── cli/           # CLI command behavior and render-layer coverage
├── config/        # schema and loader coverage
├── cron/          # scheduler persistence and due-run logic
├── memory/        # durable memory behavior
├── providers/     # provider parsing and error handling
├── runtime/       # approval and runtime models
├── session/       # JSONL persistence and locking
├── skills/        # skill loading/ranking
├── tools/         # built-in tool coverage
└── test_integration.py  # end-to-end message flow coverage
```

## Key Modules

- `sideclaw/cli/main.py`: process entry point and Typer wiring for the CLI.
- `sideclaw/cli/commands/`: command implementation modules for onboarding, status, agent, cron, and gateway behavior.
- `sideclaw/cli/render/`: shared Rich console boundary plus pure formatting helpers for CLI presentation.
- `sideclaw/app/factory.py`: shared runtime construction and provider routing (`_build_provider` / `_detect_provider`) for the current host process; keep heavyweight runtime imports lazy here so unrelated CLI commands stay lightweight.
- `sideclaw/providers/models.py`: centralized `ModelRegistry` and `ModelInfo` — single source of truth for model metadata and provider detection. Add new models here rather than hardcoding prefix matching.
- `sideclaw/providers/retry.py`: `RetryProvider` decorator wrapping all providers with exponential backoff, transient error detection, and image-unsupported fallback. Supports both `chat()` and `chat_stream()`. Individual providers should let exceptions propagate.
- `sideclaw/providers/anthropic.py`: direct Anthropic provider via official SDK with system prompt extraction, tool format conversion, and prompt caching support.
- `sideclaw/providers/openai_provider.py`: direct OpenAI provider via official SDK with native message/tool format.
- `sideclaw/providers/ollama.py`: Ollama provider via OpenAI-compatible endpoint for local model inference.
- `sideclaw/app/cli.py` and `sideclaw/app/gateway.py`: surface-specific composition hooks for approval semantics and future host divergence.
- `sideclaw/runtime/service.py`: stable run boundary used by CLI and gateway surfaces; adapts `RunRequest`/`RunResult` to the runtime loop.
- `sideclaw/runtime/state.py`: in-memory run-scoped state, events, outputs, and lifecycle phase tracking.
- `sideclaw/runtime/loop.py`: the shared orchestration shell for session locking, pending approval resume, and execution-module coordination.
- `sideclaw/runtime/execution/`: internal execution helpers for prepare, LLM driver, tool runner, persistence, and output shaping.
- `sideclaw/runtime/models/`: typed run request/result/context/event/output shapes.
- `sideclaw/tools/registry.py`: tool contract, execution boundary, and default tool registration via `build_default_tool_registry()`.
- `sideclaw/agent/skills.py`: skill discovery, workspace override precedence, frontmatter parsing, and relevance ranking.
- `sideclaw/agent/prompt_builder.py`: system prompt assembly, runtime metadata injection, and context-budget trimming.
- `sideclaw/workspace/context.py` and `sideclaw/workspace/docs.py`: canonical workspace document routing, reading, search, and controlled writes.
- `sideclaw/session/manager.py`: per-session persistence and lock ownership. Concurrency changes should be reviewed carefully.
- `sideclaw/memory/store.py`: long-term summary and history handling.
- `sideclaw/runtime/approval.py`: centralized approval policy, pending approvals, CLI prompts, and session-scope approvals.
- `sideclaw/tools/base.py`: tool base class and shared helpers.

## Prompt and Workspace Model

This repo treats workspace documents as part of the runtime, not just user content.

- Default hot-path includes are configured in `sideclaw/config/schema.py` and used by `PromptBuilder`.
- The scaffolded workspace layout in `sideclaw/templates/workspace/` is the contract for canonical docs.
- `AGENTS.md` is for operating rules, not persona.
- `SOUL.md` is for persona and stable behavioral voice.
- `docs/core-beliefs.md` is part of the default prompt hot path.
- Routed docs under `docs/runbooks/`, `docs/decisions/`, `docs/exec-plans/active/`, and memory paths are pulled in based on relevance.
- Prompt budget matters. Large or noisy docs can crowd out useful context and change model behavior.

If you change canonical doc names, routing rules, or scaffold behavior, update tests in `tests/agent/`, `tests/skills/`, `tests/config/`, and `tests/test_integration.py`.

## Tools and Extension Points

### Adding a tool

1. Implement the tool in `sideclaw/tools/`.
2. Register it in `build_default_tool_registry()` in `sideclaw/tools/registry.py`.
3. Add or extend tests in `tests/tools/` and any agent-loop coverage needed for end-to-end behavior.

### Adding a channel

1. Implement the adapter in `sideclaw/channels/`.
2. Extend config models in `sideclaw/config/schema.py`.
3. Wire startup and outbound routing in `sideclaw/cli/main.py`, the relevant `sideclaw/cli/commands/` module, and `sideclaw/app/` if the new channel changes host composition.
4. Add focused adapter tests plus at least one integration-path test if message flow changes.

### Adding a provider

1. Implement the `LLMProvider` contract in `sideclaw/providers/`.
2. Register known models in `ModelRegistry._register_defaults()` in `sideclaw/providers/models.py`.
3. Extend config loading/schema.
4. Add instantiation branch in `_build_provider()` in `sideclaw/app/factory.py`.
5. Verify tool-call parsing and error-path behavior in tests.

### Adding or changing workspace skills

1. Update `sideclaw/skills/**/SKILL.md`.
2. Keep frontmatter accurate: `name`, `summary` or `description`, plus `read_when` and `tags` when relevance matters.
3. Verify ranking/selection behavior in `tests/skills/test_loader.py` and prompt inclusion behavior in `tests/agent/test_prompt_builder.py`.

## Testing Expectations

- For prompt-context changes, run:
  - `uv run pytest tests/agent/test_prompt_builder.py tests/skills/test_loader.py tests/test_integration.py`
- For tool changes, run the affected `tests/tools/test_*.py` modules and at least one agent-loop path if registration or approval behavior changed.
- For CLI/config changes, run:
  - `uv run pytest tests/app/test_factory.py tests/app/test_cli.py tests/app/test_gateway.py tests/cli/test_commands.py tests/cli/test_render.py tests/config/test_loader.py tests/config/test_schema.py`
- For session, memory, or cron changes, run the corresponding focused tests and then the full suite if the change crosses subsystem boundaries.

Do not claim a behavior change is safe without running the tests that exercise that subsystem.

## Sharp Edges

- `exec` is intentionally high-trust and approval-gated. Keep safety checks and environment redaction intact.
- Browser tooling is optional and should fail closed when Playwright or runtime requirements are unavailable.
- Cron jobs execute through the same agent/runtime path as live messages. Avoid changes that create self-scheduling or duplicate-delivery loops.
- Skill selection is heuristic. Small frontmatter or matching changes can have broad prompt effects.
- Workspace document writes are bounded and target-aware; avoid bypassing `WorkspaceDocs` when editing canonical memory docs in runtime code.

## Related Docs

- `README.md`: user-facing setup and usage
- `TECHNICAL.md`: broader internal architecture and runtime behavior
- `sideclaw/templates/workspace/AGENTS.md`: scaffolded downstream workspace guide, not this repo's contributor guide

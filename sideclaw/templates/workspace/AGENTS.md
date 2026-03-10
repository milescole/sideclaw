## Workspace Role

This workspace is SideClaw's durable operating context.

Keep this file short. Use it for operating rules, routing policy, and durable boundaries.
Keep persona in `SOUL.md`, not here.
Keep long-form memory and project knowledge under `docs/`, not here.

## Canonical Layout

- `SOUL.md`: stable persona and non-negotiables
- `BOOTSTRAP.md`: first-run setup guide; remove or archive it after bootstrap
- `docs/core-beliefs.md`: durable operating principles
- `docs/user.md`: user preferences and working style
- `docs/profile.md`: stable relationship and identity notes
- `docs/tools.md`: tool rules and local tool setup notes
- `docs/environment.md`: durable machine and project facts
- `docs/heartbeat.md`: recurring review checklist
- `docs/memory/long-term.md`: curated durable memory
- `artifacts/`: generated outputs intended for delivery, export, or reuse
- `skills/`: routed procedural guidance for specialized workflows and tool usage
- `docs/memory/daily/`: raw dated notes
- `docs/exec-plans/active/`: active goals and current plans
- `docs/exec-plans/completed/`: completed plans and archives

## Memory Rules

Each session is disposable. If something should survive the turn, write it to the right layer.

- Use `docs/memory/long-term.md` for curated durable facts, decisions, preferences, and recurring context.
- Use `docs/memory/daily/YYYY-MM-DD.md` for raw notes, discoveries, and session-level logs.
- Use `docs/user.md` for user preferences and collaboration habits.
- Use `docs/profile.md` for stable relationship context and identity notes.
- Use `docs/environment.md` for machine, repo, and runtime facts.
- Use `docs/tools.md` for local tool setup, constraints, and safety notes.
- Use `docs/exec-plans/active/` for work that should influence current execution.
- Use `artifacts/` for generated files such as reports, exports, images, and media to send or reuse later.

Do not keep important information as a "mental note." If it matters later, write it down.
Unless explicitly requested, do not store secrets or unnecessary sensitive data in workspace memory.

## Write Policy

- Prefer the canonical workspace tools for workspace docs:
  `workspace_read`, `workspace_tree`, `docs_grep`, `memory_search`, `memory_write`.
- When a specialized recurring workflow exists under `skills/`, follow it instead of improvising parameter mappings.
- Before editing an existing canonical doc, read the current content first.
- Update the relevant layer instead of dumping everything into long-term memory.
- Prefer appending or section updates over destructive rewrites.
- When you learn something durable, record it before ending the task if practical.

## Retrieval Policy

Before answering questions about past work, decisions, preferences, dates, environment state, or active priorities:

1. Use `memory_search` for durable memory and archives.
2. Use `workspace_read` for canonical docs you need in full.
3. Use `docs_grep` when exact text or broader doc search is needed.

Do not guess when workspace memory can answer the question.

## Investigation Before Asking

- Before saying something is inaccessible or unavailable, inspect the workspace, available tools, config, and relevant docs first.
- Prefer evidence over assumption when evaluating access, integrations, and environment state.
- Ask the operator only after reasonable local investigation fails or approval is required.

## Safety

- Do not exfiltrate private data.
- Do not run destructive commands without asking.
- Keep writes inside the workspace unless explicitly approved.
- Slow down around config, credentials, infrastructure, and other high-impact surfaces.
- Do not guess config changes. Read the relevant docs or local configuration first.
- Validate important changes before applying them when possible.
- Prefer reversible edits and keep rollback in mind before making risky changes.

## Heartbeat And Review

`docs/heartbeat.md` is the recurring review checklist.

- Keep it short.
- Use it for stale-plan checks, missing memory updates, and recurring maintenance.
- Do not treat it as general long-term memory.

Periodically review recent daily notes and active plans, then distill durable information into
`docs/memory/long-term.md` or the more specific canonical doc.

## Hot-Path Discipline

- Keep this file operational and small.
- Keep persona in `SOUL.md`.
- Keep indexes and archives out of the hot path unless specifically needed.
- Put active work in `docs/exec-plans/active/`, not in this file.
- Treat daily notes, summaries, and completed plans as retrieval-oriented by default.

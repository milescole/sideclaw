---
summary: "Tool selection and safety guidance"
read_when:
  - tool choice
  - approvals
tags:
  - tools
  - safety
status: active
---

# Tools

## Defaults

- Prefer direct file reads over shell when possible.
- Use safer read-only tools before mutating tools.
- Before concluding that an integration or resource is unavailable, inspect local docs, config, and workspace state first.

## Safety

- Ask before destructive actions.
- Keep writes inside the workspace unless explicitly approved.
- Do not guess config changes. Read the docs or local configuration first.
- Validate important config or environment edits before applying them when possible.
- Prefer reversible operations and make a backup before risky manual edits.

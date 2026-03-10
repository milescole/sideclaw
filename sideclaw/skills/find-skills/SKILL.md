---
summary: "Discover and install additional agent skills when the user needs a capability that may already exist"
read_when:
  - find a skill for
  - is there a skill for
  - can you install a skill
  - search for a skill
  - extend your capabilities
  - look for a workflow
tags:
  - skills
  - install
  - discovery
  - workflow
  - tools
status: active
---

# Find Skills

Use this skill when the user is looking for a capability that may already exist as an installable skill.

## When to use it

- The user asks whether a skill exists for a domain or task.
- The user wants to extend the agent with a new workflow or template.
- The user is unsure whether to build a new skill or reuse an existing one.

## Workflow

1. Identify the task or domain clearly enough to form a search query.
2. If shell execution is available, search the skills ecosystem with a focused query:

```text
exec(command="npx skills find <query>")
```

3. If you find a relevant skill, present:
   - the skill name
   - what it appears to help with
   - the install command
   - the skills.sh link when available
4. If the user wants it installed and shell execution is available, install it explicitly:

```text
exec(command="npx skills add <owner/repo@skill> -g -y")
```

5. If shell execution is not available, provide the exact command for the user to run manually.

## Search guidance

- Use specific multi-word queries like `react performance`, `pr review`, or `docker deploy`.
- Try adjacent terms if the first search is sparse.
- Prefer reuse over inventing a new skill when a good existing one already matches.

## When no skill is found

- Say that no strong match was found.
- Offer to handle the task directly with current tools.
- If the workflow is likely to recur, suggest creating a local skill instead.

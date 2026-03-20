"""Per-category context window usage breakdown.

Produces a Claude Code-style display showing what consumes the context
window: system prompt, memory files, skills, tools, messages, autocompact
buffer, and free space — each with token count and percentage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sideclaw.utils.tokens import count_tokens, format_token_count, get_context_window


@dataclass
class ContextUsageBreakdown:
    """Token usage by prompt category."""

    model: str
    context_window: int
    system_prompt_tokens: int = 0
    memory_files_tokens: int = 0
    skills_tokens: int = 0
    tools_tokens: int = 0
    messages_tokens: int = 0
    autocompact_buffer_tokens: int = 0
    free_space_tokens: int = 0
    total_used_tokens: int = 0

    def __post_init__(self) -> None:
        self.total_used_tokens = (
            self.system_prompt_tokens
            + self.memory_files_tokens
            + self.skills_tokens
            + self.tools_tokens
            + self.messages_tokens
            + self.autocompact_buffer_tokens
        )
        self.free_space_tokens = max(0, self.context_window - self.total_used_tokens)

    def render_bar(self, width: int = 40) -> str:
        """Render an ASCII bar chart showing proportional category usage."""
        if self.context_window <= 0:
            return "[" + "?" * width + "]"

        categories = [
            ("S", self.system_prompt_tokens),
            ("M", self.memory_files_tokens),
            ("K", self.skills_tokens),
            ("T", self.tools_tokens),
            ("C", self.messages_tokens),
            ("A", self.autocompact_buffer_tokens),
            (".", self.free_space_tokens),
        ]
        bar = []
        for char, tokens in categories:
            cells = round(tokens / self.context_window * width)
            bar.append(char * cells)
        result = "".join(bar)
        # Pad or trim to exact width
        result = result[:width].ljust(width, ".")
        return f"[{result}]"

    def render_detail(self) -> str:
        """Render multi-line detail with token counts and percentages."""
        lines = ["Estimated usage by category"]
        categories = [
            ("System prompt", self.system_prompt_tokens),
            ("Memory files", self.memory_files_tokens),
            ("Skills", self.skills_tokens),
            ("Tools", self.tools_tokens),
            ("Messages", self.messages_tokens),
            ("Autocompact buffer", self.autocompact_buffer_tokens),
            ("Free space", self.free_space_tokens),
        ]
        for label, tokens in categories:
            pct = (tokens / self.context_window * 100) if self.context_window else 0
            lines.append(f"  {label}: {format_token_count(tokens)} tokens ({pct:.1f}%)")
        return "\n".join(lines)

    def render_compact(self) -> str:
        """One-line summary: model, used/total tokens, percentage."""
        pct = (self.total_used_tokens / self.context_window * 100) if self.context_window else 0
        return (
            f"{self.model} · "
            f"{format_token_count(self.total_used_tokens)}/{format_token_count(self.context_window)} "
            f"tokens ({pct:.1f}%)"
        )


def compute_context_usage(
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
    model: str,
    tools: list[dict[str, Any]] | None = None,
    bundle_sections: dict[str, int] | None = None,
    skills_text: str = "",
    compression_threshold: float = 0.5,
) -> ContextUsageBreakdown:
    """Compute a per-category context usage breakdown.

    Args:
        messages: The full message list (system + history + user).
        system_prompt: The assembled system prompt text.
        model: Model identifier for context window lookup.
        tools: Tool schema definitions (JSON-serializable dicts).
        bundle_sections: Map of section path -> token count from workspace context.
        skills_text: Loaded skill instructions text.
        compression_threshold: Fraction of context reserved for autocompact.
    """
    context_window = get_context_window(model) or 200_000

    # System prompt base (identity text, minus memory/skills which are counted separately)
    system_prompt_tokens = count_tokens(system_prompt)

    # Memory files
    memory_tokens = sum(bundle_sections.values()) if bundle_sections else 0

    # Skills
    skills_tokens = count_tokens(skills_text) if skills_text else 0

    # Adjust system prompt to not double-count memory and skills
    system_prompt_tokens = max(0, system_prompt_tokens - memory_tokens - skills_tokens)

    # Tools (JSON schemas)
    tools_tokens = 0
    if tools:
        tools_tokens = count_tokens(json.dumps(tools))

    # Messages (everything except system message)
    message_tokens = 0
    for msg in messages:
        if msg.get("role") == "system":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            message_tokens += count_tokens(content)

    # Autocompact buffer
    autocompact_tokens = int(context_window * compression_threshold)

    return ContextUsageBreakdown(
        model=model,
        context_window=context_window,
        system_prompt_tokens=system_prompt_tokens,
        memory_files_tokens=memory_tokens,
        skills_tokens=skills_tokens,
        tools_tokens=tools_tokens,
        messages_tokens=message_tokens,
        autocompact_buffer_tokens=autocompact_tokens,
    )

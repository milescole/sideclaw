"""Usage display rendering for /usage and /insights commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sideclaw.metrics.context_usage import compute_context_usage
from sideclaw.utils.tokens import format_token_count

if TYPE_CHECKING:
    from sideclaw.agent.prompt_builder import PromptBuilder
    from sideclaw.config.schema import Config
    from sideclaw.metrics.usage import UsageTracker
    from sideclaw.session.session import Session


def render_usage(
    *,
    session: Session,
    config: Config,
    usage_tracker: UsageTracker | None = None,
    prompt_builder: PromptBuilder | None = None,
) -> str:
    """Build the full /usage output string."""
    lines: list[str] = []

    if prompt_builder is not None:
        history = session.get_history(
            max_messages=max(1, config.memory.keep_recent_messages)
        )
        system_prompt = prompt_builder.build_system_prompt(history=history)
        bundle = prompt_builder._workspace_context.build_bundle(history=history)
        skills_text, _warnings = prompt_builder._skills.load_relevant_skills(
            current_message="", history=history
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
        ]
        breakdown = compute_context_usage(
            messages=messages,
            system_prompt=system_prompt,
            model=config.agent.model,
            bundle_sections=bundle.section_token_counts,
            skills_text=skills_text,
            compression_threshold=config.agent.compression_threshold,
        )
        lines.append("Context Usage")
        lines.append(breakdown.render_bar())
        lines.append(breakdown.render_compact())
        lines.append("")
        lines.append(breakdown.render_detail())
    else:
        lines.append("Context usage data not available.")

    if usage_tracker is not None:
        totals = usage_tracker.get_session_totals(session.key)
        lines.append("")
        lines.append("Session totals")
        lines.append(f"  Prompt tokens: {format_token_count(totals.prompt_tokens)}")
        lines.append(f"  Completion tokens: {format_token_count(totals.completion_tokens)}")
        lines.append(f"  Total tokens: {format_token_count(totals.total_tokens)}")
        lines.append(f"  LLM calls: {totals.llm_calls}")
        if totals.llm_calls > 0 and totals.total_duration_ms > 0:
            avg_ms = totals.total_duration_ms // totals.llm_calls
            lines.append(f"  Avg latency: {avg_ms}ms")

    return "\n".join(lines)

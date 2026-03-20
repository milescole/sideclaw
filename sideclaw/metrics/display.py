"""Usage display rendering for /usage and /insights commands."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sideclaw.metrics.context_usage import compute_context_usage
from sideclaw.metrics.pricing import PricingRegistry
from sideclaw.utils.tokens import format_token_count

if TYPE_CHECKING:
    from sideclaw.agent.prompt_builder import PromptBuilder
    from sideclaw.config.schema import Config
    from sideclaw.metrics.execution_log import ExecutionLogger
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
        cost = _estimate_session_cost(usage_tracker, session.key)
        if cost > 0:
            lines.append(f"  Estimated cost: ${cost:.4f}")

    return "\n".join(lines)


def _estimate_session_cost(tracker: UsageTracker, session_key: str) -> float:
    """Estimate cost for in-memory session records."""
    records = [r for r in tracker._records if r.session_key == session_key]
    if not records:
        return 0.0
    return PricingRegistry().estimate_session_cost(records)


def render_insights(
    *,
    days: int = 7,
    usage_tracker: UsageTracker | None = None,
    execution_logger: ExecutionLogger | None = None,
) -> str:
    """Build the full /insights output string."""
    if usage_tracker is None:
        return "Usage tracking is not enabled."

    since = datetime.now(UTC) - timedelta(days=days)
    records = usage_tracker.get_all_records(since=since)

    if not records:
        return f"No usage data in the last {days} days."

    lines: list[str] = [f"Usage Insights (last {days} days)"]

    total_prompt = sum(r.prompt_tokens for r in records)
    total_completion = sum(r.completion_tokens for r in records)
    total_tokens = total_prompt + total_completion
    total_duration = sum(r.duration_ms or 0 for r in records)

    lines.append(
        f"  Total tokens: {format_token_count(total_tokens)} "
        f"(prompt: {format_token_count(total_prompt)}, "
        f"completion: {format_token_count(total_completion)})"
    )
    lines.append(f"  Total LLM calls: {len(records)}")
    if records:
        lines.append(f"  Avg tokens/call: {format_token_count(total_tokens // len(records))}")
    if total_duration > 0:
        avg_ms = total_duration // len(records)
        lines.append(f"  Avg latency: {avg_ms}ms")
    cost = PricingRegistry().estimate_session_cost(records)
    if cost > 0:
        lines.append(f"  Estimated cost: ${cost:.4f}")

    # Model breakdown
    model_tokens: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        model_tokens[r.model][0] += 1
        model_tokens[r.model][1] += r.total_tokens
    if model_tokens:
        lines.append("  Models used:")
        for model, (calls, tokens) in sorted(
            model_tokens.items(), key=lambda x: x[1][1], reverse=True
        ):
            lines.append(f"    {model}: {calls} calls, {format_token_count(tokens)} tokens")

    # Tool breakdown (only for records with tool_name)
    tool_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        if r.tool_name:
            tool_counts[r.tool_name][0] += 1
            tool_counts[r.tool_name][1] += r.duration_ms or 0
    if tool_counts:
        lines.append("  Top tools:")
        for tool, (calls, dur) in sorted(
            tool_counts.items(), key=lambda x: x[1][0], reverse=True
        )[:10]:
            avg = dur // calls if calls else 0
            lines.append(f"    {tool}: {calls} calls, {avg}ms avg")

    # Daily breakdown
    daily: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        day = r.timestamp[:10]
        daily[day][0] += r.total_tokens
        daily[day][1] += 1
    if daily:
        lines.append("  Daily breakdown:")
        for day in sorted(daily, reverse=True):
            tokens, calls = daily[day]
            lines.append(f"    {day}: {format_token_count(tokens)} tokens, {calls} calls")

    # Execution log summary
    if execution_logger is not None:
        runs = execution_logger.get_runs_since(since)
        if runs:
            lines.append(f"  Completed runs: {len(runs)}")

    return "\n".join(lines)

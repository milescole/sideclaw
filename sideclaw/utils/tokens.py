"""Token counting and formatting utilities.

Pre-flight estimation uses tiktoken's o200k_base encoding (the newest BPE
encoding, shared by GPT-4o/o3/o4-mini) as a reasonable approximation across
all modern models including Claude.  Falls back to len(text)//4 when tiktoken
is not installed.

Post-flight tracking should use the API-returned ``LLMResponse.usage`` dict
which contains exact counts from the provider.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sideclaw.providers.models import ModelRegistry

CHARS_PER_TOKEN_FALLBACK = 4


@lru_cache(maxsize=1)
def _get_encoding():
    """Lazy-load the o200k_base tiktoken encoding."""
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except (ImportError, Exception):
        return None


def count_tokens(text: str, model: str = "") -> int:
    """Estimate token count for a string.

    Uses tiktoken o200k_base when available, otherwise len(text) // 4.
    The *model* parameter is accepted for future extensibility but currently
    the same encoding is used for all models.
    """
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    return max(1, len(text) // CHARS_PER_TOKEN_FALLBACK)


def count_message_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens across a list of chat messages.

    Extracts text from ``content``, ``tool_calls``, ``name``, and
    ``tool_call_id`` fields — mirrors the estimation logic in
    ``PromptBuilder._estimate_message_chars`` but returns tokens.
    """
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content", "")
                    if text:
                        parts.append(str(text))
                elif isinstance(block, str):
                    parts.append(block)
        role = msg.get("role", "")
        if role:
            parts.append(role)
        for tc in msg.get("tool_calls") or []:
            func = tc.get("function") or {}
            parts.append(str(func.get("name") or ""))
            parts.append(str(func.get("arguments") or ""))
        name = msg.get("name")
        if name:
            parts.append(str(name))
        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            parts.append(str(tool_call_id))
    return count_tokens("\n".join(parts))


@lru_cache(maxsize=1)
def _get_registry() -> ModelRegistry:
    return ModelRegistry()


def get_context_window(model: str) -> int | None:
    """Look up the context window size for a model from the registry."""
    info = _get_registry().get(model)
    return info.context_window if info else None


def format_token_count(value: int) -> str:
    """Format a token count compactly: 1234 → '1.23K', 1234567 → '1.23M'."""
    abs_value = abs(int(value))
    if abs_value < 1_000:
        return str(int(value))

    sign = "-" if value < 0 else ""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs_value >= threshold:
            scaled = abs_value / threshold
            if scaled < 10:
                text = f"{scaled:.2f}"
            elif scaled < 100:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.0f}"
            text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"

    return f"{value:,}"


def format_duration(seconds: float) -> str:
    """Format seconds into a compact human string: 45 → '45s', 125 → '2m'."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"

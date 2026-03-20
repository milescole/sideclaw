"""Auto-generate descriptive session titles from the first exchange."""

import re

from loguru import logger

from sideclaw.metrics.cost_guard import CostGuard
from sideclaw.providers.base import LLMProvider
from sideclaw.session.session import Session

_TITLE_PROMPT = (
    "Generate a short, descriptive title (3-7 words) for a conversation "
    "that starts with the following exchange. "
    "Return ONLY the title text, nothing else."
)

_MAX_INPUT_CHARS = 500
_MAX_TITLE_CHARS = 80
_MAX_EXCHANGES_FOR_TITLE = 2

_SKIP_VALUES = frozenset({
    "",
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "yes",
    "no",
    "sure",
    "bye",
    "goodbye",
    "/new",
    "/help",
    "/compact",
    "test",
    "ping",
})


def _clean_title(raw: str) -> str:
    """Strip quotes, 'Title:' prefix, and enforce length limit."""
    title = raw.strip().strip('"\'')
    title = re.sub(r"^[Tt]itle:\s*", "", title)
    title = title.strip().strip('"\'')
    if len(title) > _MAX_TITLE_CHARS:
        title = title[:_MAX_TITLE_CHARS].rsplit(" ", 1)[0].rstrip(".,;:- ")
    return title


async def generate_title(
    provider: LLMProvider,
    model: str,
    user_message: str,
    assistant_response: str,
    cost_guard: CostGuard | None = None,
) -> str | None:
    """Generate a session title via LLM."""
    truncated_user = user_message[:_MAX_INPUT_CHARS]
    truncated_assistant = assistant_response[:_MAX_INPUT_CHARS]

    prompt = (
        f"{_TITLE_PROMPT}\n\n"
        f"User: {truncated_user}\n"
        f"Assistant: {truncated_assistant}"
    )

    if cost_guard is not None:
        allowed, reason = cost_guard.check_allowed(model)
        if not allowed:
            logger.debug(reason or "Skipping auto-title generation due to budget limits.")
            return None

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            max_tokens=30,
            temperature=0.3,
        )
    except (RuntimeError, OSError, ValueError, TimeoutError) as exc:
        logger.debug(f"Title generation failed: {exc}")
        return None

    if not response.content:
        return None

    title = _clean_title(response.content)
    return title if title else None


async def maybe_auto_title(
    session: Session,
    provider: LLMProvider,
    model: str,
    user_message: str,
    assistant_response: str,
    cost_guard: CostGuard | None = None,
) -> None:
    """Generate a title for the session if appropriate.

    Only fires on the first few exchanges. Skips trivial messages and
    sessions that already have a user-set title.
    """
    if session.title and session.title_source == "user":
        return

    user_message_count = sum(
        1 for msg in session.messages if msg.get("role") == "user"
    )
    if user_message_count > _MAX_EXCHANGES_FOR_TITLE:
        return

    if user_message.strip().lower() in _SKIP_VALUES:
        return

    title = await generate_title(
        provider,
        model,
        user_message,
        assistant_response,
        cost_guard,
    )
    if title:
        session.title = title
        session.title_source = "auto"

"""Persistence helpers for runtime execution."""

import json_repair
from loguru import logger

from sideclaw.config.schema import Config
from sideclaw.memory.store import MemoryStore
from sideclaw.providers.base import LLMProvider
from sideclaw.session.manager import SessionManager
from sideclaw.session.session import Session
from sideclaw.workspace.docs import WorkspaceDocs


def save_session_state(*, session: Session, session_manager: SessionManager) -> None:
    """Persist the current session state without additional side effects."""
    session_manager.save(session)


def _unconsolidated_chars(session: Session) -> int:
    """Estimate the total character length of unconsolidated messages."""
    total = 0
    for msg in session.messages[session.last_consolidated :]:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
    return total


def _should_compress(session: Session, config: Config) -> bool:
    """Check whether consolidation should trigger.

    Triggers on either condition:
    - Message count exceeds ``memory_window``
    - Unconsolidated character size exceeds ``compression_threshold * max_context_chars``
    """
    unconsolidated_count = len(session.messages) - session.last_consolidated
    if unconsolidated_count >= config.agent.memory_window:
        return True

    threshold = config.agent.compression_threshold
    if threshold > 0:
        char_limit = int(config.memory.max_context_chars * threshold)
        if _unconsolidated_chars(session) >= char_limit:
            return True

    return False


async def persist_session_state(
    *,
    session: Session,
    session_manager: SessionManager,
    config: Config,
    provider: LLMProvider,
    memory_store: MemoryStore,
    workspace_docs: WorkspaceDocs,
) -> None:
    """Persist the session and trigger consolidation when needed."""
    save_session_state(session=session, session_manager=session_manager)

    if _should_compress(session, config):
        await consolidate_memory(
            session=session,
            session_manager=session_manager,
            config=config,
            provider=provider,
            memory_store=memory_store,
            workspace_docs=workspace_docs,
        )


async def consolidate_memory(
    *,
    session: Session,
    session_manager: SessionManager,
    config: Config,
    provider: LLMProvider,
    memory_store: MemoryStore,
    workspace_docs: WorkspaceDocs,
) -> None:
    """Consolidate old messages into long-term memory via the LLM."""
    old_messages = session.messages[session.last_consolidated : -config.agent.memory_window]
    if not old_messages:
        return

    current_memory = memory_store.read_long_term()
    summary_prompt = (
        "Summarize the key durable information from these messages. "
        "Merge with the existing long-term memory. "
        "Return only JSON with keys durable_facts, decisions, and preferences. "
        "Each value must be an array of short markdown bullet lines without headings.\n\n"
        f"## Current Memory\n{current_memory}\n\n"
        f"## Messages to Consolidate\n"
    )
    for msg in old_messages:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            summary_prompt += f"**{msg['role']}**: {msg['content']}\n"

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": summary_prompt}],
            model=config.agent.model,
        )
        if response.content:
            sections = parse_consolidated_memory(response.content)
            if sections:
                workspace_docs.update_long_term_sections(sections)
            entry_parts = [
                msg["content"][:100]
                for msg in old_messages
                if msg.get("role") == "user" and msg.get("content")
            ]
            if entry_parts:
                memory_store.append_history(f"Topics: {'; '.join(entry_parts[:3])}")
            session.last_consolidated = len(session.messages) - config.agent.memory_window
            session_manager.save(session)
            logger.info("Memory consolidated")
    except (RuntimeError, OSError, ValueError, TimeoutError) as e:
        logger.error(f"Memory consolidation failed: {e}")


def parse_consolidated_memory(content: str) -> dict[str, str]:
    """Parse the structured long-term memory update returned by the LLM."""
    try:
        payload = json_repair.loads(content)
    except (TypeError, ValueError):
        payload = {}

    if isinstance(payload, dict):
        sections: dict[str, str] = {}
        for field, section in (
            ("durable_facts", "Durable Facts"),
            ("decisions", "Decisions"),
            ("preferences", "Preferences"),
        ):
            value = payload.get(field)
            if isinstance(value, list):
                lines = [str(item).strip() for item in value if str(item).strip()]
                if lines:
                    sections[section] = "\n".join(lines)
            elif isinstance(value, str) and value.strip():
                sections[section] = value.strip()
        if sections:
            return sections

    fallback_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not fallback_lines:
        return {}
    return {"Durable Facts": "\n".join(fallback_lines)}

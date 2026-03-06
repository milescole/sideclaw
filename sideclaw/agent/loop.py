"""Core agent loop: receive message, call LLM, execute tools, respond."""

from pathlib import Path
from typing import Any

import json_repair
from loguru import logger

from sideclaw.agent.context import ContextBuilder
from sideclaw.bus.messages import InboundMessage, OutboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.config.schema import Config
from sideclaw.memory.store import MemoryStore
from sideclaw.providers.base import LLMProvider, LLMResponse
from sideclaw.session.manager import Session, SessionManager
from sideclaw.tools.registry import ToolRegistry

MAX_TOOL_ITERATIONS = 20


class AgentLoop:
    """The core agent: processes messages through LLM + tool loop."""

    def __init__(
        self,
        *,
        config: Config,
        bus: MessageBus,
        provider: LLMProvider,
        session_manager: SessionManager,
        workspace: Path,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._session_manager = session_manager
        self._workspace = Path(workspace)
        self._context = ContextBuilder(self._workspace)
        self._memory = MemoryStore(self._workspace)
        self._registry = ToolRegistry()

    def register_default_tools(self) -> None:
        """Register the built-in tool set."""
        from sideclaw.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
        from sideclaw.tools.memory import SaveMemoryTool
        from sideclaw.tools.shell import ExecTool
        from sideclaw.tools.web import WebFetchTool, WebSearchTool

        self._registry.register(ReadFileTool(self._workspace))
        self._registry.register(WriteFileTool(self._workspace))
        self._registry.register(EditFileTool(self._workspace))
        self._registry.register(ListDirTool(self._workspace))
        if self._config.tools.exec_enabled:
            self._registry.register(
                ExecTool(workspace=self._workspace, timeout=self._config.tools.exec_timeout)
            )
        self._registry.register(WebSearchTool(api_key=self._config.tools.web_search_api_key))
        self._registry.register(WebFetchTool())
        self._registry.register(SaveMemoryTool(self._memory))

    async def process_message(self, msg: InboundMessage) -> None:
        """Process a single inbound message through the agent loop."""
        session_key = f"{msg.channel}:{msg.chat_id}"
        session = self._session_manager.get_or_create(session_key)

        # Build context
        history = session.get_history(max_messages=100)
        messages = self._context.build_messages(
            history,
            msg.text,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        # Add user message to session
        session.messages.append({"role": "user", "content": msg.text})

        # Get tool definitions
        tools = self._registry.get_definitions() or None

        # Agent loop: call LLM, execute tools, repeat
        for _iteration in range(MAX_TOOL_ITERATIONS):
            response = await self._provider.chat(
                messages=messages,
                tools=tools,
                model=self._config.agent.model,
                max_tokens=self._config.agent.max_tokens,
                temperature=self._config.agent.temperature,
            )

            if response.finish_reason == "error":
                await self._send_response(msg, response.content or "An error occurred.")
                session.messages.append({"role": "assistant", "content": response.content})
                break

            if response.tool_calls:
                # Add assistant message with tool calls
                assistant_msg = self._build_assistant_tool_msg(response)
                messages.append(assistant_msg)
                session.messages.append(assistant_msg)

                # Execute each tool call
                for tc in response.tool_calls:
                    result = await self._execute_tool(tc.name, tc.arguments)
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    session.messages.append(tool_msg)
                continue

            # Text response - we're done
            content = response.content or ""
            session.messages.append({"role": "assistant", "content": content})
            await self._send_response(msg, content)
            break
        else:
            # Max iterations reached
            await self._send_response(msg, "(Stopped: too many tool iterations)")
            session.messages.append(
                {"role": "assistant", "content": "(Stopped: too many tool iterations)"}
            )

        # Save session
        self._session_manager.save(session)

        # Check if memory consolidation needed
        unconsolidated = len(session.messages) - session.last_consolidated
        if unconsolidated >= self._config.agent.memory_window:
            await self._consolidate_memory(session)

    async def _execute_tool(self, name: str, arguments: str) -> str:
        """Execute a tool call and return the result."""
        try:
            params = json_repair.loads(arguments)
            if not isinstance(params, dict):
                params = {}
        except (TypeError, ValueError):
            params = {}
        logger.debug(f"Executing tool: {name}({params})")
        return await self._registry.execute(name, params)

    async def _send_response(self, original: InboundMessage, text: str) -> None:
        """Send a response back through the bus."""
        await self._bus.publish_outbound(
            OutboundMessage(channel=original.channel, chat_id=original.chat_id, text=text)
        )

    def _build_assistant_tool_msg(self, response: LLMResponse) -> dict[str, Any]:
        """Build an assistant message with tool calls for the message history."""
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ],
        }

    async def _consolidate_memory(self, session: Session) -> None:
        """Consolidate old messages into long-term memory via LLM."""
        old_messages = session.messages[
            session.last_consolidated : -self._config.agent.memory_window
        ]
        if not old_messages:
            return

        current_memory = self._memory.read_long_term()
        summary_prompt = (
            "Summarize the key facts and decisions from these messages. "
            "Merge with existing memory. Return only the updated memory content.\n\n"
            f"## Current Memory\n{current_memory}\n\n"
            f"## Messages to Consolidate\n"
        )
        for msg in old_messages:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                summary_prompt += f"**{msg['role']}**: {msg['content']}\n"

        try:
            response = await self._provider.chat(
                messages=[{"role": "user", "content": summary_prompt}],
                model=self._config.agent.model,
            )
            if response.content:
                self._memory.write_long_term(response.content)
                # Build history entry
                entry_parts = [
                    msg["content"][:100]
                    for msg in old_messages
                    if msg.get("role") == "user" and msg.get("content")
                ]
                if entry_parts:
                    self._memory.append_history(f"Topics: {'; '.join(entry_parts[:3])}")
                session.last_consolidated = len(session.messages) - self._config.agent.memory_window
                self._session_manager.save(session)
                logger.info("Memory consolidated")
        except (RuntimeError, OSError, ValueError, TimeoutError) as e:
            logger.error(f"Memory consolidation failed: {e}")

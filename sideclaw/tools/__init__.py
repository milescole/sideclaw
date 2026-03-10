"""Tooling module.

Owns the agent-facing tool abstractions, registry, and built-in tool
implementations for filesystem access, browser automation, messaging, media,
memory, scheduling, shell execution, and web access.

Modules:
    - base: Tool, truncate_tool_output — shared tool contract and helpers
    - browser: BrowserTool — unified browser automation surface
    - clarify: ClarifyTool — interactive clarifying questions
    - cron: CronTool — scheduled job management
    - filesystem: workspace file read/write/edit/list tools
    - image: ImageGenerationTool — image generation
    - memory: workspace and memory search/read/write tools
    - messaging: SendMessageTool — outbound cross-channel delivery
    - registry: ToolRegistry — registration, schema export, and validation
    - shell: ExecTool — guarded shell execution
    - tts: TextToSpeechTool — text-to-speech generation
    - web: WebSearchTool, WebFetchTool — external web lookup and fetch

Example:
    >>> from sideclaw.tools import ToolRegistry
    >>> from sideclaw.tools.filesystem import ReadFileTool
    >>> registry = ToolRegistry()
    >>> registry.register(ReadFileTool(workspace))
"""

from sideclaw.tools.base import Tool, truncate_tool_output
from sideclaw.tools.registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolRegistry",
    "truncate_tool_output",
]

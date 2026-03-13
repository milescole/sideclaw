"""Unified browser automation tool."""

from typing import Any

from sideclaw.browser import BrowserService
from sideclaw.runtime.context import get_tool_runtime_context
from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.base import Tool

READ_ONLY_ACTIONS = {
    "console_messages",
    "network_requests",
    "snapshot",
    "stop",
    "tabs",
}


class BrowserTool(Tool):
    """Single browser automation tool with an action-based Playwright API."""

    def __init__(self, service: BrowserService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Browser automation tool using Playwright. Supports start, stop, open, navigate, "
            "navigate_back, snapshot, screenshot, click, type, eval, evaluate, resize, "
            "console_messages, handle_dialog, file_upload, fill_form, install, press_key, "
            "network_requests, run_code, drag, hover, select_option, tabs, wait_for, "
            "pdf, and close."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "start",
                        "stop",
                        "open",
                        "navigate",
                        "navigate_back",
                        "screenshot",
                        "snapshot",
                        "click",
                        "type",
                        "eval",
                        "evaluate",
                        "resize",
                        "console_messages",
                        "handle_dialog",
                        "file_upload",
                        "fill_form",
                        "install",
                        "press_key",
                        "network_requests",
                        "run_code",
                        "drag",
                        "hover",
                        "select_option",
                        "tabs",
                        "wait_for",
                        "pdf",
                        "close",
                    ],
                    "description": "Action to perform.",
                },
                "url": {"type": "string", "description": "URL for open or navigate."},
                "page_id": {
                    "type": "string",
                    "description": "Browser page or tab identifier.",
                    "default": "default",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click, type, hover, or drag.",
                },
                "text": {"type": "string", "description": "Text for type or wait_for."},
                "code": {
                    "type": "string",
                    "description": "JavaScript code for eval, evaluate, or run_code.",
                },
                "path": {
                    "type": "string",
                    "description": "Output file path for screenshot or pdf.",
                },
                "wait": {
                    "type": "integer",
                    "description": "Milliseconds to wait before click.",
                    "default": 0,
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full page for screenshots.",
                    "default": False,
                },
                "width": {
                    "type": "integer",
                    "description": "Viewport width for resize.",
                    "default": 0,
                },
                "height": {
                    "type": "integer",
                    "description": "Viewport height for resize.",
                    "default": 0,
                },
                "level": {
                    "type": "string",
                    "description": "Console log level filter.",
                    "default": "info",
                },
                "filename": {"type": "string", "description": "Alternate output filename."},
                "accept": {
                    "type": "boolean",
                    "description": "Accept or dismiss dialog for handle_dialog.",
                    "default": True,
                },
                "prompt_text": {
                    "type": "string",
                    "description": "Prompt response text for dialogs.",
                },
                "ref": {"type": "string", "description": "Snapshot ref for element targeting."},
                "element": {"type": "string", "description": "Optional element description hint."},
                "paths_json": {
                    "type": "string",
                    "description": "JSON array string of file paths for file_upload.",
                },
                "fields_json": {
                    "type": "string",
                    "description": "JSON array string of form field definitions for fill_form.",
                },
                "key": {"type": "string", "description": "Key name for press_key."},
                "submit": {
                    "type": "boolean",
                    "description": "Press Enter after typing.",
                    "default": False,
                },
                "slowly": {
                    "type": "boolean",
                    "description": "Type character by character for type.",
                    "default": False,
                },
                "include_static": {
                    "type": "boolean",
                    "description": "Include static assets in network_requests.",
                    "default": False,
                },
                "screenshot_type": {
                    "type": "string",
                    "enum": ["png", "jpeg"],
                    "description": "Screenshot format.",
                    "default": "png",
                },
                "snapshot_filename": {
                    "type": "string",
                    "description": "Optional snapshot output file path.",
                },
                "double_click": {
                    "type": "boolean",
                    "description": "Double click for click.",
                    "default": False,
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button for click.",
                    "default": "left",
                },
                "modifiers_json": {
                    "type": "string",
                    "description": "JSON array string of modifier keys for click.",
                },
                "start_ref": {"type": "string", "description": "Start element ref for drag."},
                "end_ref": {"type": "string", "description": "End element ref for drag."},
                "start_selector": {"type": "string", "description": "Start CSS selector for drag."},
                "end_selector": {"type": "string", "description": "End CSS selector for drag."},
                "start_element": {
                    "type": "string",
                    "description": "Optional start element description hint.",
                },
                "end_element": {
                    "type": "string",
                    "description": "Optional end element description hint.",
                },
                "values_json": {
                    "type": "string",
                    "description": "JSON array string or comma-separated values for select_option.",
                },
                "tab_action": {
                    "type": "string",
                    "enum": ["list", "new", "close", "select"],
                    "description": "Tab sub-action for tabs.",
                },
                "index": {
                    "type": "integer",
                    "description": "Tab index for tabs select or close.",
                    "default": -1,
                },
                "wait_time": {
                    "type": "number",
                    "description": "Seconds to wait for wait_for.",
                    "default": 0,
                },
                "text_gone": {
                    "type": "string",
                    "description": "Text that should disappear for wait_for.",
                },
                "frame_selector": {
                    "type": "string",
                    "description": "Iframe selector for snapshot or element actions.",
                },
                "headed": {
                    "type": "boolean",
                    "description": "Open a visible browser window when action=start.",
                    "default": False,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        if kwargs.get("action") in READ_ONLY_ACTIONS:
            return ApprovalRequirement.never
        return ApprovalRequirement.unless_session_approved

    def approval_action_type(self, **kwargs: Any) -> str:
        return f"browser_{kwargs.get('action', 'automation')}"

    def approval_description(self, **kwargs: Any) -> str:
        return f"browser {kwargs.get('action', 'automation')}"

    def approval_subject(self, **kwargs: Any) -> str:
        action = str(kwargs.get("action", "automation"))
        details: list[str] = []
        for key in (
            "url",
            "page_id",
            "ref",
            "selector",
            "text",
            "key",
            "tab_action",
            "path",
        ):
            value = kwargs.get(key)
            if value:
                details.append(f"{key}={str(value)[:120]}")
        if details:
            return f"{action}: " + ", ".join(details)
        return action

    async def execute(self, **kwargs: Any) -> str:
        return await self._service.execute(self._task_id(), **kwargs)

    @staticmethod
    def _task_id() -> str:
        context = get_tool_runtime_context()
        if context is not None:
            return context.session_key
        return "default"

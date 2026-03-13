import json

from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.tools.browser import BrowserTool


class _FakeBrowserService:
    async def execute(self, task_id: str, **kwargs: str) -> str:
        return json.dumps({"ok": True, "task_id": task_id, **kwargs})


async def test_browser_tool_dispatches_open() -> None:
    tool = BrowserTool(_FakeBrowserService())

    result = await tool.execute(action="open", url="https://example.com", page_id="main")

    parsed = json.loads(result)
    assert parsed["ok"] is True
    assert parsed["action"] == "open"
    assert parsed["url"] == "https://example.com"
    assert parsed["page_id"] == "main"


def test_browser_tool_marks_snapshot_as_read_only() -> None:
    tool = BrowserTool(_FakeBrowserService())

    assert tool.approval_requirement(action="snapshot") == ApprovalRequirement.never
    assert tool.approval_requirement(action="click") == ApprovalRequirement.unless_session_approved


def test_browser_tool_schema_includes_playwright_actions() -> None:
    tool = BrowserTool(_FakeBrowserService())

    actions = tool.parameters["properties"]["action"]["enum"]
    assert "start" in actions
    assert "navigate_back" in actions
    assert "console_messages" in actions
    assert "select_option" in actions

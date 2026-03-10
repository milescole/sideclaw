import json

from sideclaw.runtime.clarify import reset_clarify_callback, set_clarify_callback
from sideclaw.tools.clarify import ClarifyTool


async def test_clarify_tool_uses_runtime_callback() -> None:
    tool = ClarifyTool()
    token = set_clarify_callback(lambda question, choices: f"{question} / {choices[0]}")

    try:
        result = await tool.execute(question="Which one?", choices=["A", "B"])
    finally:
        reset_clarify_callback(token)

    parsed = json.loads(result)
    assert parsed["question"] == "Which one?"
    assert parsed["choices_offered"] == ["A", "B"]
    assert parsed["user_response"] == "Which one? / A"


async def test_clarify_tool_fails_without_callback() -> None:
    tool = ClarifyTool()

    result = await tool.execute(question="Which one?")

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "not available" in parsed["error"]

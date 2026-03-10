"""Interactive clarify tool."""

import json
from typing import Any

from sideclaw.runtime.clarify import get_clarify_callback
from sideclaw.tools.base import Tool

MAX_CHOICES = 4


class ClarifyTool(Tool):
    """Ask the user a clarifying question."""

    # Current scope: clarify is wired for synchronous CLI interaction via a runtime callback.
    # Messaging-platform pause/resume is a later feature because it needs a generalized
    # "wait for user reply and resume the tool loop" path beyond the existing approval flow.

    @property
    def name(self) -> str:
        return "clarify"

    @property
    def description(self) -> str:
        return (
            "Ask the user a clarifying question. Supports either open-ended input or up to four choices."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question to present to the user.",
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": MAX_CHOICES,
                    "description": "Optional predefined answer choices.",
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        question = str(kwargs["question"]).strip()
        if not question:
            return self._error("question is required")

        raw_choices = kwargs.get("choices")
        choices: list[str] | None = None
        if raw_choices is not None:
            if not isinstance(raw_choices, list):
                return self._error("choices must be a list of strings")
            normalized = [str(choice).strip() for choice in raw_choices if str(choice).strip()]
            choices = normalized[:MAX_CHOICES] or None

        callback = get_clarify_callback()
        if callback is None:
            return self._error("clarify is not available in this execution context")

        try:
            user_response = callback(question, choices)
        except Exception as exc:  # noqa: BLE001
            return self._error(f"failed to get user input: {exc}")

        return json.dumps(
            {
                "question": question,
                "choices_offered": choices,
                "user_response": str(user_response).strip(),
            },
            indent=2,
        )

    @staticmethod
    def _error(message: str) -> str:
        return json.dumps({"success": False, "error": message}, indent=2)

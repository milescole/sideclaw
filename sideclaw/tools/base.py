"""Abstract base class for tools."""

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from sideclaw.runtime.models.approval import ApprovalRequirement

DEFAULT_MAX_TOOL_OUTPUT_CHARS = 10_000


def truncate_tool_output(
    output: str,
    *,
    max_chars: int = DEFAULT_MAX_TOOL_OUTPUT_CHARS,
) -> str:
    """Bound tool output before it is sent back into model context.

    Uses a head+tail strategy so the LLM sees both the beginning and end of
    output (exit codes, summaries, and errors are typically at the end).
    """
    if len(output) <= max_chars:
        return output
    half = max_chars // 2
    omitted = len(output) - max_chars
    return output[:half] + f"\n\n... ({omitted:,} chars omitted) ...\n\n" + output[-half:]


class Tool(ABC):
    """Base class for all tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calling."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description shown to the LLM."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""
        ...

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        """Return the approval requirement for this invocation."""
        return ApprovalRequirement.never

    def approval_key(self, **kwargs: Any) -> str:
        """Return the key used for session-scoped approval caching."""
        return self.name

    def approval_subject(self, **kwargs: Any) -> str:
        """Return the user-visible subject shown in approval prompts."""
        return self.name

    def approval_action_type(self, **kwargs: Any) -> str:
        """Return a short action type for approval records."""
        return self.name

    def approval_description(self, **kwargs: Any) -> str:
        """Return a short user-facing description for approval prompts."""
        return self.description

    def display_arguments(self, **kwargs: Any) -> dict[str, Any] | None:
        """Return redacted arguments for approval prompts, if needed."""
        return kwargs or None

    def parameter_schema(self) -> dict[str, Any]:
        """Return the normalized parameter schema used for advertising and validation."""
        schema = deepcopy(self.parameters)
        if schema.get("type") == "object" and "properties" in schema:
            schema.setdefault("additionalProperties", False)
        return schema

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameter_schema(),
            },
        }

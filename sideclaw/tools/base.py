"""Abstract base class for tools."""

from abc import ABC, abstractmethod
from typing import Any

from sideclaw.runtime.models import ApprovalRequirement


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

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

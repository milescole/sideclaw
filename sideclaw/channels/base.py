"""Base channel interface."""

from abc import ABC, abstractmethod

from loguru import logger

from sideclaw.bus.messages import OutboundMessage
from sideclaw.bus.queue import MessageBus


class BaseChannel(ABC):
    """Abstract base class for chat platform channels."""

    def __init__(
        self, bus: MessageBus, channel_name: str, allow_from: list[str] | None = None
    ) -> None:
        self._bus = bus
        self._channel_name = channel_name
        self._allow_from = allow_from or []
        if not self._allow_from:
            logger.warning(
                f"Channel '{channel_name}' has empty allow_from — all access denied. "
                "Set allow_from to a list of sender IDs, or [\"*\"] to allow everyone."
            )

    @abstractmethod
    async def start(self) -> None:
        """Connect to the platform and start listening."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect and cleanup."""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message back to the platform."""

    @property
    def channel_name(self) -> str:
        """Channel identifier used for routing outbound messages."""
        return self._channel_name

    def is_allowed(self, sender_id: str) -> bool:
        """Check if sender is allowed. Empty list = deny all. Use [\"*\"] to allow everyone."""
        if not self._allow_from:
            return False
        if "*" in self._allow_from:
            return True
        return sender_id in self._allow_from

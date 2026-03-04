"""Base channel interface."""

from abc import ABC, abstractmethod

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
        """Check if sender is allowed. Empty list = allow all."""
        if not self._allow_from:
            return True
        return sender_id in self._allow_from

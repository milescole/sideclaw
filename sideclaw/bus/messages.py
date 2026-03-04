"""Inbound and outbound message types for the bus."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class InboundMessage:
    """Message received from a channel."""

    channel: str
    chat_id: str
    sender_id: str
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OutboundMessage:
    """Message to send back to a channel."""

    channel: str
    chat_id: str
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

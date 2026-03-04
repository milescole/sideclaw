import pytest

from sideclaw.bus.messages import InboundMessage, OutboundMessage
from sideclaw.bus.queue import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


async def test_inbound_publish_consume(bus: MessageBus):
    msg = InboundMessage(channel="cli", chat_id="user1", sender_id="user1", text="hello")
    await bus.publish_inbound(msg)
    received = await bus.consume_inbound()
    assert received.text == "hello"
    assert received.channel == "cli"


async def test_outbound_publish_consume(bus: MessageBus):
    msg = OutboundMessage(channel="cli", chat_id="user1", text="world")
    await bus.publish_outbound(msg)
    received = await bus.consume_outbound()
    assert received.text == "world"


async def test_inbound_message_has_only_required_fields():
    msg = InboundMessage(channel="telegram", chat_id="123", sender_id="456", text="hi")
    assert not hasattr(msg, "media")
    assert not hasattr(msg, "reply_to")
    assert hasattr(msg, "timestamp")


async def test_outbound_message_has_only_required_fields():
    msg = OutboundMessage(channel="cli", chat_id="user1", text="thinking...")
    assert not hasattr(msg, "progress")
    assert hasattr(msg, "timestamp")

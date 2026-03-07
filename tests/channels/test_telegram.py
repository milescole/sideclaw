from unittest.mock import AsyncMock

import pytest

from sideclaw.bus.messages import OutboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.channels.telegram import TelegramChannel


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def channel(bus: MessageBus) -> TelegramChannel:
    return TelegramChannel(bus=bus, token="fake:token", allow_from=[])


def test_channel_name(channel: TelegramChannel) -> None:
    assert channel._channel_name == "telegram"


def test_allow_from_empty_denies_all(channel: TelegramChannel) -> None:
    assert not channel.is_allowed("anyone")


def test_allow_from_wildcard_allows_all() -> None:
    bus = MessageBus()
    ch = TelegramChannel(bus=bus, token="fake:token", allow_from=["*"])
    assert ch.is_allowed("anyone")


def test_allow_from_restricts() -> None:
    bus = MessageBus()
    ch = TelegramChannel(bus=bus, token="fake:token", allow_from=["123"])
    assert ch.is_allowed("123")
    assert not ch.is_allowed("456")


async def test_send_calls_bot_api(channel: TelegramChannel) -> None:
    channel._bot = AsyncMock()
    msg = OutboundMessage(channel="telegram", chat_id="12345", text="Hello!")
    await channel.send(msg)
    channel._bot.send_message.assert_called_once_with(
        chat_id="12345", text="Hello!", parse_mode="Markdown"
    )


async def test_send_long_message_splits(channel: TelegramChannel) -> None:
    channel._bot = AsyncMock()
    long_text = "x" * 5000
    msg = OutboundMessage(channel="telegram", chat_id="12345", text=long_text)
    await channel.send(msg)
    assert channel._bot.send_message.call_count >= 2

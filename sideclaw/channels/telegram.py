"""Telegram channel using python-telegram-bot."""

from typing import Any

from loguru import logger
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from sideclaw.bus.messages import InboundMessage, OutboundMessage
from sideclaw.bus.queue import MessageBus
from sideclaw.channels.base import BaseChannel

TELEGRAM_MAX_LENGTH = 4096


class TelegramChannel(BaseChannel):
    """Telegram bot channel using long polling."""

    def __init__(
        self,
        bus: MessageBus,
        token: str,
        allow_from: list[str] | None = None,
    ) -> None:
        super().__init__(bus, "telegram", allow_from)
        self._token = token
        self._app: Application | None = None
        self._bot: Any = None

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        self._app = Application.builder().token(self._token).build()
        self._bot = self._app.bot

        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram channel started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to a Telegram chat."""
        if not self._bot:
            logger.error("Telegram bot not initialized")
            return

        text = msg.text
        chunks = self._split_message(text)
        for chunk in chunks:
            try:
                await self._bot.send_message(
                    chat_id=msg.chat_id,
                    text=chunk,
                    parse_mode="Markdown",
                )
            except TelegramError as e:
                logger.warning(f"Markdown send failed, retrying plain: {e}")
                try:
                    await self._bot.send_message(chat_id=msg.chat_id, text=chunk)
                except TelegramError as e2:
                    logger.error(f"Failed to send message: {e2}")

    async def _on_start(self, update: Update, _context: Any) -> None:
        """Handle /start command."""
        await update.message.reply_text("Hello! I'm a SideClaw assistant. Send me a message.")

    async def _on_new(self, update: Update, _context: Any) -> None:
        """Handle /new command to reset session."""
        chat_id = str(update.effective_chat.id)
        await self._bus.publish_inbound(
            InboundMessage(
                channel="telegram",
                chat_id=chat_id,
                sender_id=str(update.effective_user.id),
                text="/new",
            )
        )
        await update.message.reply_text("Session reset.")

    async def _on_message(self, update: Update, _context: Any) -> None:
        """Handle incoming text messages."""
        if not update.message or not update.message.text:
            return

        sender_id = str(update.effective_user.id)
        if not self.is_allowed(sender_id):
            logger.debug(f"Telegram: rejected message from {sender_id}")
            return

        chat_id = str(update.effective_chat.id)
        text = update.message.text

        logger.info(f"Telegram [{chat_id}]: {text[:50]}...")

        try:
            await update.effective_chat.send_action("typing")
        except TelegramError as e:
            logger.debug(f"Failed to send typing action: {e}")

        await self._bus.publish_inbound(
            InboundMessage(
                channel="telegram",
                chat_id=chat_id,
                sender_id=sender_id,
                text=text,
            )
        )

    @staticmethod
    def _split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
        """Split a message into chunks that fit Telegram's limit."""
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

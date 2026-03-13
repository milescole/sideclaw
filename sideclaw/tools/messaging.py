"""Cross-channel messaging tools."""

import json
import mimetypes
from pathlib import Path
from typing import Any

from sideclaw.config.schema import Config
from sideclaw.runtime.context import get_tool_runtime_context
from sideclaw.runtime.models.approval import ApprovalRequirement
from sideclaw.session.manager import SessionManager
from sideclaw.tools.base import Tool


def _classify_media_type(mime_type: str | None, *, suffix: str = "") -> str:
    """Map a MIME type to the Telegram send method family."""
    if suffix.lower() == ".ogg":
        return "voice"
    if not mime_type:
        return "file"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    return "file"


class SendMessageTool(Tool):
    """Send text or files to configured messaging channels."""

    def __init__(self, config: Config, session_manager: SessionManager) -> None:
        self._config = config
        self._session_manager = session_manager

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return (
            "Send a text message or local file to a configured messaging channel, "
            "or list known delivery targets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "list"],
                    "description": "List known targets or send a message/file.",
                },
                "target": {
                    "type": "string",
                    "description": (
                        "Delivery target in the format 'platform' or 'platform:chat_id'. "
                        "Bare platform names use the current chat when available."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "Text to send, or a caption when file_path is provided.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional local file path to send as an attachment.",
                },
            },
            "additionalProperties": False,
        }

    def approval_requirement(self, **kwargs: Any) -> ApprovalRequirement:
        if kwargs.get("action", "send") == "list":
            return ApprovalRequirement.never
        return ApprovalRequirement.always

    def approval_subject(self, **kwargs: Any) -> str:
        target = kwargs.get("target", "").strip() or "<missing target>"
        file_path = kwargs.get("file_path")
        message = (kwargs.get("message", "") or "").strip()
        if file_path:
            return f"{target} <= file {file_path}" + (f" ({message[:80]})" if message else "")
        return f"{target} <= {message[:120]}"

    def approval_action_type(self, **kwargs: Any) -> str:
        return "external_message_send"

    def approval_description(self, **kwargs: Any) -> str:
        if kwargs.get("action", "send") == "list":
            return "list messaging targets"
        if kwargs.get("file_path"):
            return "send external file"
        return "send external message"

    def display_arguments(self, **kwargs: Any) -> dict[str, Any] | None:
        payload = {"action": kwargs.get("action", "send"), "target": kwargs.get("target")}
        if kwargs.get("message"):
            payload["message"] = str(kwargs["message"])[:240]
        if kwargs.get("file_path"):
            payload["file_path"] = kwargs["file_path"]
        return payload

    async def execute(
        self,
        *,
        action: str = "send",
        target: str | None = None,
        message: str | None = None,
        file_path: str | None = None,
        **_: Any,
    ) -> str:
        if action == "list":
            return self._handle_list()
        if action != "send":
            return self._error(f"unknown action '{action}'")
        return await self._handle_send(
            target=target or "",
            message=(message or "").strip(),
            file_path=(file_path or "").strip(),
        )

    def _handle_list(self) -> str:
        configured_platforms: list[str] = []
        targets: list[dict[str, str]] = []

        if self._config.channels.telegram is not None:
            configured_platforms.append("telegram")
            for chat_id in self._known_chat_ids("telegram"):
                targets.append(
                    {
                        "platform": "telegram",
                        "chat_id": chat_id,
                        "target": f"telegram:{chat_id}",
                    }
                )

        context = get_tool_runtime_context()
        if context is not None and context.channel in configured_platforms:
            current_target = {
                "platform": context.channel,
                "chat_id": context.chat_id,
                "target": f"{context.channel}:{context.chat_id}",
                "current": "true",
            }
            if current_target not in targets:
                targets.insert(0, current_target)

        return json.dumps(
            {
                "platforms": configured_platforms,
                "targets": targets,
            },
            indent=2,
        )

    async def _handle_send(  # noqa: PLR0911
        self,
        *,
        target: str,
        message: str,
        file_path: str,
    ) -> str:
        if not target:
            return self._error("target is required for send")
        if not message and not file_path:
            return self._error("message or file_path is required for send")

        platform_name, chat_id = self._parse_target(target)
        if platform_name != "telegram":
            return self._error("only telegram is supported right now")
        if self._config.channels.telegram is None:
            return self._error("telegram is not configured")

        resolved_chat_id = self._resolve_chat_id(platform_name, chat_id)
        if resolved_chat_id is None:
            return self._error(
                "could not resolve chat_id for target; use send_message(action='list') first"
            )

        if file_path:
            return await self._send_telegram_file(
                token=self._config.channels.telegram.token,
                chat_id=resolved_chat_id,
                file_path=file_path,
                caption=message or None,
            )
        return await self._send_telegram_text(
            token=self._config.channels.telegram.token,
            chat_id=resolved_chat_id,
            text=message,
        )

    def _parse_target(self, target: str) -> tuple[str, str | None]:
        parts = target.split(":", 1)
        platform_name = parts[0].strip().lower()
        chat_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        return platform_name, chat_id

    def _resolve_chat_id(self, platform_name: str, chat_id: str | None) -> str | None:
        if chat_id:
            return chat_id

        context = get_tool_runtime_context()
        if context is not None and context.channel == platform_name:
            return context.chat_id

        known = self._known_chat_ids(platform_name)
        if len(known) == 1:
            return known[0]
        return None

    def _known_chat_ids(self, platform_name: str) -> list[str]:
        chat_ids: set[str] = set()
        for session in self._session_manager.list_sessions():
            key = str(session.get("key", ""))
            if not key.startswith(f"{platform_name}:"):
                continue
            _, chat_id = key.split(":", 1)
            if chat_id:
                chat_ids.add(chat_id)
        return sorted(chat_ids)

    async def _send_telegram_text(self, *, token: str, chat_id: str, text: str) -> str:
        try:
            from telegram import Bot

            bot = Bot(token=token)
            result = await bot.send_message(chat_id=int(chat_id), text=text)
        except ImportError:
            return self._error("python-telegram-bot is not installed")
        except Exception as exc:  # noqa: BLE001
            return self._error(f"telegram send failed: {exc}")

        return json.dumps(
            {
                "success": True,
                "platform": "telegram",
                "chat_id": chat_id,
                "message_id": str(result.message_id),
                "kind": "text",
            },
            indent=2,
        )

    async def _send_telegram_file(
        self,
        *,
        token: str,
        chat_id: str,
        file_path: str,
        caption: str | None,
    ) -> str:
        path = Path(file_path).expanduser()  # noqa: ASYNC240
        if not path.exists():
            return self._error(f"file does not exist: {file_path}")
        if not path.is_file():
            return self._error(f"path is not a file: {file_path}")

        mime_type, _encoding = mimetypes.guess_type(path.name)
        media_type = _classify_media_type(mime_type, suffix=path.suffix)

        try:
            from telegram import Bot

            bot = Bot(token=token)
            with path.open("rb") as handle:
                if media_type == "image":
                    result = await bot.send_photo(
                        chat_id=int(chat_id),
                        photo=handle,
                        caption=caption,
                    )
                elif media_type == "audio":
                    result = await bot.send_audio(
                        chat_id=int(chat_id),
                        audio=handle,
                        caption=caption,
                    )
                elif media_type == "voice":
                    result = await bot.send_voice(
                        chat_id=int(chat_id),
                        voice=handle,
                        caption=caption,
                    )
                elif media_type == "video":
                    result = await bot.send_video(
                        chat_id=int(chat_id),
                        video=handle,
                        caption=caption,
                    )
                else:
                    result = await bot.send_document(
                        chat_id=int(chat_id),
                        document=handle,
                        caption=caption,
                        filename=path.name,
                    )
        except ImportError:
            return self._error("python-telegram-bot is not installed")
        except Exception as exc:  # noqa: BLE001
            return self._error(f"telegram file send failed: {exc}")

        return json.dumps(
            {
                "success": True,
                "platform": "telegram",
                "chat_id": chat_id,
                "message_id": str(result.message_id),
                "kind": media_type,
                "filename": path.name,
            },
            indent=2,
        )

    @staticmethod
    def _error(message: str) -> str:
        return json.dumps({"success": False, "error": message}, indent=2)

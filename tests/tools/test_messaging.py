import json
from pathlib import Path
from types import SimpleNamespace

from sideclaw.config.schema import (
    AgentConfig,
    ChannelsConfig,
    Config,
    OpenRouterConfig,
    ProvidersConfig,
    TelegramConfig,
)
from sideclaw.runtime.context import (
    ToolRuntimeContext,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)
from sideclaw.session.manager import SessionManager
from sideclaw.tools.messaging import SendMessageTool


class _FakeBot:
    def __init__(self, token: str) -> None:
        self.token = token

    async def send_message(self, *, chat_id: int, text: str):
        assert chat_id == 123
        assert text == "hello from sideclaw"
        return SimpleNamespace(message_id=41)

    async def send_photo(self, *, chat_id: int, photo, caption: str | None):
        assert chat_id == 123
        assert caption == "caption"
        assert getattr(photo, "read", None) is not None
        return SimpleNamespace(message_id=42)

    async def send_voice(self, *, chat_id: int, voice, caption: str | None):
        assert chat_id == 123
        assert caption == "voice caption"
        assert getattr(voice, "read", None) is not None
        return SimpleNamespace(message_id=43)


def _config(workspace: Path) -> Config:
    return Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        channels=ChannelsConfig(
            telegram=TelegramConfig(token="123:telegram-token", allow_from=["*"]),
            send_progress=True,
            send_tool_hints=True,
        ),
    )


async def test_send_message_lists_known_targets(tmp_path) -> None:
    manager = SessionManager(tmp_path / "sessions")
    manager.save(manager.get_or_create("telegram:123"))
    tool = SendMessageTool(_config(tmp_path), manager)

    result = await tool.execute(action="list")

    parsed = json.loads(result)
    assert parsed["platforms"] == ["telegram"]
    assert parsed["targets"][0]["target"] == "telegram:123"


async def test_send_message_sends_text_to_current_chat(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("telegram.Bot", _FakeBot)
    manager = SessionManager(tmp_path / "sessions")
    tool = SendMessageTool(_config(tmp_path), manager)
    token = set_tool_runtime_context(
        ToolRuntimeContext(
            channel="telegram",
            chat_id="123",
            sender_id="77",
            session_key="telegram:123",
        )
    )

    try:
        result = await tool.execute(
            action="send",
            target="telegram",
            message="hello from sideclaw",
        )
    finally:
        reset_tool_runtime_context(token)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["kind"] == "text"


async def test_send_message_sends_photo(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("telegram.Bot", _FakeBot)
    manager = SessionManager(tmp_path / "sessions")
    tool = SendMessageTool(_config(tmp_path), manager)
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"fakepng")

    result = await tool.execute(
        action="send",
        target="telegram:123",
        file_path=str(photo),
        message="caption",
    )

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["kind"] == "image"
    assert parsed["filename"] == "photo.png"


async def test_send_message_sends_ogg_as_voice(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("telegram.Bot", _FakeBot)
    manager = SessionManager(tmp_path / "sessions")
    tool = SendMessageTool(_config(tmp_path), manager)
    voice = tmp_path / "voice.ogg"
    voice.write_bytes(b"fakeogg")

    result = await tool.execute(
        action="send",
        target="telegram:123",
        file_path=str(voice),
        message="voice caption",
    )

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["kind"] == "voice"
    assert parsed["filename"] == "voice.ogg"

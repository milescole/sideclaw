import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from sideclaw.config.schema import TTSConfig
from sideclaw.runtime.context import (
    ToolRuntimeContext,
    reset_tool_runtime_context,
    set_tool_runtime_context,
)
from sideclaw.tools.tts import TextToSpeechTool


class _FakeCommunicate:
    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def save(self, output_path: str) -> None:
        await asyncio.to_thread(Path(output_path).write_bytes, b"mp3-bytes")


async def test_text_to_speech_generates_edge_audio(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(
        sys.modules,
        "edge_tts",
        SimpleNamespace(Communicate=_FakeCommunicate),
    )
    tool = TextToSpeechTool(tmp_path, TTSConfig(enabled=True, provider="edge"))

    result = await tool.execute(text="hello world")

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert await asyncio.to_thread(Path(parsed["file_path"]).exists)
    assert parsed["provider"] == "edge"


async def test_text_to_speech_prefers_ogg_for_telegram_openai(monkeypatch, tmp_path) -> None:
    class _FakeSpeech:
        def create(self, **kwargs):
            assert kwargs["response_format"] == "opus"
            return SimpleNamespace(stream_to_file=lambda path: Path(path).write_bytes(b"ogg-bytes"))

    class _FakeAudio:
        speech = _FakeSpeech()

    class _FakeOpenAI:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.audio = _FakeAudio()

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=_FakeOpenAI),
    )
    monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "voice-key")
    tool = TextToSpeechTool(tmp_path, TTSConfig(enabled=True, provider="openai"))
    token = set_tool_runtime_context(
        ToolRuntimeContext(
            channel="telegram",
            chat_id="123",
            sender_id="123",
            session_key="telegram:123",
        )
    )

    try:
        result = await tool.execute(text="hello telegram")
    finally:
        reset_tool_runtime_context(token)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["file_path"].endswith(".ogg")
    assert parsed["voice_compatible"] is True


async def test_text_to_speech_generates_elevenlabs_audio_via_httpx(
    monkeypatch,
    tmp_path,
) -> None:
    recorded: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"ogg"
            yield b"-bytes"

    class _FakeClient:
        def __init__(self, *, base_url: str, timeout: float) -> None:
            recorded["base_url"] = base_url
            recorded["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, *, params, headers, json):
            recorded["method"] = method
            recorded["url"] = url
            recorded["params"] = params
            recorded["headers"] = headers
            recorded["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("sideclaw.tools.tts.httpx.Client", _FakeClient)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "voice-key")
    tool = TextToSpeechTool(tmp_path, TTSConfig(enabled=True, provider="elevenlabs"))
    token = set_tool_runtime_context(
        ToolRuntimeContext(
            channel="telegram",
            chat_id="123",
            sender_id="123",
            session_key="telegram:123",
        )
    )

    try:
        result = await tool.execute(text="hello telegram")
    finally:
        reset_tool_runtime_context(token)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["file_path"].endswith(".ogg")
    assert parsed["voice_compatible"] is True
    assert Path(parsed["file_path"]).read_bytes() == b"ogg-bytes"
    assert recorded["base_url"] == "https://api.elevenlabs.io"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL/stream"
    assert recorded["params"] == {"output_format": "opus_48000_64"}
    assert recorded["headers"] == {
        "xi-api-key": "voice-key",
        "accept": "application/octet-stream",
    }
    assert recorded["json"] == {
        "text": "hello telegram",
        "model_id": "eleven_flash_v2_5",
    }


async def test_text_to_speech_uses_configured_elevenlabs_api_key(
    monkeypatch,
    tmp_path,
) -> None:
    recorded: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"mp3-bytes"

    class _FakeClient:
        def __init__(self, *, base_url: str, timeout: float) -> None:
            recorded["base_url"] = base_url
            recorded["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, *, params, headers, json):
            recorded["method"] = method
            recorded["url"] = url
            recorded["params"] = params
            recorded["headers"] = headers
            recorded["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("sideclaw.tools.tts.httpx.Client", _FakeClient)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    tool = TextToSpeechTool(
        tmp_path,
        TTSConfig(
            enabled=True,
            provider="elevenlabs",
            elevenlabs_api_key="config-voice-key",
        ),
    )

    result = await tool.execute(text="hello world")

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["file_path"].endswith(".mp3")
    assert parsed["voice_compatible"] is False
    assert recorded["headers"] == {
        "xi-api-key": "config-voice-key",
        "accept": "application/octet-stream",
    }

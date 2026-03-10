"""Text-to-speech tool."""

import asyncio
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from sideclaw.config.schema import TTSConfig
from sideclaw.runtime.context import get_tool_runtime_context
from sideclaw.tools.base import Tool

DEFAULT_ELEVENLABS_API_ENV = "ELEVENLABS_API_KEY"
DEFAULT_OPENAI_API_ENV = "VOICE_TOOLS_OPENAI_KEY"


class TextToSpeechTool(Tool):
    """Generate speech audio from text using the configured provider."""

    def __init__(self, workspace: Path, config: TTSConfig) -> None:
        self._workspace = Path(workspace)
        self._config = config

    @property
    def name(self) -> str:
        return "text_to_speech"

    @property
    def description(self) -> str:
        return (
            "Convert text to speech audio using the configured provider and "
            "save it as a local artifact."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to convert to speech.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional custom output path for the generated audio file.",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        text = str(kwargs["text"]).strip()
        if not text:
            return self._error("text is required")

        truncated = text[: self._config.max_text_length]
        provider = self._config.provider.lower().strip()
        output_path = self._resolve_output_path(
            kwargs.get("output_path"),
            provider=provider,
            channel=(get_tool_runtime_context().channel if get_tool_runtime_context() else ""),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if provider == "elevenlabs":
                await asyncio.to_thread(self._generate_elevenlabs, truncated, output_path)
            elif provider == "openai":
                await asyncio.to_thread(self._generate_openai, truncated, output_path)
            else:
                await self._generate_edge(truncated, output_path)
        except ImportError as exc:
            return self._error(str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

        final_path = output_path
        voice_compatible = output_path.suffix == ".ogg"
        if provider == "edge" and output_path.suffix == ".mp3":
            opus_path = self._convert_to_opus(output_path)
            if opus_path is not None:
                final_path = opus_path
                voice_compatible = True

        if not final_path.exists() or final_path.stat().st_size == 0:
            return self._error("tts generation produced no output")

        media_tag = f"MEDIA:{final_path}"
        if voice_compatible:
            media_tag = f"[[audio_as_voice]]\n{media_tag}"

        return json.dumps(
            {
                "success": True,
                "file_path": str(final_path),
                "media_tag": media_tag,
                "provider": provider,
                "voice_compatible": voice_compatible,
            },
            indent=2,
        )

    def _resolve_output_path(self, raw_path: str | None, *, provider: str, channel: str) -> Path:
        if raw_path:
            return Path(raw_path).expanduser()
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        extension = (
            ".ogg" if channel == "telegram" and provider in {"openai", "elevenlabs"} else ".mp3"
        )
        return self._workspace / "artifacts" / "media" / f"tts_{timestamp}{extension}"

    async def _generate_edge(self, text: str, output_path: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - import guard
            msg = "edge-tts is not installed"
            raise ImportError(msg) from exc
        communicate = edge_tts.Communicate(text, self._config.edge_voice)
        await communicate.save(str(output_path))

    def _generate_elevenlabs(self, text: str, output_path: Path) -> None:
        api_key = (
            os.getenv(DEFAULT_ELEVENLABS_API_ENV, "").strip()
            or (self._config.elevenlabs_api_key or "").strip()
        )
        if not api_key:
            msg = f"{DEFAULT_ELEVENLABS_API_ENV} is not set"
            raise ValueError(msg)
        output_format = "opus_48000_64" if output_path.suffix == ".ogg" else "mp3_44100_128"
        payload = {
            "text": text,
            "model_id": self._config.elevenlabs_model_id,
        }
        headers = {
            "xi-api-key": api_key,
            "accept": "application/octet-stream",
        }
        with httpx.Client(base_url="https://api.elevenlabs.io", timeout=60.0) as client:
            with client.stream(
                "POST",
                f"/v1/text-to-speech/{self._config.elevenlabs_voice_id}/stream",
                params={"output_format": output_format},
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                with output_path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        if chunk:
                            handle.write(chunk)

    def _generate_openai(self, text: str, output_path: Path) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - import guard
            msg = "openai is not installed"
            raise ImportError(msg) from exc

        api_key = os.getenv(DEFAULT_OPENAI_API_ENV, "").strip()
        if not api_key:
            msg = f"{DEFAULT_OPENAI_API_ENV} is not set"
            raise ValueError(msg)
        response_format = "opus" if output_path.suffix == ".ogg" else "mp3"
        client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")
        response = client.audio.speech.create(
            model=self._config.openai_model,
            voice=self._config.openai_voice,
            input=text,
            response_format=response_format,
        )
        response.stream_to_file(output_path)

    @staticmethod
    def _convert_to_opus(mp3_path: Path) -> Path | None:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            return None
        ogg_path = mp3_path.with_suffix(".ogg")
        try:
            subprocess.run(  # noqa: S603
                [
                    ffmpeg_path,
                    "-i",
                    str(mp3_path),
                    "-acodec",
                    "libopus",
                    "-ac",
                    "1",
                    "-b:a",
                    "64k",
                    "-vbr",
                    "off",
                    str(ogg_path),
                    "-y",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if ogg_path.exists() and ogg_path.stat().st_size > 0:
            return ogg_path
        return None

    @staticmethod
    def _error(message: str) -> str:
        return json.dumps({"success": False, "error": message}, indent=2)

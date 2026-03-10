import json
import sys
from types import SimpleNamespace
from typing import ClassVar

from sideclaw.tools.image import ImageGenerationTool, UpscalingConfig, normalize_fal_model_id


class _FakeSyncClient:
    subscribe_calls: ClassVar[list[dict[str, object]]] = []
    subscribe_results: ClassVar[list[object]] = []

    def __init__(self, *, key, default_timeout) -> None:
        self.key = key
        self.default_timeout = default_timeout

    def subscribe(self, application, *, arguments, client_timeout):
        type(self).subscribe_calls.append(
            {
                "application": application,
                "arguments": arguments,
                "client_timeout": client_timeout,
            }
        )
        result = type(self).subscribe_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @classmethod
    def reset(cls) -> None:
        cls.subscribe_calls = []
        cls.subscribe_results = []


async def test_image_generation_tool_uses_flux_profile_and_upscaling(monkeypatch) -> None:
    _FakeSyncClient.reset()
    _FakeSyncClient.subscribe_results = [
        {
            "images": [
                {"url": "https://example.com/banana-1.png", "width": 1024, "height": 1024},
                {"url": "https://example.com/banana-2.png", "width": 1024, "height": 1024},
            ]
        },
        {"image": {"url": "https://example.com/upscaled-1.png", "width": 2048, "height": 2048}},
        {"image": {"url": "https://example.com/upscaled-2.png", "width": 2048, "height": 2048}},
    ]
    monkeypatch.setitem(sys.modules, "fal_client", SimpleNamespace(SyncClient=_FakeSyncClient))
    tool = ImageGenerationTool(
        api_key="fal_test_key",
        model_id="fal-ai/flux-pro/v1.1",
        upscaling=UpscalingConfig(
            enabled=True,
            model_id="fal-ai/clarity-upscaler",
        ),
    )

    result = await tool.execute(
        prompt="A yellow banana astronaut",
        aspect_ratio="1:1",
        num_images=2,
        seed=7,
        num_inference_steps=30,
        guidance_scale=5.5,
        output_format="jpeg",
    )

    parsed = json.loads(result)
    generate_call = _FakeSyncClient.subscribe_calls[0]
    assert generate_call["application"] == "fal-ai/flux-pro/v1.1"
    assert generate_call["arguments"] == {
        "prompt": "A yellow banana astronaut",
        "image_size": "square_hd",
        "num_inference_steps": 30,
        "guidance_scale": 5.5,
        "num_images": 2,
        "output_format": "jpeg",
        "enable_safety_checker": True,
        "sync_mode": True,
        "seed": 7,
    }
    assert parsed["success"] is True
    assert parsed["profile"] == "flux"
    assert parsed["image"] == "https://example.com/upscaled-1.png"
    assert parsed["upscaled_images"] == 2
    assert parsed["images"][0]["original_url"] == "https://example.com/banana-1.png"
    assert parsed["warnings"] == []


async def test_image_generation_tool_uses_nano_banana_2_profile(monkeypatch) -> None:
    _FakeSyncClient.reset()
    _FakeSyncClient.subscribe_results = [
        {
            "images": [
                {"url": "https://example.com/banana-1.png", "width": 1024, "height": 1024},
            ]
        }
    ]
    monkeypatch.setitem(sys.modules, "fal_client", SimpleNamespace(SyncClient=_FakeSyncClient))
    tool = ImageGenerationTool(api_key="fal_test_key", model_id="nano-banana-2")

    result = await tool.execute(
        prompt="A yellow banana astronaut",
        aspect_ratio="square",
        resolution="2K",
        num_images=1,
        seed=7,
        enable_web_search=True,
        output_format="webp",
    )

    parsed = json.loads(result)
    generate_call = _FakeSyncClient.subscribe_calls[0]
    assert generate_call["application"] == "fal-ai/nano-banana-2"
    assert generate_call["arguments"] == {
        "prompt": "A yellow banana astronaut",
        "aspect_ratio": "1:1",
        "resolution": "2K",
        "num_images": 1,
        "seed": 7,
        "output_format": "webp",
        "enable_web_search": True,
    }
    assert parsed["success"] is True
    assert parsed["profile"] == "nano_banana"
    assert parsed["images"][0]["upscaled"] is False


def test_normalize_fal_model_id_accepts_shorthand_aliases() -> None:
    assert normalize_fal_model_id("nano-banana-2") == "fal-ai/nano-banana-2"
    assert normalize_fal_model_id("nano-banana") == "fal-ai/nano-banana"
    assert normalize_fal_model_id("fal-ai/flux-pro/v1.1") == "fal-ai/flux-pro/v1.1"


async def test_image_generation_tool_generic_profile_only_forwards_explicit_options(
    monkeypatch,
) -> None:
    _FakeSyncClient.reset()
    _FakeSyncClient.subscribe_results = [
        {
            "data": [
                {
                    "image": {
                        "url": "https://example.com/custom.png",
                        "width": 800,
                        "height": 600,
                    }
                }
            ]
        }
    ]
    monkeypatch.setitem(sys.modules, "fal_client", SimpleNamespace(SyncClient=_FakeSyncClient))
    tool = ImageGenerationTool(api_key="fal_test_key", model_id="fal-ai/custom-model")

    result = await tool.execute(
        prompt="A custom banana",
        image_size={"width": 800, "height": 600},
        output_format="png",
    )

    parsed = json.loads(result)
    generate_call = _FakeSyncClient.subscribe_calls[0]
    assert generate_call["arguments"] == {
        "prompt": "A custom banana",
        "image_size": {"width": 800, "height": 600},
        "output_format": "png",
    }
    assert parsed["success"] is True
    assert parsed["profile"] == "generic"
    assert parsed["image"] == "https://example.com/custom.png"


async def test_image_generation_tool_falls_back_when_upscaler_fails(monkeypatch) -> None:
    _FakeSyncClient.reset()
    _FakeSyncClient.subscribe_results = [
        {"images": [{"url": "https://example.com/base.png", "width": 1024, "height": 1024}]},
        RuntimeError("upscale failed"),
    ]
    monkeypatch.setitem(sys.modules, "fal_client", SimpleNamespace(SyncClient=_FakeSyncClient))
    tool = ImageGenerationTool(
        api_key="fal_test_key",
        model_id="fal-ai/flux-pro/v1.1",
        upscaling=UpscalingConfig(model_id="fal-ai/clarity-upscaler"),
    )

    result = await tool.execute(
        prompt="A fallback banana",
        aspect_ratio="landscape",
        upscale=True,
    )

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["image"] == "https://example.com/base.png"
    assert parsed["images"][0]["upscaled"] is False
    assert parsed["warnings"] == [
        "upscaling failed for 1 image(s); original image URLs were returned"
    ]


async def test_image_generation_tool_rejects_invalid_resolution() -> None:
    tool = ImageGenerationTool(api_key="fal_test_key")

    result = await tool.execute(
        prompt="A yellow banana astronaut",
        resolution="8K",
    )

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "resolution must be one of" in parsed["error"]


async def test_image_generation_tool_reports_missing_client(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "fal_client", raising=False)
    tool = ImageGenerationTool(api_key="fal_test_key")

    real_import = __import__

    def _raising_import(name, *args, **kwargs):
        if name == "fal_client":
            msg = "No module named 'fal_client'"
            raise ImportError(msg)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raising_import)

    result = await tool.execute(prompt="A yellow banana astronaut")

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert parsed["error"] == "fal-client is not installed"

"""Image generation tools."""

import asyncio
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from loguru import logger

from sideclaw.tools.base import Tool

DEFAULT_FAL_MODEL = "fal-ai/nano-banana-2"
DEFAULT_FAL_UPSCALER_MODEL = "fal-ai/clarity-upscaler"
DEFAULT_ASPECT_RATIO = "auto"
DEFAULT_RESOLUTION = "1K"
DEFAULT_IMAGE_SIZE = "landscape_16_9"
DEFAULT_NUM_IMAGES = 1
DEFAULT_NUM_INFERENCE_STEPS = 28
DEFAULT_GUIDANCE_SCALE = 4.0
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_CLIENT_TIMEOUT = 180.0
DEFAULT_UPSCALE_FACTOR = 2

VALID_ASPECT_RATIOS = [
    "auto",
    "landscape",
    "square",
    "portrait",
    "8:1",
    "21:9",
    "16:9",
    "4:1",
    "3:2",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "2:3",
    "1:4",
    "9:16",
    "1:8",
]
VALID_RESOLUTIONS = ["0.5K", "1K", "2K", "4K"]
VALID_OUTPUT_FORMATS = ["jpeg", "png", "webp"]
VALID_IMAGE_SIZES = [
    "square_hd",
    "square",
    "portrait_4_3",
    "portrait_16_9",
    "landscape_4_3",
    "landscape_16_9",
]
ASPECT_RATIO_ALIASES = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
}
FLUX_IMAGE_SIZE_BY_ASPECT = {
    "auto": DEFAULT_IMAGE_SIZE,
    "landscape": "landscape_16_9",
    "16:9": "landscape_16_9",
    "4:3": "landscape_4_3",
    "square": "square_hd",
    "1:1": "square_hd",
    "portrait": "portrait_16_9",
    "9:16": "portrait_16_9",
    "3:4": "portrait_4_3",
}

FAL_MODEL_ALIASES = {
    "nano-banana": "fal-ai/nano-banana",
    "nano-banana-2": "fal-ai/nano-banana-2",
}


class ImageModelProfile(StrEnum):
    """Supported request-shaping strategies for fal image models."""

    nano_banana = "nano_banana"
    flux = "flux"
    generic = "generic"


@dataclass(frozen=True)
class ImageSize:
    """Custom image size for models that accept explicit dimensions."""

    width: int
    height: int

    def as_payload(self) -> dict[str, int]:
        return {"width": self.width, "height": self.height}


@dataclass(frozen=True)
class NormalizedImageRequest:
    """Validated tool input independent of the target model family."""

    prompt: str
    aspect_ratio: str
    resolution: str
    num_images: int
    seed: int | None
    image_size: str | ImageSize | None
    num_inference_steps: int
    guidance_scale: float
    output_format: str
    enable_web_search: bool
    enable_safety_checker: bool
    upscale: bool
    provided_fields: frozenset[str]


@dataclass(frozen=True)
class UpscalingConfig:
    """Config for optional post-generation upscaling."""

    enabled: bool = False
    model_id: str | None = None
    factor: int = DEFAULT_UPSCALE_FACTOR


def normalize_fal_model_id(model_id: str) -> str:
    """Resolve common shorthand fal model names to canonical app identifiers."""

    normalized = model_id.strip()
    if not normalized:
        return DEFAULT_FAL_MODEL
    return FAL_MODEL_ALIASES.get(normalized, normalized)


class ImageGenerationTool(Tool):
    """Generate images with the configured fal.ai model."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = DEFAULT_FAL_MODEL,
        client_timeout: float = DEFAULT_CLIENT_TIMEOUT,
        upscaling: UpscalingConfig | None = None,
    ) -> None:
        upscaling = upscaling or UpscalingConfig()
        if client_timeout <= 0:
            msg = "client_timeout must be greater than 0"
            raise ValueError(msg)
        if upscaling.factor < 1:
            msg = "upscale_factor must be at least 1"
            raise ValueError(msg)
        self._api_key = api_key
        self._model_id = normalize_fal_model_id(model_id)
        self._client_timeout = client_timeout
        self._default_upscale = upscaling.enabled
        self._upscaler_model = (upscaling.model_id or "").strip() or None
        self._upscale_factor = upscaling.factor

    @property
    def name(self) -> str:
        return "image_generation"

    @property
    def description(self) -> str:
        return (
            "Generate images from a text prompt using the configured fal.ai image model. "
            "Supports optional advanced controls such as aspect ratio, image size, "
            "quality settings, and post-generation upscaling when configured."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text prompt describing the desired image.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": VALID_ASPECT_RATIOS,
                    "description": (
                        "Target aspect ratio. Friendly values like 'landscape', 'square', "
                        "and 'portrait' are normalized for supported models."
                    ),
                    "default": DEFAULT_ASPECT_RATIO,
                },
                "image_size": {
                    "description": (
                        "Optional explicit image size preset or custom dimensions for "
                        "models that support it."
                    ),
                    "anyOf": [
                        {
                            "type": "string",
                            "enum": VALID_IMAGE_SIZES,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "width": {
                                    "type": "integer",
                                    "minimum": 64,
                                    "maximum": 2048,
                                },
                                "height": {
                                    "type": "integer",
                                    "minimum": 64,
                                    "maximum": 2048,
                                },
                            },
                            "required": ["width", "height"],
                            "additionalProperties": False,
                        },
                    ],
                },
                "resolution": {
                    "type": "string",
                    "enum": VALID_RESOLUTIONS,
                    "description": "Output resolution tier for models that support it.",
                    "default": DEFAULT_RESOLUTION,
                },
                "num_images": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "description": "Number of images to generate.",
                    "default": DEFAULT_NUM_IMAGES,
                },
                "seed": {
                    "type": "integer",
                    "description": "Optional random seed for reproducible results.",
                },
                "num_inference_steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Sampling steps for models that expose them.",
                    "default": DEFAULT_NUM_INFERENCE_STEPS,
                },
                "guidance_scale": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 20.0,
                    "description": "Prompt guidance strength for models that expose it.",
                    "default": DEFAULT_GUIDANCE_SCALE,
                },
                "output_format": {
                    "type": "string",
                    "enum": VALID_OUTPUT_FORMATS,
                    "description": "Preferred image format for models that support it.",
                    "default": DEFAULT_OUTPUT_FORMAT,
                },
                "enable_web_search": {
                    "type": "boolean",
                    "description": "Allow the model to use web search context when supported.",
                    "default": False,
                },
                "enable_safety_checker": {
                    "type": "boolean",
                    "description": "Enable fal.ai safety filtering when supported.",
                    "default": True,
                },
                "upscale": {
                    "type": "boolean",
                    "description": "Apply configured fal.ai upscaling after generation.",
                    "default": False,
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        try:
            request = self._normalize_request(kwargs)
        except (TypeError, ValueError) as exc:
            return self._error(str(exc))

        try:
            response = await asyncio.to_thread(self._generate_sync, request)
        except ImportError:
            return self._error("fal-client is not installed")
        except Exception as exc:  # noqa: BLE001
            logger.exception("image generation failed")
            return self._error(str(exc))

        return json.dumps(response, indent=2)

    def _generate_sync(self, request: NormalizedImageRequest) -> dict[str, Any]:
        import fal_client

        profile = self._detect_profile(self._model_id)
        client = fal_client.SyncClient(key=self._api_key, default_timeout=self._client_timeout)
        arguments = self._build_arguments(request, profile)

        logger.info(
            "Generating {} image(s) with model '{}' using profile '{}'",
            request.num_images,
            self._model_id,
            profile.value,
        )
        result = client.subscribe(
            self._model_id,
            arguments=arguments,
            client_timeout=self._client_timeout,
        )
        images = self._extract_images(result)
        if not images:
            msg = "fal.ai returned no images"
            raise ValueError(msg)

        warnings: list[str] = []
        processed_images = self._apply_optional_upscaling(
            client,
            images,
            request,
            warnings=warnings,
        )

        return {
            "success": True,
            "model": self._model_id,
            "profile": profile.value,
            "image": processed_images[0]["url"],
            "images": processed_images,
            "upscaled_images": sum(1 for image in processed_images if image.get("upscaled")),
            "warnings": warnings,
        }

    def _build_arguments(
        self,
        request: NormalizedImageRequest,
        profile: ImageModelProfile,
    ) -> dict[str, Any]:
        if profile == ImageModelProfile.nano_banana:
            return self._build_nano_banana_arguments(request)
        if profile == ImageModelProfile.flux:
            return self._build_flux_arguments(request)
        return self._build_generic_arguments(request)

    def _build_nano_banana_arguments(self, request: NormalizedImageRequest) -> dict[str, Any]:
        if request.image_size is not None:
            msg = "image_size is not supported by the configured Nano Banana model"
            raise ValueError(msg)

        arguments: dict[str, Any] = {
            "prompt": request.prompt,
            "aspect_ratio": self._normalize_nano_banana_aspect_ratio(request.aspect_ratio),
            "resolution": request.resolution,
            "num_images": request.num_images,
            "output_format": request.output_format,
            "enable_web_search": request.enable_web_search,
        }
        if request.seed is not None:
            arguments["seed"] = request.seed
        return arguments

    def _build_flux_arguments(self, request: NormalizedImageRequest) -> dict[str, Any]:
        image_size = self._resolve_flux_image_size(request)
        arguments: dict[str, Any] = {
            "prompt": request.prompt,
            "image_size": image_size,
            "num_inference_steps": request.num_inference_steps,
            "guidance_scale": request.guidance_scale,
            "num_images": request.num_images,
            "output_format": request.output_format,
            "enable_safety_checker": request.enable_safety_checker,
            "sync_mode": True,
        }
        if request.seed is not None:
            arguments["seed"] = request.seed
        return arguments

    def _build_generic_arguments(self, request: NormalizedImageRequest) -> dict[str, Any]:
        arguments: dict[str, Any] = {"prompt": request.prompt}

        explicit_builders: dict[str, Any] = {
            "aspect_ratio": lambda: self._normalize_generic_aspect_ratio(request.aspect_ratio),
            "resolution": lambda: request.resolution,
            "num_images": lambda: request.num_images,
            "seed": lambda: request.seed,
            "image_size": lambda: (
                request.image_size.as_payload()
                if isinstance(request.image_size, ImageSize)
                else request.image_size
            ),
            "num_inference_steps": lambda: request.num_inference_steps,
            "guidance_scale": lambda: request.guidance_scale,
            "output_format": lambda: request.output_format,
            "enable_web_search": lambda: request.enable_web_search,
            "enable_safety_checker": lambda: request.enable_safety_checker,
        }

        for field_name, builder in explicit_builders.items():
            if field_name not in request.provided_fields:
                continue
            value = builder()
            if value is not None:
                arguments[field_name] = value
        return arguments

    def _apply_optional_upscaling(
        self,
        client: Any,
        images: list[dict[str, Any]],
        request: NormalizedImageRequest,
        *,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if not request.upscale:
            return [self._with_upscale_flag(image, upscaled=False) for image in images]
        if self._upscaler_model is None:
            warnings.append("upscale requested but no upscaler model is configured")
            return [self._with_upscale_flag(image, upscaled=False) for image in images]

        processed: list[dict[str, Any]] = []
        failed = 0
        for image in images:
            upscaled = self._upscale_image(client, image["url"])
            if upscaled is None:
                processed.append(self._with_upscale_flag(image, upscaled=False))
                failed += 1
                continue
            processed.append(
                {
                    **upscaled,
                    "original_url": image["url"],
                    "upscaled": True,
                }
            )

        if failed:
            warnings.append(
                f"upscaling failed for {failed} image(s); original image URLs were returned"
            )
        return processed

    def _upscale_image(self, client: Any, image_url: str) -> dict[str, Any] | None:
        if self._upscaler_model is None:
            return None

        try:
            result = client.subscribe(
                self._upscaler_model,
                arguments={
                    "image_url": image_url,
                    "upscale_factor": self._upscale_factor,
                },
                client_timeout=self._client_timeout,
            )
        except Exception:  # noqa: BLE001
            logger.warning("image upscaling failed for {}", image_url)
            return None

        images = self._extract_images(result)
        if not images:
            return None
        return images[0]

    @staticmethod
    def _with_upscale_flag(
        image: dict[str, Any],
        *,
        upscaled: bool,
    ) -> dict[str, Any]:
        return {**image, "upscaled": upscaled}

    @staticmethod
    def _detect_profile(model_id: str) -> ImageModelProfile:
        model_name = model_id.lower()
        if "nano-banana" in model_name:
            return ImageModelProfile.nano_banana
        if "flux" in model_name:
            return ImageModelProfile.flux
        return ImageModelProfile.generic

    def _normalize_request(self, raw: dict[str, Any]) -> NormalizedImageRequest:
        prompt = str(raw.get("prompt", "")).strip()
        if not prompt:
            msg = "prompt is required"
            raise ValueError(msg)

        return NormalizedImageRequest(
            prompt=prompt,
            aspect_ratio=ImageGenerationTool._normalize_aspect_ratio(
                raw.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
            ),
            resolution=ImageGenerationTool._normalize_resolution(
                raw.get("resolution", DEFAULT_RESOLUTION)
            ),
            num_images=ImageGenerationTool._normalize_int(
                raw.get("num_images", DEFAULT_NUM_IMAGES),
                field_name="num_images",
                minimum=1,
                maximum=4,
            ),
            seed=ImageGenerationTool._normalize_optional_seed(raw.get("seed")),
            image_size=ImageGenerationTool._normalize_image_size(raw.get("image_size")),
            num_inference_steps=ImageGenerationTool._normalize_int(
                raw.get("num_inference_steps", DEFAULT_NUM_INFERENCE_STEPS),
                field_name="num_inference_steps",
                minimum=1,
                maximum=100,
            ),
            guidance_scale=ImageGenerationTool._normalize_float(
                raw.get("guidance_scale", DEFAULT_GUIDANCE_SCALE),
                field_name="guidance_scale",
                minimum=0.1,
                maximum=20.0,
            ),
            output_format=ImageGenerationTool._normalize_output_format(
                raw.get("output_format", DEFAULT_OUTPUT_FORMAT)
            ),
            enable_web_search=bool(raw.get("enable_web_search", False)),
            enable_safety_checker=bool(raw.get("enable_safety_checker", True)),
            upscale=bool(raw.get("upscale", self._default_upscale)),
            provided_fields=frozenset(raw),
        )

    @staticmethod
    def _normalize_aspect_ratio(value: Any) -> str:
        aspect_ratio = str(value or DEFAULT_ASPECT_RATIO).strip().lower()
        if aspect_ratio not in VALID_ASPECT_RATIOS:
            msg = f"aspect_ratio must be one of: {', '.join(VALID_ASPECT_RATIOS)}"
            raise ValueError(msg)
        return aspect_ratio

    @staticmethod
    def _normalize_resolution(value: Any) -> str:
        resolution = str(value or DEFAULT_RESOLUTION).strip()
        if resolution not in VALID_RESOLUTIONS:
            msg = f"resolution must be one of: {', '.join(VALID_RESOLUTIONS)}"
            raise ValueError(msg)
        return resolution

    @staticmethod
    def _normalize_output_format(value: Any) -> str:
        output_format = str(value or DEFAULT_OUTPUT_FORMAT).strip().lower()
        if output_format not in VALID_OUTPUT_FORMATS:
            msg = f"output_format must be one of: {', '.join(VALID_OUTPUT_FORMATS)}"
            raise ValueError(msg)
        return output_format

    @staticmethod
    def _normalize_optional_seed(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            msg = "seed must be an integer"
            raise TypeError(msg)
        return value

    @staticmethod
    def _normalize_int(
        value: Any,
        *,
        field_name: str,
        minimum: int,
        maximum: int,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            msg = f"{field_name} must be an integer between {minimum} and {maximum}"
            raise TypeError(msg)
        if not minimum <= value <= maximum:
            msg = f"{field_name} must be between {minimum} and {maximum}"
            raise ValueError(msg)
        return value

    @staticmethod
    def _normalize_float(
        value: Any,
        *,
        field_name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            msg = f"{field_name} must be a number between {minimum} and {maximum}"
            raise TypeError(msg)
        numeric = float(value)
        if not minimum <= numeric <= maximum:
            msg = f"{field_name} must be between {minimum} and {maximum}"
            raise ValueError(msg)
        return numeric

    @staticmethod
    def _normalize_image_size(value: Any) -> str | ImageSize | None:
        if value is None:
            return None
        if isinstance(value, str):
            image_size = value.strip()
            if image_size not in VALID_IMAGE_SIZES:
                msg = f"image_size must be one of: {', '.join(VALID_IMAGE_SIZES)}"
                raise ValueError(msg)
            return image_size
        if not isinstance(value, dict):
            msg = "image_size must be a preset string or an object with width and height"
            raise TypeError(msg)
        if set(value) != {"width", "height"}:
            msg = "image_size may only contain width and height"
            raise ValueError(msg)

        width = value.get("width")
        height = value.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            msg = "image_size.width and image_size.height must be integers"
            raise TypeError(msg)
        if not 64 <= width <= 2048 or not 64 <= height <= 2048:
            msg = "custom image_size dimensions must be between 64 and 2048"
            raise ValueError(msg)
        return ImageSize(width=width, height=height)

    @staticmethod
    def _normalize_nano_banana_aspect_ratio(aspect_ratio: str) -> str:
        return ASPECT_RATIO_ALIASES.get(aspect_ratio, aspect_ratio)

    @staticmethod
    def _normalize_generic_aspect_ratio(aspect_ratio: str) -> str:
        return ASPECT_RATIO_ALIASES.get(aspect_ratio, aspect_ratio)

    @staticmethod
    def _resolve_flux_image_size(request: NormalizedImageRequest) -> str | dict[str, int]:
        if isinstance(request.image_size, ImageSize):
            return request.image_size.as_payload()
        if isinstance(request.image_size, str):
            return request.image_size
        if request.aspect_ratio in FLUX_IMAGE_SIZE_BY_ASPECT:
            return FLUX_IMAGE_SIZE_BY_ASPECT[request.aspect_ratio]
        msg = (
            "image_size is required for the configured flux model when using aspect_ratio "
            f"'{request.aspect_ratio}'"
        )
        raise ValueError(msg)

    @staticmethod
    def _extract_images(result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []

        candidates: list[Any] = []
        for key in ("images", "data", "output"):
            value = result.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif isinstance(value, dict):
                candidates.append(value)

        if isinstance(result.get("image"), dict):
            candidates.append(result["image"])
        if isinstance(result.get("url"), str):
            candidates.append(result)

        parsed: list[dict[str, Any]] = []
        for candidate in candidates:
            image = ImageGenerationTool._extract_single_image(candidate)
            if image is not None:
                parsed.append(image)
        return parsed

    @staticmethod
    def _extract_single_image(candidate: Any) -> dict[str, Any] | None:
        if not isinstance(candidate, dict):
            return None
        if isinstance(candidate.get("url"), str):
            return {
                "url": candidate["url"],
                "width": candidate.get("width"),
                "height": candidate.get("height"),
                "content_type": candidate.get("content_type"),
            }

        nested_image = candidate.get("image")
        if isinstance(nested_image, dict) and isinstance(nested_image.get("url"), str):
            return {
                "url": nested_image["url"],
                "width": nested_image.get("width"),
                "height": nested_image.get("height"),
                "content_type": nested_image.get("content_type"),
            }
        return None

    def _error(self, message: str) -> str:
        return json.dumps(
            {
                "success": False,
                "model": self._model_id,
                "images": [],
                "image": None,
                "error": message,
            },
            indent=2,
        )

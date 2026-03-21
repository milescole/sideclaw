"""Configuration loading and saving."""

import json
import os
from pathlib import Path

from loguru import logger

from sideclaw.config.schema import Config

DEFAULT_CONFIG_DIR = Path.home() / ".sideclaw"

_ENV_PREFIX = "SIDECLAW_"


def get_config_path() -> Path:
    """Return the default config file path."""
    return DEFAULT_CONFIG_DIR / "config.json"


def coerce_config_value(value: str) -> str | int | float | bool:
    """Coerce a string value to int, float, bool, or string."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _apply_env_overrides(config_dict: dict) -> dict:
    """Merge SIDECLAW_ env vars into the config dict."""
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        suffix = key[len(_ENV_PREFIX) :]
        if not suffix:
            continue
        parts = suffix.lower().split("__")
        target = config_dict
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = coerce_config_value(value)
    return config_dict


def load_config(path: Path | None = None) -> Config:
    """Load config from JSON file. Returns defaults if file doesn't exist."""
    path = path or get_config_path()
    if not path.exists():
        logger.debug(f"Config not found at {path}, using defaults")
        data: dict = {}
    else:
        data = json.loads(path.read_text())
    _apply_env_overrides(data)
    return Config(**data)


def save_config(config: Config, path: Path | None = None) -> None:
    """Save config to JSON file."""
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(exclude_none=True), indent=2))
    logger.debug(f"Config saved to {path}")

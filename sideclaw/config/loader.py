"""Configuration loading and saving."""

import json
from pathlib import Path

from loguru import logger

from sideclaw.config.schema import Config

DEFAULT_CONFIG_DIR = Path.home() / ".sideclaw"


def get_config_path() -> Path:
    """Return the default config file path."""
    return DEFAULT_CONFIG_DIR / "config.json"


def load_config(path: Path | None = None) -> Config:
    """Load config from JSON file. Returns defaults if file doesn't exist."""
    path = path or get_config_path()
    if not path.exists():
        logger.debug(f"Config not found at {path}, using defaults")
        return Config()
    data = json.loads(path.read_text())
    return Config(**data)


def save_config(config: Config, path: Path | None = None) -> None:
    """Save config to JSON file."""
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(exclude_none=True), indent=2))
    logger.debug(f"Config saved to {path}")

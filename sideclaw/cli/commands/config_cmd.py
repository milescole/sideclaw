"""Config CLI surface."""

import json

import typer
from pydantic import ValidationError

from sideclaw.cli.render.console import print_line
from sideclaw.cli.render.formatting import format_error_message, format_success_message
from sideclaw.config.loader import coerce_config_value, get_config_path, load_config
from sideclaw.config.schema import Config
from sideclaw.utils.files import atomic_write_text


def _flatten_dict(d: dict, prefix: str = "") -> list[tuple[str, object]]:
    """Flatten nested dict into dot-notation key=value pairs."""
    items: list[tuple[str, object]] = []
    for key, value in d.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            items.extend(_flatten_dict(value, full_key))
        else:
            items.append((full_key, value))
    return items


def _set_nested(d: dict, parts: list[str], value: object) -> None:
    """Set a nested key in a dict, creating intermediates."""
    for part in parts[:-1]:
        if part not in d or not isinstance(d[part], dict):
            d[part] = {}
        d = d[part]
    d[parts[-1]] = value


def _remove_nested(d: dict, parts: list[str]) -> bool:
    """Remove a nested key. Returns True if found and removed."""
    for part in parts[:-1]:
        if part not in d or not isinstance(d[part], dict):
            return False
        d = d[part]
    return d.pop(parts[-1], None) is not None


def _get_nested(d: dict, parts: list[str]) -> object:
    """Traverse a dict by dot-path parts. Raises KeyError if missing."""
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            msg = ".".join(parts)
            raise KeyError(msg)
        d = d[part]
    return d


def config_list() -> None:
    """Dump config as dot-notation key=value pairs."""
    config = load_config(get_config_path())
    data = config.model_dump(exclude_none=True)
    for key, value in _flatten_dict(data):
        print_line(f"{key}={value}")


def config_get(key: str) -> None:
    """Get a config value by dot path."""
    config = load_config(get_config_path())
    data = config.model_dump(exclude_none=True)
    parts = key.split(".")
    try:
        value = _get_nested(data, parts)
    except KeyError:
        print_line(format_error_message(f"Key not found: {key}"))
        raise typer.Exit(1)
    print_line(str(value))


def config_set(key: str, value: str) -> None:
    """Set a config value by dot path."""
    config_path = get_config_path()
    if config_path.exists():
        raw = json.loads(config_path.read_text())
    else:
        raw = {}
    parts = key.split(".")
    _set_nested(raw, parts, coerce_config_value(value))
    try:
        Config(**raw)
    except ValidationError as exc:
        print_line(format_error_message(f"Invalid config: {exc.errors()[0]['msg']}"))
        raise typer.Exit(1) from exc
    config_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(config_path, json.dumps(raw, indent=2))
    print_line(format_success_message(f"Set {key}={value}"))


def config_reset(key: str) -> None:
    """Remove a key from config, letting Pydantic defaults take over."""
    config_path = get_config_path()
    if not config_path.exists():
        print_line(format_error_message(f"Key not found: {key}"))
        raise typer.Exit(1)
    raw = json.loads(config_path.read_text())
    parts = key.split(".")
    if not _remove_nested(raw, parts):
        print_line(format_error_message(f"Key not found: {key}"))
        raise typer.Exit(1)
    atomic_write_text(config_path, json.dumps(raw, indent=2))
    print_line(format_success_message(f"Reset {key}"))

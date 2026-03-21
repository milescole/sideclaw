import json
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from sideclaw.cli.main import app
from sideclaw.config.loader import save_config
from sideclaw.config.schema import AgentConfig, Config

runner = CliRunner()


def test_config_list_shows_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(Config(agent=AgentConfig(workspace=str(tmp_path / "ws"))), config_path)

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "list"])

    assert result.exit_code == 0
    assert "agent.model=" in result.output


def test_config_get_existing_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(Config(agent=AgentConfig(workspace=str(tmp_path / "ws"))), config_path)

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "get", "agent.model"])

    assert result.exit_code == 0
    assert "openai/gpt-4o-mini" in result.output


def test_config_get_missing_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(Config(), config_path)

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "get", "nonexistent.key"])

    assert result.exit_code == 1
    assert "Key not found" in result.output


def test_config_set_and_get(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"agent": {"model": "openai/gpt-4o-mini"}}))

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        set_result = runner.invoke(app, ["config", "set", "agent.max_tokens", "2048"])
        assert set_result.exit_code == 0
        assert "Set agent.max_tokens=2048" in set_result.output

        get_result = runner.invoke(app, ["config", "get", "agent.max_tokens"])
        assert get_result.exit_code == 0
        assert "2048" in get_result.output


def test_config_reset_removes_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"agent": {"model": "custom-model", "max_tokens": 2048}}))

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "reset", "agent.max_tokens"])
        assert result.exit_code == 0
        assert "Reset agent.max_tokens" in result.output

    raw = json.loads(config_path.read_text())
    assert "max_tokens" not in raw["agent"]


def test_config_set_rejects_invalid_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"agent": {"model": "openai/gpt-4o-mini"}}))

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "set", "agent.compression_threshold", "5.0"])

    assert result.exit_code == 1
    assert "Invalid config" in result.output


def test_config_reset_missing_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"agent": {"model": "openai/gpt-4o-mini"}}))

    config_cmd = import_module("sideclaw.cli.commands.config_cmd")
    with patch.object(config_cmd, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["config", "reset", "nonexistent.key"])

    assert result.exit_code == 1
    assert "Key not found" in result.output

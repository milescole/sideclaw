from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from sideclaw.cli.main import app
from sideclaw.config.loader import save_config
from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig

runner = CliRunner()


def test_doctor_passes_with_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    save_config(
        Config(
            agent=AgentConfig(workspace=str(workspace)),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    doctor_surface = import_module("sideclaw.cli.commands.doctor")
    with patch.object(doctor_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "Config loads" in result.output
    assert "Workspace exists" in result.output


def test_doctor_warns_no_provider_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    save_config(
        Config(agent=AgentConfig(workspace=str(workspace))),
        config_path,
    )

    doctor_surface = import_module("sideclaw.cli.commands.doctor")
    with patch.object(doctor_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "WARN" in result.output
    assert "No provider API keys" in result.output


def test_doctor_fails_missing_workspace(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_config(
        Config(
            agent=AgentConfig(workspace=str(tmp_path / "nonexistent")),
            providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
        ),
        config_path,
    )

    doctor_surface = import_module("sideclaw.cli.commands.doctor")
    with patch.object(doctor_surface, "get_config_path", return_value=config_path):
        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "FAIL" in result.output
    assert "Workspace missing" in result.output

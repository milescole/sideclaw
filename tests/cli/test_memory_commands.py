"""Tests for memory CLI commands."""

from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from sideclaw.cli.main import app
from sideclaw.config.schema import Config

runner = CliRunner()


def _setup_workspace(tmp_path: Path) -> Config:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory_dir = workspace / "docs" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "long-term.md").write_text("Some memory content\nwith multiple lines\n")
    (memory_dir / "history.md").write_text("[2026-03-20] Something happened\n")
    config = Config()
    config.agent.workspace = str(workspace)
    return config


def test_memory_show_lists_files(tmp_path: Path) -> None:
    config = _setup_workspace(tmp_path)
    memory_mod = import_module("sideclaw.cli.commands.memory")
    with patch.object(memory_mod, "get_config_path", return_value=tmp_path / "c.json"), patch.object(
        memory_mod, "load_config", return_value=config
    ):
        result = runner.invoke(app, ["memory", "show"])
    assert result.exit_code == 0
    assert "long-term.md" in result.output
    assert "history.md" in result.output
    assert "tokens" in result.output


def test_memory_show_no_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = Config()
    config.agent.workspace = str(workspace)
    memory_mod = import_module("sideclaw.cli.commands.memory")
    with patch.object(memory_mod, "get_config_path", return_value=tmp_path / "c.json"), patch.object(
        memory_mod, "load_config", return_value=config
    ):
        result = runner.invoke(app, ["memory", "show"])
    assert result.exit_code == 0
    assert "No memory directory" in result.output


def test_memory_usage_shows_budget(tmp_path: Path) -> None:
    config = _setup_workspace(tmp_path)
    memory_mod = import_module("sideclaw.cli.commands.memory")
    with patch.object(memory_mod, "get_config_path", return_value=tmp_path / "c.json"), patch.object(
        memory_mod, "load_config", return_value=config
    ):
        result = runner.invoke(app, ["memory", "usage"])
    assert result.exit_code == 0
    assert "% of budget" in result.output
    assert "Total:" in result.output


def test_memory_usage_includes_hot_path_docs(tmp_path: Path) -> None:
    config = _setup_workspace(tmp_path)
    workspace = Path(config.agent.workspace)
    (workspace / "AGENTS.md").write_text("# Agents\nSome content here\n")
    memory_mod = import_module("sideclaw.cli.commands.memory")
    with patch.object(memory_mod, "get_config_path", return_value=tmp_path / "c.json"), patch.object(
        memory_mod, "load_config", return_value=config
    ):
        result = runner.invoke(app, ["memory", "usage"])
    assert result.exit_code == 0
    assert "AGENTS.md" in result.output

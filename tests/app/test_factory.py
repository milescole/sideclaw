import sys
from importlib import import_module
from pathlib import Path

from sideclaw.config.schema import AgentConfig, Config, OpenRouterConfig, ProvidersConfig


def test_build_runtime_wires_common_dependencies(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config = Config(
        agent=AgentConfig(workspace=str(workspace)),
        providers=ProvidersConfig(openrouter=OpenRouterConfig(api_key="sk-test")),
    )

    factory = import_module("sideclaw.app.factory")
    runtime = factory.build_runtime(config)

    assert runtime.workspace == workspace
    assert workspace.exists()
    assert (workspace / "sessions").exists()
    assert runtime.agent_loop._workspace == workspace
    assert runtime.agent_loop._bus is runtime.bus
    assert runtime.agent_loop._provider is runtime.provider
    assert runtime.agent_loop._session_manager is runtime.session_manager
    assert runtime.runtime_service._agent_loop is runtime.agent_loop
    assert runtime.runtime_service._session_manager is runtime.session_manager


def test_importing_factory_does_not_eagerly_import_runtime_dependencies() -> None:
    sys.modules.pop("sideclaw.app.factory", None)
    sys.modules.pop("sideclaw.agent.loop", None)
    sys.modules.pop("sideclaw.providers.openrouter", None)

    import_module("sideclaw.app.factory")

    assert "sideclaw.agent.loop" not in sys.modules
    assert "sideclaw.providers.openrouter" not in sys.modules

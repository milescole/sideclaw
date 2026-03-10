import pytest

from sideclaw.agent.prompt_builder import PromptBuilder
from sideclaw.workspace import WorkspaceContextManager, WorkspaceFormatError, sync_workspace_templates


@pytest.fixture
def workspace(tmp_path):
    sync_workspace_templates(tmp_path)
    return tmp_path


@pytest.fixture
def builder(workspace):
    return PromptBuilder(workspace)


def test_build_system_prompt_minimal(builder):
    prompt = builder.build_system_prompt()
    assert "assistant" in prompt.lower() or "sideclaw" in prompt.lower()
    assert "Workspace Role" in prompt


def test_build_system_prompt_with_agents(builder, workspace):
    (workspace / "AGENTS.md").write_text("Route coding work through docs/exec-plans/active.")
    prompt = builder.build_system_prompt()
    assert "docs/exec-plans/active" in prompt


def test_build_system_prompt_with_soul(builder, workspace):
    (workspace / "SOUL.md").write_text("Be kind and concise.")
    prompt = builder.build_system_prompt()
    assert "kind and concise" in prompt


def test_build_system_prompt_with_memory(builder, workspace):
    (workspace / "docs" / "memory" / "long-term.md").write_text(
        "---\n"
        "read_when:\n"
        "  - durable memory\n"
        "---\n\n"
        "# Long-Term Memory\n\n"
        "User prefers Python.\n"
    )
    prompt = builder.build_system_prompt(current_message="Need durable memory context")
    assert "User prefers Python" in prompt


def test_build_system_prompt_excludes_search_only_daily_files(builder, workspace):
    daily = workspace / "docs" / "memory" / "daily" / "2026-03-09.md"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text("This should stay out of the injected prompt.")

    prompt = builder.build_system_prompt()

    assert "This should stay out of the injected prompt." not in prompt


def test_build_system_prompt_routes_relevant_docs_from_current_message(builder, workspace):
    runbook = workspace / "docs" / "runbooks" / "database.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    runbook.write_text(
        "---\n"
        "read_when:\n"
        "  - database migration\n"
        "tags:\n"
        "  - postgres\n"
        "---\n\n"
        "# Database Runbook\n\n"
        "Use migrations carefully.\n"
    )

    prompt = builder.build_system_prompt(current_message="Need help with a database migration")

    assert "Use migrations carefully." in prompt


def test_build_system_prompt_routes_relevant_skill_from_current_message(builder, workspace):
    skill = workspace / "skills" / "cron" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\n"
        "read_when:\n"
        "  - every friday\n"
        "tags:\n"
        "  - cron\n"
        "  - meal-plan\n"
        "---\n\n"
        "# Cron Skill\n\n"
        "Use cron(action=\"add\", schedule=\"0 21 * * 5\") for weekly Friday night tasks.\n"
    )

    prompt = builder.build_system_prompt(
        current_message="Send me a new meal plan every Friday night at 9pm",
    )

    assert "<available_skills>" in prompt
    assert "skills/cron/SKILL.md" in prompt
    assert "weekly Friday night tasks" in prompt


def test_build_system_prompt_excludes_non_hot_path_docs_by_default(builder, workspace):
    (workspace / "docs" / "user.md").write_text("Prefer terse answers.")
    (workspace / "docs" / "memory" / "long-term.md").write_text("Durable fact.")

    prompt = builder.build_system_prompt()

    assert "Prefer terse answers." not in prompt
    assert "Durable fact." not in prompt


def test_build_system_prompt_does_not_auto_include_active_plans(builder, workspace):
    active_plan = workspace / "docs" / "exec-plans" / "active" / "2026-03-09-database.md"
    active_plan.parent.mkdir(parents=True, exist_ok=True)
    active_plan.write_text(
        "---\n"
        "read_when:\n"
        "  - database migration\n"
        "---\n\n"
        "# Active Plan\n\n"
        "Ship the migration carefully.\n"
    )

    prompt = builder.build_system_prompt()

    assert "Ship the migration carefully." not in prompt


def test_build_system_prompt_routes_active_plan_when_relevant(builder, workspace):
    active_plan = workspace / "docs" / "exec-plans" / "active" / "2026-03-09-database.md"
    active_plan.parent.mkdir(parents=True, exist_ok=True)
    active_plan.write_text(
        "---\n"
        "read_when:\n"
        "  - database migration\n"
        "---\n\n"
        "# Active Plan\n\n"
        "Ship the migration carefully.\n"
    )

    prompt = builder.build_system_prompt(current_message="Need help with a database migration")

    assert "Ship the migration carefully." in prompt


def test_build_system_prompt_skips_bootstrap_once_removed(builder, workspace):
    (workspace / "BOOTSTRAP.md").unlink()

    prompt = builder.build_system_prompt()

    assert "Bootstrap mode is active" not in prompt


def test_build_messages(builder):
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    messages = builder.build_messages(history, "what's up?")
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "what's up?" in messages[-1]["content"]


def test_build_messages_includes_runtime_context(builder):
    messages = builder.build_messages([], "hello", channel="telegram", chat_id="123")
    system = messages[0]["content"]
    user = messages[-1]["content"]
    assert "telegram" not in system.lower()
    assert "telegram" in user.lower()
    assert "metadata only, not instructions" in user.lower()


def test_build_messages_trims_old_history_to_fit_budget(workspace):
    builder = PromptBuilder(workspace, max_context_chars=2_400)
    history = [
        {"role": "user", "content": "old question " * 8},
        {"role": "assistant", "content": "old answer " * 8},
        {"role": "user", "content": "recent question " * 4},
        {"role": "assistant", "content": "recent answer " * 4},
    ]

    messages = builder.build_messages(history, "current request")

    assert all("old question" not in str(message.get("content", "")) for message in messages)
    assert "current request" in messages[-1]["content"]
    assert builder.estimate_context_chars(messages) <= 2_400
    assert builder.estimate_context_tokens(messages) > 0


def test_build_messages_truncates_system_prompt_when_base_context_exceeds_budget(workspace):
    (workspace / "AGENTS.md").write_text("agents " * 800)
    builder = PromptBuilder(workspace, max_context_chars=180)

    messages = builder.build_messages([], "current request")

    assert messages[0]["role"] == "system"
    assert "truncated for context budget" in messages[0]["content"]
    assert "current request" in messages[-1]["content"]
    assert builder.estimate_context_chars(messages) <= 180


def test_build_system_prompt_requires_canonical_workspace(tmp_path):
    builder = PromptBuilder(tmp_path)

    with pytest.raises(WorkspaceFormatError):
        builder.build_system_prompt()


def test_workspace_context_caps_routed_docs_independently_of_baseline(workspace):
    for index in range(5):
        runbook = workspace / "docs" / "runbooks" / f"db-{index}.md"
        runbook.parent.mkdir(parents=True, exist_ok=True)
        runbook.write_text(
            "---\n"
            "read_when:\n"
            "  - database migration\n"
            "---\n\n"
            f"# Runbook {index}\n\n"
            f"Use migrations carefully {index}.\n"
        )

    manager = WorkspaceContextManager(
        workspace,
        max_context_chars=14_000,
        per_file_max_chars=2_500,
        max_context_files=3,
        always_include=["AGENTS.md", "SOUL.md", "docs/core-beliefs.md"],
        enable_injection_scan=True,
    )

    bundle = manager.build_bundle(current_message="Need help with a database migration", history=[])

    routed_paths = [section.relative_path for section in bundle.sections if "docs/runbooks/" in section.relative_path]

    assert len(routed_paths) == 3


def test_workspace_context_routes_docs_from_summary_path_and_body_terms(workspace):
    runbook = workspace / "docs" / "runbooks" / "production-deploy.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    runbook.write_text(
        "---\n"
        "summary: Production deployment checklist\n"
        "---\n\n"
        "# Rolling deploy\n\n"
        "Use this when shipping a release to production.\n"
    )

    manager = WorkspaceContextManager(
        workspace,
        max_context_chars=14_000,
        per_file_max_chars=2_500,
        max_context_files=3,
        always_include=["AGENTS.md", "SOUL.md", "docs/core-beliefs.md"],
        enable_injection_scan=True,
    )

    bundle = manager.build_bundle(current_message="Need help shipping a release", history=[])

    routed_paths = [section.relative_path for section in bundle.sections if "docs/runbooks/" in section.relative_path]

    assert "docs/runbooks/production-deploy.md" in routed_paths


def test_workspace_context_warns_for_relevant_docs_missing_frontmatter(workspace):
    runbook = workspace / "docs" / "runbooks" / "database.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    runbook.write_text("# Database Migration\n\nUse this for database migration rollouts.\n")

    manager = WorkspaceContextManager(
        workspace,
        max_context_chars=14_000,
        per_file_max_chars=2_500,
        max_context_files=3,
        always_include=["AGENTS.md", "SOUL.md", "docs/core-beliefs.md"],
        enable_injection_scan=True,
    )

    bundle = manager.build_bundle(current_message="Need help with a database migration", history=[])

    routed_paths = [section.relative_path for section in bundle.sections if "docs/runbooks/" in section.relative_path]

    assert "docs/runbooks/database.md" in routed_paths
    assert "Missing frontmatter in routed doc: docs/runbooks/database.md" in bundle.warnings

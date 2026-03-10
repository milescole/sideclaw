from sideclaw.agent.skills import SkillsLoader
from sideclaw.workspace import sync_workspace_templates


def test_skills_loader_lists_skill(tmp_path) -> None:
    sync_workspace_templates(tmp_path)
    skill = tmp_path / "skills" / "cron" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\n"
        "summary: Weekly scheduling guidance\n"
        "---\n\n"
        "# Cron Skill\n\n"
        "Use the cron tool.\n"
    )

    skills = SkillsLoader(tmp_path).list_skills()

    assert skills == [
        {
            "name": "cron",
            "path": "skills/cron/SKILL.md",
            "description": "Weekly scheduling guidance",
            "source": "workspace",
        }
    ]


def test_skills_loader_ranks_matching_skill(tmp_path) -> None:
    sync_workspace_templates(tmp_path)
    skill = tmp_path / "skills" / "cron" / "SKILL.md"
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
        "Use the cron tool for recurring Friday night plans.\n"
    )

    ranked, warnings = SkillsLoader(tmp_path).rank_paths(
        current_message="Send me a new meal plan every Friday night at 9pm",
        history=[],
    )

    assert ranked[0]["display_path"] == "skills/cron/SKILL.md"
    assert warnings == []

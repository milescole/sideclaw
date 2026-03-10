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

    assert skills[0] == {
        "name": "cron",
        "path": "skills/cron/SKILL.md",
        "description": "Weekly scheduling guidance",
        "source": "workspace",
    }
    assert {
        skill["name"]: skill["path"]
        for skill in skills
    } == {
        "cron": "skills/cron/SKILL.md",
        "find-skills": "skills/find-skills/SKILL.md",
        "skill-creator": "skills/skill-creator/SKILL.md",
    }


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


def test_skills_loader_ranks_builtin_find_skills(tmp_path) -> None:
    sync_workspace_templates(tmp_path)

    ranked, warnings = SkillsLoader(tmp_path).rank_paths(
        current_message="Find a skill for docker deployment workflows",
        history=[],
    )

    assert ranked[0]["display_path"] == "skills/find-skills/SKILL.md"
    assert warnings == []


def test_skills_loader_ranks_description_only_skill(tmp_path) -> None:
    skill = tmp_path / "skills" / "skill-creator" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\n"
        "name: skill-creator\n"
        "description: Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets.\n"
        "---\n\n"
        "# Skill Creator\n\n"
        "Follow the skill creation workflow.\n"
    )

    ranked, warnings = SkillsLoader(tmp_path, builtin_skills_dir=tmp_path / "_builtin").rank_paths(
        current_message="Create a new skill with scripts and references for PDF workflows",
        history=[],
    )

    assert ranked[0]["display_path"] == "skills/skill-creator/SKILL.md"
    assert warnings == []

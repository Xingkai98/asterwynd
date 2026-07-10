from pathlib import Path

import pytest

from agent.skills.loader import SkillLoader
from agent.skills.runtime import SkillRuntime


def write_skill(
    root: Path,
    name: str,
    *,
    description: str = "review code changes",
    prompt: str = "Use careful review steps.",
    always: bool = False,
    triggers: list[str] | None = None,
    user_invocable: bool = True,
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    trigger_block = ""
    if triggers is not None:
        trigger_block = "triggers:\n" + "".join(f"  - {trigger}\n" for trigger in triggers)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "tools: [Read, Bash]\n"
        f"always: {'true' if always else 'false'}\n"
        f"user_invocable: {'true' if user_invocable else 'false'}\n"
        "argument_hint: <request>\n"
        f"{trigger_block}"
        "---\n\n"
        f"# {name}\n\n"
        f"{prompt}\n",
        encoding="utf-8",
    )
    return skill_dir / "SKILL.md"


def test_loads_directory_style_skills_and_metadata(tmp_path):
    skill_path = write_skill(
        tmp_path,
        "code-review",
        description="审查代码变更",
        triggers=["review", "审查"],
    )

    outcome = SkillLoader().load_roots([tmp_path])

    assert outcome.diagnostics == []
    assert len(outcome.skills) == 1
    skill = outcome.skills[0]
    assert skill.name == "code-review"
    assert skill.description == "审查代码变更"
    assert skill.tools == ["Read", "Bash"]
    assert skill.triggers == ("review", "审查")
    assert skill.argument_hint == "<request>"
    assert skill.user_invocable is True
    assert skill.source_path == skill_path


def test_root_level_markdown_files_are_not_loaded(tmp_path):
    (tmp_path / "legacy.md").write_text(
        "---\nname: legacy\ndescription: old\n---\nlegacy prompt\n",
        encoding="utf-8",
    )

    outcome = SkillLoader().load_roots([tmp_path])

    assert outcome.skills == []


def test_load_roots_records_missing_invalid_and_duplicate_diagnostics(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    invalid_root = tmp_path / "invalid"
    missing_root = tmp_path / "missing"
    write_skill(first_root, "review", prompt="first")
    write_skill(second_root, "review", prompt="second")
    (invalid_root / "broken").mkdir(parents=True)
    (invalid_root / "broken" / "SKILL.md").write_text("missing frontmatter", encoding="utf-8")

    outcome = SkillLoader().load_roots([first_root, second_root, invalid_root, missing_root])

    assert [skill.prompt for skill in outcome.skills] == ["# review\n\nfirst"]
    messages = [diagnostic.message for diagnostic in outcome.diagnostics]
    assert any("duplicate skill" in message for message in messages)
    assert any("Invalid skill format" in message for message in messages)
    assert any("does not exist" in message for message in messages)


def test_skill_runtime_renders_index_and_active_context(tmp_path):
    write_skill(
        tmp_path,
        "code-review",
        description="审查代码变更",
        prompt="review prompt",
        triggers=["review"],
    )
    runtime = SkillRuntime.from_roots([tmp_path])

    index = runtime.render_skill_index()
    assert "Available skills" in index
    assert "/code-review <request>" in index
    assert "review prompt" not in index

    runtime.begin_run("请 review 这个 change")
    context = runtime.render_active_skill_context()

    assert "Active Skill: code-review" in context
    assert "review prompt" in context


def test_queued_skill_activation_takes_priority_over_local_match(tmp_path):
    write_skill(
        tmp_path,
        "code-review",
        description="审查代码变更",
        prompt="review prompt",
        triggers=["审查"],
    )
    runtime = SkillRuntime.from_roots([tmp_path])

    queued = runtime.queue_activation("code-review", source="slash_command")
    runtime.begin_run("请审查这个 change")

    assert queued.activated is True
    assert runtime.activations == [
        {"skill_name": "code-review", "source": "slash_command"}
    ]


@pytest.mark.asyncio
async def test_skill_runtime_activate_skill_for_current_run(tmp_path):
    write_skill(tmp_path, "research", description="调研信息", prompt="research prompt")
    runtime = SkillRuntime.from_roots([tmp_path])
    runtime.begin_run("普通问题")

    result = runtime.activate_skill("research", source="llm_tool", reason="need research")

    assert result.activated is True
    assert "Activated skill: research" in result.message
    assert "research prompt" in runtime.render_active_skill_context()


def test_skill_runtime_activate_unknown_and_duplicate(tmp_path):
    write_skill(tmp_path, "research")
    runtime = SkillRuntime.from_roots([tmp_path])
    runtime.begin_run("普通问题")

    missing = runtime.activate_skill("missing", source="llm_tool")
    first = runtime.activate_skill("research", source="llm_tool")
    second = runtime.activate_skill("research", source="llm_tool")

    assert missing.activated is False
    assert "Unknown skill" in missing.message
    assert first.activated is True
    assert second.activated is False
    assert "already active" in second.message

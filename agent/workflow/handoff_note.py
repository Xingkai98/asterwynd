from __future__ import annotations

from pathlib import Path

from agent.workflow.models import Phase, StateSnapshot

FALLBACK_HANDOFF_PROMPT = """You are completing the "{current_phase}" phase of change "{change_id}".

Read all documents in openspec/changes/{change_id}/, including handoff.json
for current state, then produce a handoff note at
.handoff/{change_id}/{current_phase}-to-{next_phase}.md that covers:

1. What was done in this phase (summary)
2. Key decisions made and why
3. Alternatives considered and rejected
4. Open questions or risks for the next phase
5. Specific entry point and priority hints for the next agent

Keep the note concise — aim for 200-400 words. Then update handoff.json:
append to transitions, update current state, and set next hints.

**ADR 格式要求**: 对于有 >= 2 个备选方案的关键决策，必须使用 ADR 格式记录。
在 handoff note 的 Key Decisions 章节中，每个符合条件的决策引用对应的 ADR 文件名
（如 `adr/0001-xxx.md`），并包含：决策标题、备选方案表格（方案|描述|拒绝原因）、
选择理由和重访条件。ADR 模板参考 `docs/adr/_TEMPLATE.md`。
如果该决策尚无 ADR 文件，必须在 handoff note 中内联完整的 ADR 格式记录。"""

HANDOFF_NOTE_SECTIONS = [
    "## Summary",
    "## Key Decisions",
    "## Alternatives Considered",
    "## Open Questions / Risks",
    "## Entry Point and Priority Hints",
]


def build_handoff_filename(from_phase: Phase, to_phase: Phase) -> str:
    return f"{from_phase}-to-{to_phase}.md"


def build_handoff_path(
    change_id: str,
    from_phase: Phase,
    to_phase: Phase,
    base_dir: str | Path = ".handoff",
) -> Path:
    directory = Path(base_dir) / change_id
    return directory / build_handoff_filename(from_phase, to_phase)


def build_fallback_prompt(
    change_id: str,
    current_phase: Phase,
    next_phase: Phase,
) -> str:
    return FALLBACK_HANDOFF_PROMPT.format(
        current_phase=current_phase,
        next_phase=next_phase,
        change_id=change_id,
    )


def ensure_handoff_dir(change_id: str, base_dir: str | Path = ".handoff") -> Path:
    directory = Path(base_dir) / change_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def generate_handoff_note(
    change_id: str,
    from_phase: Phase,
    to_phase: Phase,
    base_dir: str | Path = ".handoff",
    *,
    use_skill: bool = True,
) -> tuple[Path, str]:
    """Generate a handoff note file path and prompt.

    Returns (file_path, prompt_to_use). The caller is responsible for
    executing the prompt (via skill or LLM call) and writing the content.
    """
    ensure_handoff_dir(change_id, base_dir)
    file_path = build_handoff_path(change_id, from_phase, to_phase, base_dir)

    if use_skill:
        prompt = (
            f"Use the handoff skill to generate a handoff note for change "
            f"'{change_id}' transitioning from {from_phase} to {to_phase}. "
            f"Write the output to {file_path}."
        )
    else:
        prompt = build_fallback_prompt(change_id, from_phase, to_phase)

    return file_path, prompt


def write_handoff_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_handoff_note(path: Path) -> str:
    return path.read_text(encoding="utf-8")

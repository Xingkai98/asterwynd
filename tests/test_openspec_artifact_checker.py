from pathlib import Path

from scripts.check_openspec_artifacts import (
    check_backlog_consistency,
    check_change,
    parse_change_type,
)


VALID_DESIGN = """## Context
This change has context.

## Goals / Non-Goals
Goals and non-goals are documented.

## Decisions
Decision one is documented.

## Risks / Trade-offs
Risks are documented.

## Testing Strategy
Tests are documented.

## Pre-Implementation Review
Questions resolved: documented.
Options considered: documented.
Rejected alternatives: documented.
Final confirmations: documented.
Remaining risks: documented.
"""

VALID_DESIGN_WITHOUT_REVIEW = """## Context
This change has context.

## Goals / Non-Goals
Goals and non-goals are documented.

## Decisions
Decision one is documented.

## Risks / Trade-offs
Risks are documented.

## Testing Strategy
Tests are documented.
"""

VALID_DIAGNOSIS = """## Symptom
The issue is visible.

## Reproduction
Run the repro.

## Evidence
Evidence is recorded.

## Root Cause
The root cause is known.

## Recommended Direction
The direction is documented.

## Regression Tests
Regression tests are documented.
"""

VALID_REFERENCE_RESEARCH = """## Reference Implementation Research

- status: enabled
- reason: Reference implementations are relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
"""


def write_change(root: Path, proposal: str, design: str | None = None, diagnosis: str | None = None):
    root.mkdir(parents=True)
    (root / "proposal.md").write_text(proposal, encoding="utf-8")
    if design is not None:
        (root / "design.md").write_text(design, encoding="utf-8")
    if diagnosis is not None:
        (root / "diagnosis.md").write_text(diagnosis, encoding="utf-8")


def write_tasks(root: Path, text: str):
    (root / "tasks.md").write_text(text, encoding="utf-8")


def write_spec_delta(root: Path, capability: str = "web-ui"):
    spec = root / "specs" / capability / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("## ADDED Requirements\n\n### Requirement: Example\n\nExample.\n", encoding="utf-8")


def proposal_for(
    change_type: str,
    extra: str = "",
    *,
    impact: bool = True,
    reference_research: bool = True,
) -> str:
    proposal = f"""## Change Type

- primary: {change_type}
"""
    if extra:
        proposal += f"\n{extra.strip()}\n"
    if impact:
        proposal += """
## Impact Analysis

- Tests: covered.
"""
    if reference_research and change_type != "docs":
        proposal += f"\n{VALID_REFERENCE_RESEARCH}"
    return proposal


def test_parse_change_type_primary_and_secondary():
    change_type, errors = parse_change_type(
        """## Change Type

- primary: bugfix
- secondary: [research, feature]
"""
    )

    assert errors == []
    assert change_type is not None
    assert change_type.primary == "bugfix"
    assert change_type.secondary == ("research", "feature")
    assert change_type.all_types == {"bugfix", "research", "feature"}


def test_combined_bugfix_research_feature_requires_diagnosis_and_design(tmp_path):
    change = tmp_path / "harden-web-search"
    write_change(
        change,
        """## Change Type

- primary: bugfix
- secondary: [research, feature]

## Impact Analysis

- Tests: covered.

## Reference Implementation Research

- status: enabled
- reason: Reference implementations are relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. Spec\n\n- [ ] Run grill-with-docs.\n")

    errors = check_change(change)

    assert errors == ["harden-web-search: missing required file: diagnosis.md"]


def test_combined_type_passes_when_all_required_artifacts_exist(tmp_path):
    change = tmp_path / "harden-web-search"
    write_change(
        change,
        """## Change Type

- primary: bugfix
- secondary: [research, feature]

## Impact Analysis

- Tests: covered.

## Reference Implementation Research

- status: enabled
- reason: Reference implementations are relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
        diagnosis=VALID_DIAGNOSIS,
    )

    write_tasks(
        change,
        "## 1. Spec\n\n- [ ] Run grill-with-docs.\n\n"
        "## 4. Verification\n\n- [ ] Run benchmark smoke.\n",
    )

    assert check_change(change) == []


def test_design_placeholder_section_fails(tmp_path):
    change = tmp_path / "add-feature"
    write_change(
        change,
        proposal_for("feature"),
        design="""## Context
<!-- Background and current state -->

## Goals / Non-Goals
Goals are documented.

## Decisions
Decisions are documented.

## Risks / Trade-offs
Risks are documented.

## Testing Strategy
Tests are documented.

## Pre-Implementation Review
Questions resolved: documented.
""",
    )
    write_tasks(change, "## 1. Spec\n\n- [ ] Run grill-with-docs.\n")

    assert check_change(change) == [
        "add-feature: design.md section is empty or placeholder-only: ## Context"
    ]


def test_docs_only_change_does_not_require_design(tmp_path):
    change = tmp_path / "fix-readme"
    write_change(
        change,
        """## Change Type

- primary: docs
""",
    )

    assert check_change(change) == []


def test_core_change_requires_benchmark_smoke_task(tmp_path):
    change = tmp_path / "change-tool-system"
    write_change(
        change,
        proposal_for("feature", """## Capabilities

### Modified Capabilities

- `tool-system`: Update tool behavior.
"""),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. Spec\n\n- [ ] Run grill-with-docs.\n\n"
        "## 4. Verification\n\n- [ ] Run full tests.\n",
    )

    assert check_change(change) == [
        "change-tool-system: tasks.md missing benchmark smoke verification item for coding-agent core change"
    ]


def test_core_change_passes_with_benchmark_smoke_task(tmp_path):
    change = tmp_path / "change-tool-system"
    write_change(
        change,
        proposal_for("feature", """## Capabilities

### Modified Capabilities

- `tool-system`: Update tool behavior.
"""),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n- [ ] 开发前使用 `grill-with-docs`。\n\n"
        "## 4. Verification\n\n- [ ] 跑通至少一个 benchmark smoke。\n",
    )

    assert check_change(change) == []


def test_design_change_requires_preimplementation_design_review_task(tmp_path):
    change = tmp_path / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")

    assert check_change(change) == [
        "change-ui: tasks.md missing pre-implementation grill-with-docs or equivalent design review task"
    ]


def test_non_core_change_does_not_require_benchmark_smoke_task(tmp_path):
    change = tmp_path / "change-doc-process"
    write_change(
        change,
        proposal_for("process"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n\n"
        "## 4. Verification\n\n- [ ] Run OpenSpec validation.\n",
    )

    assert check_change(change) == []


def test_spec_delta_requires_matching_current_spec(tmp_path):
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n"
        "- [ ] 开发前使用等价设计追问。\n"
        "- [ ] 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。\n",
    )
    write_spec_delta(change, "web-ui")

    assert check_change(change, tmp_path / "openspec" / "specs") == [
        "change-ui: spec delta capability `web-ui` has no matching current spec at "
        f"{tmp_path / 'openspec' / 'specs' / 'web-ui' / 'spec.md'}"
    ]


def test_spec_delta_requires_current_spec_sync_task(tmp_path):
    specs_root = tmp_path / "openspec" / "specs"
    current = specs_root / "web-ui" / "spec.md"
    current.parent.mkdir(parents=True)
    current.write_text("# web-ui 规格\n", encoding="utf-8")

    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")
    write_spec_delta(change, "web-ui")

    assert check_change(change, specs_root) == [
        "change-ui: tasks.md missing current spec sync task for spec delta "
        "(`openspec/specs/<capability>/spec.md`)"
    ]


def test_spec_delta_passes_with_matching_current_spec_and_sync_task(tmp_path):
    specs_root = tmp_path / "openspec" / "specs"
    current = specs_root / "web-ui" / "spec.md"
    current.parent.mkdir(parents=True)
    current.write_text("# web-ui 规格\n", encoding="utf-8")

    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n"
        "- [ ] 开发前使用等价设计追问。\n"
        "- [ ] 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。\n",
    )
    write_spec_delta(change, "web-ui")

    assert check_change(change, specs_root) == []


def test_non_docs_change_requires_impact_analysis(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", impact=False),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md or design.md missing required section: ## Impact Analysis"
    ]


def test_docs_only_change_does_not_require_impact_analysis(tmp_path):
    change = tmp_path / "fix-docs"
    write_change(
        change,
        """## Change Type

- primary: docs
""",
    )

    assert check_change(change) == []


def test_non_docs_change_requires_reference_implementation_research(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md or design.md missing required section: "
        "## Reference Implementation Research"
    ]


def test_reference_implementation_research_enabled_requires_fields(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- status: enabled
- reason: Relevant.
- research questions:
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The checker should enforce records.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md section must include non-empty "
        "`research questions` when reference implementation research is enabled: "
        "## Reference Implementation Research"
    ]


def test_reference_implementation_research_disabled_requires_reason(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- status: disabled
- reason:
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md section must include non-empty `reason`: "
        "## Reference Implementation Research"
    ]


def test_reference_implementation_research_can_be_recorded_in_design(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False),
        design=VALID_DESIGN + "\n" + VALID_REFERENCE_RESEARCH,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == []


def test_design_change_requires_preimplementation_review_section(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process"),
        design=VALID_DESIGN_WITHOUT_REVIEW,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: design.md missing required section: ## Pre-Implementation Review"
    ]


def test_backlog_rejects_archived_change_reference(tmp_path):
    changes = tmp_path / "openspec" / "changes"
    archive = changes / "archive" / "2026-06-22-done-change"
    archive.mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

### 1. `done-change`

状态：未实现。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    assert check_backlog_consistency(changes, backlog) == [
        "backlog references archived change `done-change`; remove it from backlog"
    ]


def test_backlog_rejects_missing_active_change_reference(tmp_path):
    changes = tmp_path / "openspec" / "changes"
    (changes / "archive").mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

### 1. `missing-change`

状态：未实现。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    assert check_backlog_consistency(changes, backlog) == [
        "backlog references missing active change `missing-change`"
    ]


def test_backlog_accepts_active_change_reference(tmp_path):
    changes = tmp_path / "openspec" / "changes"
    (changes / "active-change").mkdir(parents=True)
    (changes / "archive").mkdir()
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

### 1. `active-change`

状态：未实现。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    assert check_backlog_consistency(changes, backlog) == []

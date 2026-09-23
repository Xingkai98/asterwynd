from pathlib import Path
import json
import re
import subprocess

import pytest

from scripts.check_openspec_artifacts import (
    check_backlog_consistency,
    check_change,
    check_protected_path_explanations,
    main,
    parse_change_type,
)


@pytest.fixture(autouse=True)
def _seed_policy_file(tmp_path):
    """Seed scripts/flow-policy.json so protected-path checks load real rules.

    flow-policy-source P0: the checker loads PROTECTED_PATH_RULES from
    scripts/flow-policy.json (single policy source), so tmp_path-based repo
    fixtures must provide it.
    """
    src = Path(__file__).resolve().parents[1] / "scripts" / "flow-policy.json"
    target = tmp_path / "scripts" / "flow-policy.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


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

- research_tier: full
- status: enabled
- reason: Reference implementations are relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
"""

ALL_TASKS_CHECKED = (
    "## 1. 规格\n\n- [x] 1.1 完成。\n- [x] 开发前使用等价设计追问。\n"
)


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


def write_review_evidence(repo_root: Path, change_id: str, phase: str = "building"):
    """写一个通过 verify_review_manifest 的 review report + manifest。

    审阅证据放在 change 目录的 reviews/ 子目录（随 change 进 PR，CI 可校验）。
    测试目录非 git repo，verify 跳过 sha 校验；哈希基于实际文件计算。
    """
    from agent.workflow.review_manifest import write_review_manifest

    review_dir = repo_root / "openspec" / "changes" / change_id / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    report_path = review_dir / f"{phase}-review.md"
    report_path.write_text("## Verdict\n\n**PASS**\n", encoding="utf-8")
    write_review_manifest(
        repo_root,
        change_id,
        phase,
        reviewer_run_id="test-reviewer",
        base_sha="0" * 40,
        head_sha="0" * 40,
        verdict="PASS",
    )


def _seed_gen1_change(change: Path, change_id: str) -> None:
    """老世代（gen-1）种子：`initialized` 首事件 + handoff.json 投影 + 一次 sub_state 推进。

    原实现用 `WorkflowManager(...)`（已随四阶段状态机退役删除）。
    """
    change.mkdir(parents=True)
    handoff = {
        "schema_version": "1.0",
        "change_id": change_id,
        "state": {"phase": "planning", "sub_state": "exploring"},
        "transitions": [],
        "current_agent": None,
        "last_gate": None,
        "blockers": [],
        "routing": {},
        "next_hints": {},
    }
    events = [
        {
            "schema": "workflow-event/v1",
            "seq": 1,
            "event_type": "initialized",
            "change_id": change_id,
            "handoff": handoff,
        },
        {
            "schema": "workflow-event/v1",
            "seq": 2,
            "event_type": "transition_applied",
            "change_id": change_id,
            "transition": {
                "from": {"phase": "planning", "sub_state": "exploring"},
                "to": {"phase": "planning", "sub_state": "writing_proposal"},
                "trigger": "auto",
                "actor_type": "agent",
                "actor_id": "system",
            },
        },
    ]
    (change / "workflow-events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8"
    )
    handoff["state"] = {"phase": "planning", "sub_state": "writing_proposal"}
    (change / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def test_check_change_rejects_handoff_projection_mismatch(tmp_path):
    change = tmp_path / "tampered-change"
    _seed_gen1_change(change, "tampered-change")
    handoff_path = change / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["state"] = {"phase": "building", "sub_state": "writing_tests"}
    handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    (change / "proposal.md").write_text(proposal_for("docs"), encoding="utf-8")

    errors = check_change(change, tmp_path / "openspec" / "specs")

    assert any("handoff.json projection does not match workflow-events.jsonl" in e for e in errors)


def test_check_change_rejects_review_report_without_manifest(tmp_path):
    change = tmp_path / "openspec" / "changes" / "reviewed-change"
    write_change(change, proposal_for("docs"))
    review_dir = change / "reviews"
    review_dir.mkdir(parents=True)
    (review_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")

    errors = check_change(change, tmp_path / "openspec" / "specs")

    assert any("review manifest missing" in e for e in errors)


def test_feature_change_requires_building_review_manifest(tmp_path):
    """强制：非 docs + 有 spec delta + tasks 全勾选的 change 必须跑独立审阅。"""
    change = tmp_path / "openspec" / "changes" / "feature-change"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 实现\n\n"
        "- [x] 功能实现。\n",
    )
    write_spec_delta(change, "web-ui")

    # 无 .handoff/ 目录 → 报 building-review.md missing
    errors = check_change(change, tmp_path / "openspec" / "specs")
    assert any("building-review.md missing" in e for e in errors), errors


def test_partial_change_does_not_require_building_review(tmp_path):
    """回归：部分实现（有 [ ] 未勾选）的 change 不触发强制审阅。

    修复审阅发现的门禁误伤：spec delta 从 proposal 阶段就存在，未实现
    的 active change 不应被 building 审阅门禁拦截。
    """
    change = tmp_path / "openspec" / "changes" / "partial-change"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 实现\n\n"
        "- [x] 已完成项。\n"
        "- [ ] 待实现项。\n",
    )
    write_spec_delta(change, "web-ui")

    errors = check_change(change, tmp_path / "openspec" / "specs")
    assert not any("building-review.md missing" in e for e in errors), errors


def test_feature_change_rejects_review_report_without_manifest(tmp_path):
    """强制：有 building-review.md 但缺 manifest → verify_review_manifest 报错。"""
    change = tmp_path / "openspec" / "changes" / "feature-change"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 实现\n\n"
        "- [x] 功能实现。\n",
    )
    write_spec_delta(change, "web-ui")
    review_dir = change / "reviews"
    review_dir.mkdir(parents=True)
    (review_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")

    errors = check_change(change, tmp_path / "openspec" / "specs")
    assert any("review manifest missing" in e for e in errors), errors


def test_docs_change_does_not_require_building_review(tmp_path):
    """docs change 不强制 building review（无代码实现）。"""
    change = tmp_path / "openspec" / "changes" / "docs-change"
    write_change(change, proposal_for("docs"))
    write_tasks(change, "## 1. 文档\n\n- [x] 更新文档。\n")

    errors = check_change(change, tmp_path / "openspec" / "specs")
    assert not any("building-review.md missing" in e for e in errors), errors


def test_known_debt_change_requires_workflow_event_explanation(tmp_path):
    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"docs/known-debt.md"},
    )

    assert errors == [
        "protected path `docs/known-debt.md` changed without workflow event explanation"
    ]


def test_known_debt_workflow_event_requires_reason_and_approver(tmp_path):
    event_log = tmp_path / "openspec" / "changes" / "test-change" / "workflow-events.jsonl"
    event_log.parent.mkdir(parents=True)
    event_log.write_text(
        json.dumps(
            {
                "schema": "workflow-event/v1",
                "seq": 1,
                "event_type": "protected_artifact_explained",
                "change_id": "test-change",
                "artifact_path": "docs/known-debt.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"docs/known-debt.md"},
    )

    assert errors == [
        "protected artifact event for `docs/known-debt.md` missing required field: reason",
        "protected artifact event for `docs/known-debt.md` missing required field: approved_by",
    ]


def test_known_debt_change_passes_with_valid_workflow_event_explanation(tmp_path):
    event_log = tmp_path / "openspec" / "changes" / "test-change" / "workflow-events.jsonl"
    event_log.parent.mkdir(parents=True)
    event_log.write_text(
        json.dumps(
            {
                "schema": "workflow-event/v1",
                "seq": 1,
                "event_type": "protected_artifact_explained",
                "change_id": "test-change",
                "artifact_path": "docs/known-debt.md",
                "reason": "closing review accepted the documented debt entry",
                "approved_by": "human",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"docs/known-debt.md"},
    )

    assert errors == []


def test_current_spec_change_requires_sync_event(tmp_path):
    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"openspec/specs/dev-workflow-state-machine/spec.md"},
    )

    assert errors == [
        "protected path `openspec/specs/dev-workflow-state-machine/spec.md` "
        "changed without workflow event explanation"
    ]


def test_backlog_change_requires_backlog_event(tmp_path):
    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"docs/openspec-change-backlog.md"},
    )

    assert errors == [
        "protected path `docs/openspec-change-backlog.md` "
        "changed without workflow event explanation"
    ]


def test_archive_change_requires_archive_event(tmp_path):
    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"openspec/changes/archive/2026-07-30-test-change/proposal.md"},
    )

    assert errors == [
        "protected path `openspec/changes/archive/2026-07-30-test-change/proposal.md` "
        "changed without workflow event explanation"
    ]


def test_archive_event_accepts_change_id_without_archive_date_prefix(tmp_path):
    archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-07-30-test-change"
    archive_dir.mkdir(parents=True)
    (archive_dir / "workflow-events.jsonl").write_text(
        json.dumps(
            {
                "schema": "workflow-event/v1",
                "seq": 1,
                "event_type": "change_archived",
                "change_id": "test-change",
                "artifact_path": "openspec/changes/archive/2026-07-30-test-change",
                "reason": "closing archived accepted change artifacts",
                "approved_by": "human",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = check_protected_path_explanations(
        tmp_path,
        changed_paths={"openspec/changes/archive/2026-07-30-test-change/proposal.md"},
    )

    assert errors == []


def test_main_rejects_protected_path_diff_without_event(tmp_path, monkeypatch):
    changes_root = tmp_path / "openspec" / "changes"
    (changes_root / "archive").mkdir(parents=True)
    specs_root = tmp_path / "openspec" / "specs"
    specs_root.mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

当前无。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    import scripts.check_openspec_artifacts as mod

    monkeypatch.setattr(
        mod,
        "_changed_paths_since_base",
        lambda repo_root, base_ref, require_base=False: ({"docs/known-issues.md"}, None),
    )

    exit_code = main(
        [
            "--changes-root",
            str(changes_root),
            "--current-specs-root",
            str(specs_root),
            "--backlog",
            str(backlog),
            "--base-ref",
            "master",
        ]
    )

    assert exit_code == 1


def test_require_base_fails_closed_when_base_unresolvable(tmp_path, monkeypatch):
    """Regression (grill Q5): with --require-base, a failed git diff (e.g. on a
    shallow checkout missing the base ref) must fail the gate instead of
    silently passing."""
    changes_root = tmp_path / "openspec" / "changes"
    (changes_root / "archive").mkdir(parents=True)
    specs_root = tmp_path / "openspec" / "specs"
    specs_root.mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

当前无。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    import scripts.check_openspec_artifacts as mod

    # Simulate a shallow checkout where the base ref cannot be resolved.
    monkeypatch.setattr(
        mod,
        "_changed_paths_since_base",
        lambda repo_root, base_ref, require_base=False: (
            set(),
            f"could not resolve base ref '{base_ref}'",
        ),
    )

    exit_code = main(
        [
            "--changes-root",
            str(changes_root),
            "--current-specs-root",
            str(specs_root),
            "--backlog",
            str(backlog),
            "--base-ref",
            "origin/main",
            "--require-base",
        ]
    )

    assert exit_code == 1


def test_require_base_defaults_to_best_effort_warning(tmp_path, monkeypatch, capsys):
    """Without --require-base, an unresolvable base ref is a warning, not an
    error (local best-effort mode)."""
    changes_root = tmp_path / "openspec" / "changes"
    (changes_root / "archive").mkdir(parents=True)
    specs_root = tmp_path / "openspec" / "specs"
    specs_root.mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        """# OpenSpec Change 实现队列

## 未实现队列

当前无。

## 已完成待归档

当前无。
""",
        encoding="utf-8",
    )

    import scripts.check_openspec_artifacts as mod

    monkeypatch.setattr(
        mod,
        "_changed_paths_since_base",
        lambda repo_root, base_ref, require_base=False: (
            set(),
            "could not resolve base ref 'origin/main'",
        ),
    )

    exit_code = main(
        [
            "--changes-root",
            str(changes_root),
            "--current-specs-root",
            str(specs_root),
            "--backlog",
            str(backlog),
            "--base-ref",
            "origin/main",
        ]
    )

    assert exit_code == 0
    assert "WARNING: could not resolve base ref" in capsys.readouterr().err



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

- research_tier: full
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

- research_tier: full
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
        "change-ui: tasks.md missing pre-implementation batch-grill-me (grill-with-docs) or equivalent design review task"
    ]


def test_grill_evidence_passes_design_review(tmp_path):
    """issue #95：结构化 grill 证据（reviews/grill-design.md + ≥3 决策）通过。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n"
        "- **决策**: 方案A；理由: 简单；来源: run-1\n"
        "- **决策**: 方案B；理由: 可靠；来源: run-1\n"
        "- **决策**: 方案C；理由: 已验证；来源: run-1\n"
        "## Open Questions\n- 无\n",
        encoding="utf-8",
    )

    errors = check_change(change)
    assert not any("design review" in e or "grill" in e.lower() for e in errors), errors


def test_grill_evidence_insufficient_fails(tmp_path):
    """issue #95：grill 证据 <3 条决策 → 报错。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n- **决策**: 只有一条\n",
        encoding="utf-8",
    )

    errors = check_change(change)
    assert any("Confirmed Decisions" in e for e in errors), errors


def test_grill_evidence_without_design_marker_passes(tmp_path):
    """issue #95：有结构化证据但 tasks 无 batch-grill 字样 → 仍通过（证据优先）。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n"
        "- **决策**: A；理由: a；来源: r1\n"
        "- **决策**: B；理由: b；来源: r1\n"
        "- **决策**: C；理由: c；来源: r1\n",
        encoding="utf-8",
    )

    errors = check_change(change)
    assert not any("design review" in e or "grill" in e.lower() for e in errors), errors


def test_completed_change_literal_marker_without_evidence_fails(tmp_path):
    """issue #95：已完成 change（tasks 全勾选 + spec delta）有字面 marker 但无
    reviews/grill-design.md → 报错（纸糊的墙被堵住）。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [x] 开发前使用 batch-grill-me。\n\n- [x] 完成项。\n")
    write_spec_delta(change, "web-ui")

    errors = check_change(change)
    assert any("grill-design.md missing" in e for e in errors), errors


def test_incomplete_change_literal_marker_without_evidence_passes(tmp_path):
    """issue #95：未完成 change（tasks 未全勾选）有字面 marker → 不强制证据（存量不误伤）。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [x] 开发前使用 batch-grill-me。\n\n- [ ] 待完成项。\n")
    write_spec_delta(change, "web-ui")

    errors = check_change(change)
    assert not any("grill-design.md missing" in e for e in errors), errors


# ── grill 用户确认门禁（grill-confirmation-gate）────────────────────────

_UC_DECISIONS = (
    "## Confirmed Decisions\n"
    "- **决策**：A；理由: a；来源: r1\n"
    "- **决策**：B；理由: b；来源: r1\n"
    "- **决策**：C；理由: c；来源: r1\n"
)


def _grill_evidence(tmp_path, body: str, tasks_all_checked: bool = True) -> Path:
    """Create a feature change with grill-design.md and (optionally) checked tasks."""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(change, proposal_for("feature"), design=VALID_DESIGN)
    tasks = "## 1. 规格\n\n- [x] 完成项。\n" if tasks_all_checked else "## 1. 规格\n\n- [ ] 待完成项。\n"
    write_tasks(change, tasks)
    write_spec_delta(change, "web-ui")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(_UC_DECISIONS + body, encoding="utf-8")
    return change


def test_grill_completed_change_unconfirmed_open_question_fails(tmp_path):
    """grill-confirmation-gate：tasks 全勾选 + Open Question 无确认记录 → 报错。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n2. 问题二\n"
        "## User Confirmation\n- **Q1**: 用户答复：已确认做 A；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q2" in e for e in errors), errors


def test_grill_completed_change_all_open_questions_confirmed_passes(tmp_path):
    """grill-confirmation-gate：tasks 全勾选 + Open Questions 全部有确认记录 → 通过。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n2. 问题二\n"
        "## User Confirmation\n"
        "- **Q1**: 用户答复：做 A；确认时间: 2026-08-02\n"
        "- **Q2**: 用户答复：做 B；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert not any("未确认" in e for e in errors), errors


def test_grill_placeholder_confirmation_does_not_count(tmp_path):
    """grill-confirmation-gate Q1：占位确认（待主 agent 提交）不得计入已确认 → 报错。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n"
        "## User Confirmation\n- **Q1**: 用户答复：待主 agent 提交用户确认；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q1" in e for e in errors), errors


def test_grill_duplicate_confirmation_indexes_do_not_cover_missing(tmp_path):
    """grill-confirmation-gate Q5：Q1,Q2,Q3,Q3,Q3 条数够但 Q4 缺失 → 报错。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n2. 问题二\n3. 问题三\n4. 问题四\n"
        "## User Confirmation\n"
        "- **Q1**: 用户答复：a；确认时间: 2026-08-02\n"
        "- **Q2**: 用户答复：b；确认时间: 2026-08-02\n"
        "- **Q3**: 用户答复：c；确认时间: 2026-08-02\n"
        "- **Q3**: 用户答复：c；确认时间: 2026-08-02\n"
        "- **Q3**: 用户答复：c；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q4" in e for e in errors), errors


def test_grill_incomplete_change_unconfirmed_open_question_passes(tmp_path):
    """grill-confirmation-gate：tasks 未全勾选 + 未确认 Open Question → 不报错（开发中可澄清）。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n",
        tasks_all_checked=False,
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert not any("未确认" in e for e in errors), errors


def test_grill_completed_change_missing_confirmation_section_fails(tmp_path):
    """grill-confirmation-gate：tasks 全勾选 + 有 Open Questions 但无 User Confirmation 节 → 报错。"""
    _grill_evidence(tmp_path, "## Open Questions\n1. 问题一\n")
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q1" in e for e in errors), errors


def test_grill_empty_open_questions_skips_confirmation(tmp_path):
    """grill-confirmation-gate：Open Questions 为空（- 无）→ 无需确认记录，通过。"""
    _grill_evidence(tmp_path, "## Open Questions\n- 无\n")
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert not any("未确认" in e for e in errors), errors


def test_grill_punctuation_variant_confirmation_not_counted(tmp_path):
    """grill-confirmation-gate M1：标点/空白变体（待确认。/待主agent提交）不得计入确认。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n"
        "## User Confirmation\n- **Q1**: 用户答复：待确认。；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q1" in e for e in errors), errors


def test_grill_no_space_variant_confirmation_not_counted(tmp_path):
    """grill-confirmation-gate M1：无空格变体（待主agent提交）不得计入确认。"""
    _grill_evidence(
        tmp_path,
        "## Open Questions\n1. 问题一\n"
        "## User Confirmation\n- **Q1**: 用户答复：待主agent提交；确认时间: 2026-08-02\n",
    )
    errors = check_change(tmp_path / "openspec" / "changes" / "change-ui")
    assert any("未确认" in e and "Q1" in e for e in errors), errors


def test_grill_evidence_fullwidth_colon_passes(tmp_path):
    """issue #95：全角冒号列表项格式（- **决策**：）3 条 → 通过（实际证据格式）。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n"
        "- **决策**：方案A；理由: a；来源: r1\n"
        "- **决策**：方案B；理由: b；来源: r1\n"
        "- **决策**：方案C；理由: c；来源: r1\n",
        encoding="utf-8",
    )

    errors = check_change(change)
    assert not any("design review" in e or "grill" in e.lower() for e in errors), errors


def test_grill_evidence_headings_only_fails(tmp_path):
    """issue #95：只有 ### Decision N: 标题、无规范列表项 → 不满足 ≥3 证据阈值。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(
        change,
        proposal_for("feature"),
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n"
        "### Decision 1: 方案A\n"
        "### Decision 2: 方案B\n"
        "### Decision 3: 方案C\n",
        encoding="utf-8",
    )

    errors = check_change(change)
    assert any("Confirmed Decisions" in e for e in errors), errors


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
    write_review_evidence(tmp_path, "change-ui")

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
    write_review_evidence(tmp_path, "change-ui")

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
    write_review_evidence(tmp_path, "change-ui")

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

- research_tier: full
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

- research_tier: exempt
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


# --- research_tier 结构门槛（2.1）与 exempt 证据校验（2.2）---


def test_research_tier_missing_rejected_in_proposal_phase(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- status: enabled
- reason: Relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md section must declare "
        "`research_tier: full|light|exempt`: ## Reference Implementation Research"
    ]


def test_research_tier_invalid_value_rejected_in_proposal_phase(tmp_path):
    change = tmp_path / "change-process"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: deep
- status: enabled
- reason: Relevant.
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == [
        "change-process: proposal.md section has invalid research_tier `deep` "
        "(allowed: full, light, exempt)"
    ]


@pytest.mark.parametrize("tier,status", [("full", "enabled"), ("light", "enabled"), ("exempt", "disabled")])
def test_research_tier_valid_values_pass_structure_gate(tmp_path, tier, status):
    change = tmp_path / f"change-{tier}"
    rir = f"""## Reference Implementation Research

- research_tier: {tier}
- status: {status}
- reason: {"上游决策锁定" if tier == "exempt" else "Relevant."}
"""
    if tier != "exempt":
        rir += """- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
"""
    write_change(
        change,
        proposal_for("process", reference_research=False) + rir,
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == []


def test_light_tier_research_questions_optional(tmp_path):
    """light 档可省略 research questions（D2 + spec 口径），proposal 阶段与
    tasks 全勾完成时均通过（review-loop Round 1 issue 回归）。"""
    rir = """## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 常规功能增强，成熟模式局部应用。
- findings:
  - Comparable repositories use documented gates; local application is routine.
- design impact:
  - The change records a mechanical gate.
"""
    change = tmp_path / "change-light-proposal"
    write_change(
        change,
        proposal_for("process", reference_research=False) + rir,
        design=VALID_DESIGN,
    )
    write_tasks(change, "## 1. 规格\n\n- [ ] 开发前使用等价设计追问。\n")

    assert check_change(change) == []

    completed = tmp_path / "change-light-completed"
    write_change(
        completed,
        proposal_for("process", reference_research=False) + rir,
        design=VALID_DESIGN,
    )
    write_tasks(completed, ALL_TASKS_CHECKED)

    assert check_change(completed) == []


def test_exempt_reason_structural_keyword_passes_when_tasks_complete(tmp_path):
    change = tmp_path / "change-exempt-keyword"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 纯 bugfix，无新增能力面，带回归测试。
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    assert check_change(change) == []


def test_exempt_reason_issue_reference_passes_when_tasks_complete(tmp_path):
    change = tmp_path / "change-exempt-issue"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 方案已在 #128 决策 issue 完整讨论并记录，无待定设计项。
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    assert check_change(change) == []


def test_exempt_reason_review_path_reference_passes_when_tasks_complete(tmp_path):
    change = tmp_path / "change-exempt-path"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 决策已记录于 docs/adr/0007-gate.md，无待定设计项。
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    assert check_change(change) == []


def test_exempt_reason_placeholder_rejected_when_tasks_complete(tmp_path):
    change = tmp_path / "change-exempt-placeholder"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 待确认。
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    errors = check_change(change)
    assert len(errors) == 1
    assert "命中「自认未完成」短语「待确认」" in errors[0]


def test_exempt_reason_empty_rejected_when_tasks_complete(tmp_path):
    change = tmp_path / "change-exempt-empty"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason:
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    errors = check_change(change)
    assert any("must include non-empty `reason`" in e for e in errors)


def test_exempt_reason_without_evidence_rejected_when_tasks_complete(tmp_path):
    """判断性豁免示例「与已有模块 X 等价改造」无引用 → 证据校验拒绝（Q3 口径）。"""
    change = tmp_path / "change-exempt-noevidence"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 与已有模块 X 等价改造。
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    errors = check_change(change)
    assert len(errors) == 1
    assert "exempt 证据校验不通过" in errors[0]


# --- full/light 内容门槛（2.3）与阶段感知（2.4）---


def test_full_tier_incomplete_findings_rejected_when_tasks_complete(tmp_path):
    change = tmp_path / "change-full-incomplete"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 引入新协议。
- research questions:
  - Which patterns are reusable?
- findings:
  - 业界调研尚未完成。
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    errors = check_change(change)
    assert any("findings" in e and "尚未完成" in e for e in errors)


def test_full_tier_status_disabled_rejected_when_tasks_complete(tmp_path):
    change = tmp_path / "change-full-disabled"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: full
- status: disabled
- reason: 调研在途。
- research questions:
  - Which patterns are reusable?
- findings:
  - Comparable repositories use documented gates.
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(change, ALL_TASKS_CHECKED)

    errors = check_change(change)
    assert any("status" in e and "disabled" in e for e in errors)


def test_full_tier_status_disabled_allowed_in_proposal_phase(tmp_path):
    change = tmp_path / "change-full-disabled-proposal"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: full
- status: disabled
- reason: 调研在途。
- research questions:
  - Which patterns are reusable?
- findings:
  - 业界调研尚未完成。
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n- [x] 1.1 完成。\n- [ ] 1.2 未完成。\n"
        "- [x] 开发前使用等价设计追问。\n",
    )

    assert check_change(change) == []


def test_structure_gate_only_when_tasks_not_complete(tmp_path):
    """阶段感知：tasks 未全勾时不触发 full/light 内容门槛。"""
    change = tmp_path / "change-stage-aware"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

- research_tier: full
- status: disabled
- reason: 调研在途。
- research questions:
  - Which patterns are reusable?
- findings:
  - 业界调研尚未完成。
- design impact:
  - The change records a mechanical gate.
""",
        design=VALID_DESIGN,
    )
    write_tasks(
        change,
        "## 1. 规格\n\n- [x] 1.1 完成。\n- [ ] 1.2 未完成。\n"
        "- [x] 开发前使用等价设计追问。\n",
    )

    assert check_change(change) == []


def test_active_change_without_tier_reports_clear_error(tmp_path):
    """2.6 存量非 docs change 缺 research_tier → 结构门槛报错信息清晰可修。"""
    change = tmp_path / "legacy-change"
    write_change(
        change,
        proposal_for("process", reference_research=False)
        + """## Reference Implementation Research

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
    write_tasks(change, "## 1. 规格\n\n- [ ] 1.1 完成。\n")

    errors = check_change(change)
    assert any("must declare `research_tier: full|light|exempt`" in e for e in errors)


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


def test_change_id_from_dir_name_strips_date_prefix():
    """Regression (grill Q6): archived dirs are date-prefixed; the bare change
    id must be derived for manifest verification."""
    import scripts.check_openspec_artifacts as mod

    assert mod._change_id_from_dir_name("2026-08-02-long-term-memory-deepening") == "long-term-memory-deepening"
    assert mod._change_id_from_dir_name("long-term-memory-deepening") == "long-term-memory-deepening"


def test_verify_review_manifest_archived_path(tmp_path):
    """Regression (grill Q6): verify_review_manifest must resolve archived
    change paths (openspec/changes/archive/<date>-<id>) for drift detection.

    #232 (A′): archived 语境**不再以 tasks_hash 判失败**（tasks.md 是贯穿到归档
    的活文档，收尾勾选/补行必然使其字节哈希漂移），但**其余校验保留**——该测试
    同时锁住这两侧：tasks 漂移不报错、spec 漂移仍报错。判别性对照（同一漂移在
    active 语境必须报错）见 tests/agent/workflow/test_review_manifest.py。"""
    import json

    from agent.workflow.review_manifest import (
        REVIEW_MANIFEST_SCHEMA,
        artifact_hash,
        file_sha256,
        verify_review_manifest,
    )

    archive = tmp_path / "openspec" / "changes" / "archive" / "2026-08-02-sample-change"
    (archive / "reviews").mkdir(parents=True)
    (archive / "specs").mkdir()
    (archive / "tasks.md").write_text("- [x] task\n", encoding="utf-8")
    report = archive / "reviews" / "building-review.md"
    report.write_text("# Review\n\nPASS\n", encoding="utf-8")

    manifest = {
        "schema": REVIEW_MANIFEST_SCHEMA,
        "change_id": "sample-change",
        "phase": "building",
        "verdict": "PASS",
        "reviewer_run_id": "r1",
        "base_sha": "abc123",
        "head_sha": "def456",
        "tasks_hash": artifact_hash(archive / "tasks.md"),
        "spec_hash": artifact_hash(archive / "specs"),
        "diff_hash": "sha256:unavailable",
        "report_hash": file_sha256(report),
    }
    (archive / "reviews" / "building-review-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    # No git repo here → git-span checks are skipped; content hashes must pass.
    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)
    assert errors == []

    # tasks.md 在归档后仍会被勾选/补行 → archived 语境下该漂移不构成失败。
    (archive / "tasks.md").write_text("- [x] task\n- [x] another\n", encoding="utf-8")
    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)
    assert errors == []

    # 但归档语境的其余校验保留：spec 漂移仍须判失败（本 change 不放过这一侧）。
    (archive / "specs" / "extra.md").write_text("spec changed\n", encoding="utf-8")
    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)
    assert any("spec hash mismatch" in e for e in errors)


# ── workflow-state.json 投影一致性 + 归档可投影（flow-event-projection P1）──


def _seed_gen2_projection(change: Path, *, tamper: bool = False) -> None:
    change.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "schema": "workflow-event/v1",
            "seq": 1,
            "event_type": "change_created",
            "change_id": change.name,
        },
        {
            "schema": "workflow-event/v1",
            "seq": 2,
            "event_type": "backlog_updated",
            "change_id": change.name,
            "artifact_path": "docs/x.md",
        },
    ]
    with (change / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    ws = {
        "schema": "workflow-state/v1",
        "change_id": change.name,
        "state": {"phase": "planning", "sub_state": "exploring"},
        "milestones": [],
        "source_event_seq": 2,
    }
    if tamper:
        ws["state"] = {"phase": "building", "sub_state": "writing_tests"}
    (change / "workflow-state.json").write_text(
        json.dumps(ws, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # gen-1 目标才由写通道刷新 handoff.json；此处手工落盘以构造被检对象
    handoff = {
        "schema_version": "1.0",
        "change_id": change.name,
        "state": ws["state"],
        "transitions": [],
    }
    (change / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def test_check_handoff_json_rejects_gen2_projection_mismatch(tmp_path):
    from scripts.check_openspec_artifacts import _check_handoff_json

    change = tmp_path / "openspec" / "changes" / "projected-change"
    _seed_gen2_projection(change, tamper=True)

    errors = _check_handoff_json(change)

    assert any("workflow-state.json projection does not match workflow-events.jsonl" in e for e in errors)


def test_check_handoff_json_passes_gen2_projection(tmp_path):
    from scripts.check_openspec_artifacts import _check_handoff_json

    change = tmp_path / "openspec" / "changes" / "projected-change"
    _seed_gen2_projection(change)

    assert _check_handoff_json(change) == []


def test_check_handoff_json_gen2_without_disk_projection_passes(tmp_path):
    """gen-2 change 未跑过 flow status（无 workflow-state.json）→ 不报错（可投影即通过）。"""
    from scripts.check_openspec_artifacts import _check_handoff_json

    change = tmp_path / "openspec" / "changes" / "no-projection"
    change.mkdir(parents=True, exist_ok=True)
    (change / "workflow-events.jsonl").write_text(
        json.dumps(
            {"schema": "workflow-event/v1", "seq": 1, "event_type": "change_created", "change_id": "no-projection"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    assert _check_handoff_json(change) == []


def test_check_archived_projectable_passes_with_recognized_types(tmp_path):
    from scripts.check_openspec_artifacts import _check_archived_projectable

    change = tmp_path / "openspec" / "changes" / "archive" / "2026-08-09-web-multi-session-entry"
    change.mkdir(parents=True, exist_ok=True)
    events = [
        {"schema": "workflow-event/v1", "seq": 1, "event_type": "change_created", "change_id": "web-multi-session-entry"},
        {"schema": "workflow-event/v1", "seq": 2, "event_type": "backlog_updated", "change_id": "web-multi-session-entry", "artifact_path": "docs/x.md"},
        {"schema": "workflow-event/v1", "seq": 3, "event_type": "grill_completed", "change_id": "web-multi-session-entry"},
        {"schema": "workflow-event/v1", "seq": 4, "event_type": "change_archived", "change_id": "web-multi-session-entry", "artifact_path": "openspec/changes/archive/x"},
    ]
    with (change / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    assert _check_archived_projectable(change) == []


def test_check_archived_projectable_rejects_unknown_event(tmp_path):
    from scripts.check_openspec_artifacts import _check_archived_projectable

    change = tmp_path / "openspec" / "changes" / "archive" / "2026-08-09-broken"
    change.mkdir(parents=True, exist_ok=True)
    events = [
        {"schema": "workflow-event/v1", "seq": 1, "event_type": "change_created", "change_id": "broken"},
        {"schema": "workflow-event/v1", "seq": 2, "event_type": "mystery_event", "change_id": "broken"},
    ]
    with (change / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    errors = _check_archived_projectable(change)

    assert any("不可投影" in e for e in errors)


def test_check_archived_no_seed_projectable(tmp_path):
    """gen-0 归档（backlog_updated 开头，无 seed）→ 结构合法即可投影，不抛错。"""
    from scripts.check_openspec_artifacts import _check_archived_projectable

    change = tmp_path / "openspec" / "changes" / "archive" / "2026-08-01-gen0"
    change.mkdir(parents=True, exist_ok=True)
    events = [
        {"schema": "workflow-event/v1", "seq": 1, "event_type": "backlog_updated", "change_id": "gen0", "artifact_path": "docs/x.md"},
        {"schema": "workflow-event/v1", "seq": 2, "event_type": "current_spec_synced", "change_id": "gen0", "artifact_path": "openspec/specs/x.md"},
    ]
    with (change / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    assert _check_archived_projectable(change) == []


def _write_archived_change_with_manifest(changes_root, dir_name, change_id):
    """Build an archived change whose manifest has drifted tasks_hash.

    The manifest deliberately records a stale ``tasks_hash`` (post-PASS 勾选漂移
    的等价物) so the archive path must tolerate it while still checking the rest.
    """
    from agent.workflow.review_manifest import artifact_hash, file_sha256

    change = changes_root / "archive" / dir_name
    (change / "reviews").mkdir(parents=True)
    (change / "specs").mkdir()
    (change / "tasks.md").write_text("- [x] task\n- [x] added during closing\n", encoding="utf-8")
    (change / "proposal.md").write_text("# Proposal\n\n## Change Type\n\n- primary: process\n", encoding="utf-8")
    report = change / "reviews" / "building-review.md"
    report.write_text("# Review\n\nPASS\n", encoding="utf-8")
    manifest = {
        "schema": "review-manifest/v1",
        "change_id": change_id,
        "phase": "building",
        "verdict": "PASS",
        "reviewer_run_id": "r1",
        "base_sha": "abc123",
        "head_sha": "def456",
        "tasks_hash": "sha256:stale-does-not-match",
        "spec_hash": artifact_hash(change / "specs"),
        "diff_hash": "sha256:unavailable",
        "report_hash": file_sha256(report),
    }
    (change / "reviews" / "building-review-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return change


def test_check_archived_prints_visible_tasks_hash_skip_summary(tmp_path, capsys):
    """#232 B（A′ 的可见性）：--check-archived 必须 exit 0（tasks 漂移被降级），
    且在 stderr 输出**一行**汇总说明，证明降级不静默。

    这条锁住「降级可见」落在调用方而非返回值：若 note 混进 verify_review_manifest
    的返回列表，它会被 `errors.extend` 收走 → 打成 ERROR → exit 1，本用例转红。
    """
    from scripts.check_openspec_artifacts import main

    changes_root = tmp_path / "openspec" / "changes"
    _write_archived_change_with_manifest(changes_root, "2026-08-02-sample-change", "sample-change")

    exit_code = main(
        [
            "--changes-root",
            str(changes_root),
            "--check-archived",
            "--skip-protected-paths",
            "--skip-backlog",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "tasks_hash 已按归档语境跳过" in captured.err
    assert captured.err.count("tasks_hash 已按归档语境跳过") == 1
    assert "ERROR" not in captured.err


def test_check_archived_still_fails_on_spec_drift(tmp_path, capsys):
    """A′ 只放宽 tasks_hash：归档 change 的 spec_hash 漂移仍须 exit 1。"""
    from scripts.check_openspec_artifacts import main

    changes_root = tmp_path / "openspec" / "changes"
    change = _write_archived_change_with_manifest(changes_root, "2026-08-02-sample-change", "sample-change")
    # 归档后改 specs → spec_hash 漂移（manifest 绑定的是改动前的哈希）。
    (change / "specs" / "extra.md").write_text("changed\n", encoding="utf-8")

    exit_code = main(
        [
            "--changes-root",
            str(changes_root),
            "--check-archived",
            "--skip-protected-paths",
            "--skip-backlog",
        ]
    )

    assert exit_code == 1
    assert "spec hash mismatch" in capsys.readouterr().err


def _yaml_step_containing(text: str, needle: str) -> str:
    """Return the YAML step block (``- name:`` … next ``- name:``) holding needle,
    with YAML comment lines removed.

    绑定到 step 结构而非整文件子串；**剥掉注释行**是关键——否则 step 内解释
    参数的注释会冒充真正的命令行参数，让「flag 被从命令里删掉」探测不到。
    """
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if needle in line),
        None,
    )
    assert start is not None, f"{needle!r} not found in ci.yml"
    step_start = next(
        (i for i in range(start, -1, -1) if lines[i].lstrip().startswith("- name:")),
        0,
    )
    step_end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("- name:")),
        len(lines),
    )
    block = lines[step_start:step_end]
    return "\n".join(line for line in block if not line.lstrip().startswith("#"))


def test_ci_validate_job_runs_check_archived():
    """D4：CI 的 validate job 必须运行 --check-archived 且参数钉死
    （--skip-protected-paths / --skip-backlog，避免默认 --base-ref master 在 CI
    上解析失败打出无意义 WARNING 与重复检查）。防该步骤被无声移除或参数退化。

    断言的 flag 必须出现在**命令行**（注释已剥离），且三条同属一个 step。"""
    ci = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")

    assert "--check-archived" in text, "CI 缺少归档 manifest 校验步骤"
    step = _yaml_step_containing(text, "--check-archived")

    # 门禁不得被弱化：不接受 continue-on-error / 条件跳过。
    assert "continue-on-error" not in step
    assert "|| true" not in step

    # 参数钉死：同 step 的命令行必须带这两个 skip flag。
    assert "--skip-protected-paths" in step
    assert "--skip-backlog" in step
    # 且确实在跑 checker 脚本。
    assert "check_openspec_artifacts.py" in step


# ── issue #235: 完成度门禁改挂归档点 ──────────────────────────────────
#
# 三条判别性主线（缺任何一条，本 change 就退化成「看起来在工作」）：
#   1. 触发必须用 --diff-filter=AR（纯 rename 归档 git 报 R，A-only 会漏）
#   2. 触发必须叠「该归档目录在 base 树不存在」（否则往旧归档补文件会误伤旧 change）
#   3. 四道门在归档侧必须**不因 tasks 未全勾而降级**（A′ 的 assume_implemented）


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def _git_commit(repo: Path, message: str) -> str:
    _git_out(repo, "add", "-A")
    _git_out(repo, "commit", "-qm", message)
    return _git_out(repo, "rev-parse", "HEAD").strip()


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git_out(repo, "init", "-q", ".")
    _git_out(repo, "config", "user.email", "t@t")
    _git_out(repo, "config", "user.name", "t")
    _git_out(repo, "config", "commit.gpgsign", "false")


def test_archived_gate_ar_catches_pure_rename_where_a_only_misses(tmp_path):
    """D1：整目录 `git mv` 归档时 git 报 R，`--diff-filter=A` 输出为空 ⇒ 必须用 AR。"""
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    change = tmp_path / "openspec" / "changes" / "my-change"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("x\n", encoding="utf-8")
    base = _git_commit(tmp_path, "base")

    (tmp_path / "openspec" / "changes" / "archive").mkdir(parents=True)
    _git_out(
        tmp_path, "mv",
        "openspec/changes/my-change",
        "openspec/changes/archive/2026-09-23-my-change",
    )
    _git_commit(tmp_path, "archive")

    # A-only 漏掉（这正是必须 AR 的原因）
    a_only = _git_out(tmp_path, "diff", "--name-only", "--diff-filter=A", base, "--")
    assert "openspec/changes/archive/2026-09-23-my-change/proposal.md" not in a_only

    new_dirs, bad_paths, warning = mod._new_archive_dirs_since_base(tmp_path, base)
    assert new_dirs == ["2026-09-23-my-change"]
    assert bad_paths == []
    assert warning is None


def test_archived_gate_ar_catches_same_pr_create_then_move(tmp_path):
    """D1 的 A 侧：源目录不在 base 树（同 PR 内先建后 mv）时 git 报 A，AR 同样取到。"""
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    base = _git_commit(tmp_path, "base")

    archive = tmp_path / "openspec" / "changes" / "archive" / "2026-09-24-fresh"
    archive.mkdir(parents=True)
    (archive / "proposal.md").write_text("x\n", encoding="utf-8")
    _git_commit(tmp_path, "add archived change directly")

    new_dirs, _, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert new_dirs == ["2026-09-24-fresh"]


def test_archived_gate_ignores_file_added_to_existing_archive(tmp_path):
    """grill 风险②：往**既有**归档目录补文件会产出 A 路径，但不得当成「本 PR 新归档」。

    #234/#236/#238 干的正是「给归档补 manifest」——不叠「base 树不存在」条件
    就会对旧的、不该追溯的 change 求值四道门（实测 89 个归档里 69 个会红）。
    """
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    old = tmp_path / "openspec" / "changes" / "archive" / "2026-09-01-old-change"
    old.mkdir(parents=True)
    (old / "proposal.md").write_text("x\n", encoding="utf-8")
    base = _git_commit(tmp_path, "旧归档已存在")

    # 后续 PR 补一份 manifest —— 这是 A 路径，正则也会命中
    (old / "reviews").mkdir()
    (old / "reviews" / "building-review-manifest.json").write_text("{}", encoding="utf-8")
    _git_commit(tmp_path, "补 manifest")

    a_only = _git_out(tmp_path, "diff", "--name-only", "--diff-filter=A", base, "--")
    assert "2026-09-01-old-change" in a_only  # 反证：A 路径确实出现

    new_dirs, bad_paths, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert new_dirs == [], "旧归档目录被误判成本 PR 新归档"
    assert bad_paths == []


def test_archived_gate_reports_non_conforming_archive_dir(tmp_path):
    """Q5：`archive/<id>/`（缺日期前缀）既不匹配正则、又被 active 迭代排除
    ⇒ 会落进「谁都不管」的静默面，必须报错。"""
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    base = _git_commit(tmp_path, "base")

    bad_dir = tmp_path / "openspec" / "changes" / "archive" / "foo"
    bad_dir.mkdir(parents=True)
    (bad_dir / "proposal.md").write_text("x\n", encoding="utf-8")
    _git_commit(tmp_path, "漏日期前缀的归档")

    new_dirs, bad_paths, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert new_dirs == []
    assert "openspec/changes/archive/foo/proposal.md" in bad_paths


def _archived_change(
    tmp_path: Path,
    dir_name: str,
    *,
    change_type: str = "feature",
    tasks: str = "## 1. 实现\n\n- [x] 做完。\n",
    spec_delta: str | None = "web-ui",
    design: str | None = VALID_DESIGN,
    grill: str | None = None,
    building_review: bool = False,
) -> Path:
    """构造一个归档目录下的 change（无 git，供门评估单测用）。"""
    change = tmp_path / "openspec" / "changes" / "archive" / dir_name
    write_change(change, proposal_for(change_type), design=design)
    write_tasks(change, tasks)
    if spec_delta:
        write_spec_delta(change, spec_delta)
    if grill is not None:
        review_dir = change / "reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "grill-design.md").write_text(grill, encoding="utf-8")
    if building_review:
        review_dir = change / "reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "building-review.md").write_text("## Verdict\n\n**PASS**\n", encoding="utf-8")
    return change


GRILL_EVIDENCE_OK = """# Grill

## Confirmed Decisions

- **决策**: 决策一；理由: 理由一；来源: run-1
- **决策**: 决策二；理由: 理由二；来源: run-1
- **决策**: 决策三；理由: 理由三；来源: run-1

## Open Questions

- 无
"""


def test_archived_gate_flags_missing_building_review(tmp_path):
    """问题二：本 PR 新归档的非 docs change 缺 building-review.md → 门触发。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path, "2026-09-23-demo", grill=GRILL_EVIDENCE_OK, building_review=False
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("building-review.md missing" in e for e in errors), errors


def test_archived_gate_flags_untagged_unchecked_task(tmp_path):
    """问题一：未勾且未标 (post-merge) 的任务 → 报错（不得静默）。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [x] 做完。\n- [ ] 忘了勾的一项。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("忘了勾的一项" in e for e in errors), errors


def test_archived_gate_post_merge_tag_exempts_unchecked_task(tmp_path):
    """同一 fixture 加 (post-merge) → 不报。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [x] 做完。\n- [ ] (post-merge) PR 合入后关 issue。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("post-merge" in e for e in errors), errors
    assert not any("未勾" in e for e in errors), errors


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] (post-merge) 收尾",
        "- [ ] 5.5 (post-merge) 收尾",
        "- [ ] **6.9** (post-merge) 收尾",
        "- [ ] （post-merge）收尾",       # 全角括号
        "- [ ] (POST-MERGE) 收尾",        # 大小写
        "+ [ ] (post-merge) 收尾",        # + 标记
        "* [ ] (post-merge) 收尾",        # * 标记
        "  - [ ] (post-merge) 收尾",      # 缩进子项
    ],
)
def test_archived_gate_tag_syntax_variants_all_exempt(tmp_path, line):
    """D4：tag 语法 8 变体全部识别为豁免（编号/粗体在前、全半角括号、大小写、标记符、缩进）。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks=f"## 1. 实现\n\n- [x] 做完。\n{line}\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("未勾" in e for e in errors), (line, errors)


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] 收尾（无 tag）",
        "- [ ] (pre-merge) 收尾",
        "- [ ] post-merge 无括号",
    ],
)
def test_archived_gate_tag_negative_cases_still_reported(tmp_path, line):
    """D4 反例：无 tag / 错 tag / 缺括号 → 仍算未完成。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks=f"## 1. 实现\n\n- [x] 做完。\n{line}\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("未勾" in e for e in errors), (line, errors)


def test_archived_gate_requires_grill_evidence_even_when_tasks_incomplete(tmp_path):
    """Q1b / A′ 的判别性断言：归档侧四道门**不因 tasks 未全勾而降级**。

    这是整个 change 的核心——不修的话，归档 change 只要留一条未勾任务，
    grill 证据门就静默返回空（绿着归档），正是 issue #235 要堵的洞。
    """
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        # tasks 里带 batch-grill 字面标记，且有一条未勾 —— 正是「静默通过」的形态
        tasks="## 1. 实现\n\n- [x] 跑 batch-grill-me。\n- [ ] 一条无 tag 未勾任务。\n",
        grill=None,
        building_review=True,
    )

    # active 语义（假定未实现）：字面标记兜底 → 静默通过，这就是被绕开的路径
    from scripts.check_openspec_artifacts import _check_design_review_task, parse_change_type

    proposal_text = (change / "proposal.md").read_text(encoding="utf-8")
    change_type = parse_change_type(proposal_text)[0]
    assert _check_design_review_task(change, change_type) == []

    # 归档语义（A′）：必须报 grill 证据缺失
    errors = mod._check_archived_completion_gate(change)
    assert any("reviews/grill-design.md missing" in e for e in errors), errors


def test_archived_gate_flags_unconfirmed_open_question_when_tasks_incomplete(tmp_path):
    """A′：归档侧的 OpenQuestion 确认覆盖同样不因未全勾而降级。"""
    import scripts.check_openspec_artifacts as mod

    grill = GRILL_EVIDENCE_OK.replace(
        "## Open Questions\n\n- 无\n", "## Open Questions\n\n- **Q1**: 未决项。\n"
    )
    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [x] 做完。\n- [ ] 一条未勾任务。\n",
        grill=grill,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("未确认的 Open Question" in e for e in errors), errors


def test_archived_gate_rir_content_threshold_applies_when_tasks_incomplete(tmp_path):
    """A′：RIR 内容门槛（含 tier↔status 闭环）在归档侧不因未全勾而降级。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [x] 做完。\n- [ ] 一条未勾任务。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    # exempt + enabled 不闭环（tasks 未全勾时 active 侧不报）
    proposal = (change / "proposal.md").read_text(encoding="utf-8")
    proposal = proposal.replace("research_tier: full", "research_tier: exempt")
    (change / "proposal.md").write_text(proposal, encoding="utf-8")

    errors = mod._check_archived_completion_gate(change)
    assert any("tier/status" in e or "exempt" in e for e in errors), errors


def test_archived_gate_docs_only_archive_is_exempt(tmp_path):
    """Q1a：docs-only 归档 → 四道门都不要求（豁免继承）。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-docs-only",
        change_type="docs",
        tasks="## 1. 文档\n\n- [ ] 一条未勾的文档任务。\n",
        spec_delta=None,
        design=None,
        grill=None,
        building_review=False,
    )
    errors = mod._check_archived_completion_gate(change)
    # docs 豁免四道门；未 tag 的未勾任务仍报（那是任务约定，不属四道门豁免面）
    assert not any("building-review.md missing" in e for e in errors), errors
    assert not any("grill-design.md missing" in e for e in errors), errors
    assert not any("Reference Implementation Research" in e for e in errors), errors


def test_archived_gate_bugfix_archive_is_exempt_from_grill(tmp_path):
    """Q1a：bugfix 不在 DESIGN_TYPES → 不要求 grill 证据（豁免继承）。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-bugfix",
        change_type="bugfix",
        tasks="## 1. 修复\n\n- [x] 修完。\n",
        grill=None,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("grill-design.md missing" in e for e in errors), errors


def test_archived_gate_no_spec_delta_does_not_require_building_review(tmp_path):
    """D2 继承的 `_changed_capabilities` 豁免：无 spec delta → 不要求 building-review。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        spec_delta=None,
        tasks="## 1. 实现\n\n- [x] 做完。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=False,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("building-review.md missing" in e for e in errors), errors


def _minimal_changes_root(tmp_path: Path) -> Path:
    changes_root = tmp_path / "openspec" / "changes"
    (changes_root / "archive").mkdir(parents=True)
    specs_root = tmp_path / "openspec" / "specs"
    specs_root.mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir(parents=True, exist_ok=True)
    backlog.write_text(
        "# OpenSpec Change 实现队列\n\n## 未实现队列\n\n当前无。\n\n## 已完成待归档\n\n当前无。\n",
        encoding="utf-8",
    )
    return changes_root


def _main_args(changes_root: Path, tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--changes-root", str(changes_root),
        "--current-specs-root", str(tmp_path / "openspec" / "specs"),
        "--backlog", str(tmp_path / "docs" / "openspec-change-backlog.md"),
        *extra,
    ]


def test_main_runs_archived_gate_with_skip_protected_paths(tmp_path, monkeypatch):
    """D6：新门**不能**被 `--skip-protected-paths` 关掉（它必须在该块之外）。

    CI 第二步同时也传这个 flag，若新门放在块内，该 flag 就成了事实上的
    区分开关，与 D6 明文冲突。
    """
    import scripts.check_openspec_artifacts as mod

    changes_root = _minimal_changes_root(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        mod, "_check_new_archived_completion_gates",
        lambda *a, **k: calls.append("called") or [],
    )

    exit_code = main(
        _main_args(changes_root, tmp_path, "--skip-protected-paths", "--skip-backlog")
    )

    assert calls == ["called"], "新门被 --skip-protected-paths 关掉了"
    assert exit_code == 0


def test_main_skips_archived_gate_in_check_archived_mode(tmp_path, monkeypatch):
    """D6：`--check-archived` 模式不触发新门（守 48 个历史归档的爆炸半径）。"""
    import scripts.check_openspec_artifacts as mod

    changes_root = _minimal_changes_root(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        mod, "_check_new_archived_completion_gates",
        lambda *a, **k: calls.append("called") or [],
    )

    main(_main_args(changes_root, tmp_path, "--check-archived", "--skip-backlog"))

    assert calls == [], "--check-archived 触发了归档点门"


def test_main_skips_archived_gate_for_single_change_mode(tmp_path, monkeypatch):
    """风险小a：`--change <id>` 时跳过新门，避免「以为只查一个 change」却多报。"""
    import scripts.check_openspec_artifacts as mod

    changes_root = _minimal_changes_root(tmp_path)
    only = changes_root / "some-change"
    write_change(only, proposal_for("feature"), design=VALID_DESIGN)
    write_tasks(only, ALL_TASKS_CHECKED)
    write_spec_delta(only, "web-ui")
    calls: list[str] = []
    monkeypatch.setattr(
        mod, "_check_new_archived_completion_gates",
        lambda *a, **k: calls.append("called") or [],
    )

    main(_main_args(changes_root, tmp_path, "--change", "some-change"))

    assert calls == [], "--change 模式触发了归档点门"


def test_archived_gate_fails_closed_when_base_unresolvable(tmp_path, monkeypatch):
    """风险小b：新门独立算 diff，必须自己兑现 --require-base，否则浅检出 fail-open。"""
    import scripts.check_openspec_artifacts as mod

    changes_root = _minimal_changes_root(tmp_path)
    monkeypatch.setattr(
        mod, "_new_archive_dirs_since_base",
        lambda repo_root, base_ref: (
            [], [], f"could not resolve base ref '{base_ref}' for archived completion gate"
        ),
    )

    strict = mod._check_new_archived_completion_gates(
        tmp_path, changes_root, "master", require_base=True
    )
    assert any("could not resolve base ref" in e for e in strict), strict

    # 非严格模式：降级为可见 warning，不报错（与既有 protected-path 行为一致）
    lenient = mod._check_new_archived_completion_gates(
        tmp_path, changes_root, "master", require_base=False
    )
    assert lenient == []


def test_archived_gate_bad_dir_path_is_reported_by_main(tmp_path, monkeypatch):
    """Q5 端到端：非规范归档目录经 main() 进 errors（不是只在 helper 里可见）。"""
    import scripts.check_openspec_artifacts as mod

    changes_root = _minimal_changes_root(tmp_path)
    monkeypatch.setattr(
        mod, "_new_archive_dirs_since_base",
        lambda repo_root, base_ref: (
            [], ["openspec/changes/archive/foo/proposal.md"], None,
        ),
    )

    exit_code = main(
        _main_args(changes_root, tmp_path, "--skip-protected-paths", "--skip-backlog")
    )

    assert exit_code == 1


def test_archived_gate_flags_missing_tasks_md(tmp_path):
    """building-review R1 M1：归档非 docs change 缺 tasks.md → 报错（不得静默）。

    `_untagged_unchecked_tasks` 在文件缺失时返回空 ⇒ 完成度维度唯一证据载体
    消失、门静默通过。这与「留一条 `- [ ]` 自我关闸」同构（靠「不写 checkbox」
    而非「不勾 checkbox」），必须显式报错。
    """
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path, "2026-09-23-demo", grill=GRILL_EVIDENCE_OK, building_review=True
    )
    (change / "tasks.md").unlink()

    errors = mod._check_archived_completion_gate(change)
    assert any("tasks.md 缺失" in e for e in errors), errors


@pytest.mark.parametrize("body", ["这是一段散文，没有任何勾选项。\n", ""])
def test_archived_gate_flags_tasks_md_without_checkbox_lines(tmp_path, body):
    """同上，散文式 / 空 tasks.md（无任何 checkbox 行）同样无从评估完成度。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path, "2026-09-23-demo", grill=GRILL_EVIDENCE_OK, building_review=True
    )
    (change / "tasks.md").write_text(body, encoding="utf-8")

    errors = mod._check_archived_completion_gate(change)
    # 必须钉死**区分性**子串（R4 发现：`"tasks.md" in e` 是恒真项，因为模板里
    # 永远有 "tasks.md"——把消息误退回「缺失」也能绿）。这里要求明确说「无 checkbox 行」。
    assert any("tasks.md 无任何 checkbox 行" in e for e in errors), (body, errors)


def test_archived_gate_flags_all_post_merge_zero_checked(tmp_path):
    """R2 M2：有 checkbox 行但**零勾选**（全标 post-merge）仍能关闸，须报错。

    历史归档里这种形态真实存在（8/93）。「把所有任务都标成 post-merge、一个
    都不勾」与「不写 checkbox」是同一类结构性绕开。
    """
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [ ] (post-merge) 关 issue。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("全部未勾选" in e for e in errors), errors


def test_archived_gate_passes_when_at_least_one_task_checked(tmp_path):
    """反向：只要有一条勾选（其余是带 tag 的 closeout 项）→ 通过，别修成误红。"""
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-demo",
        tasks="## 1. 实现\n\n- [x] 做完。\n- [ ] (post-merge) 关 issue。\n",
        grill=GRILL_EVIDENCE_OK,
        building_review=True,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("归档点无法评估完成度" in e for e in errors), errors


def test_archived_gate_docs_only_missing_tasks_md_is_flagged(tmp_path):
    """R2 low（对称性）：docs 归档缺 tasks.md 也曾放行——「删文件即关闸」的隐含路径。

    语料实测 0/93 个 docs 归档缺 tasks.md，统一口径不产生假阳性。
    """
    import scripts.check_openspec_artifacts as mod

    change = _archived_change(
        tmp_path,
        "2026-09-23-docs-only",
        change_type="docs",
        tasks="## 1. 文档\n\n- [ ] 一条未勾的文档任务。\n",
        spec_delta=None,
        design=None,
        grill=None,
        building_review=False,
    )
    (change / "tasks.md").unlink()

    errors = mod._check_archived_completion_gate(change)
    assert any("tasks.md 缺失" in e for e in errors), errors


def test_archived_gate_does_not_flag_plain_file_under_archive_root(tmp_path):
    """building-review R1 low-1：`archive/.gitkeep` 这类普通文件不是命名不合规的归档目录。"""
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    base = _git_commit(tmp_path, "base")

    archive_root = tmp_path / "openspec" / "changes" / "archive"
    archive_root.mkdir(parents=True)
    (archive_root / ".gitkeep").write_text("", encoding="utf-8")
    (archive_root / "notes.md").write_text("x\n", encoding="utf-8")
    _git_commit(tmp_path, "archive root files")

    new_dirs, non_conforming, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert new_dirs == []
    assert non_conforming == [], "归档根下的普通文件被判成命名不合规"


def test_archived_gate_still_flags_non_dated_archive_directory(tmp_path):
    """收敛判定后，真正的「无日期前缀归档目录」仍须报错（别把修复做成 fail-open）。"""
    import scripts.check_openspec_artifacts as mod

    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    base = _git_commit(tmp_path, "base")

    bad = tmp_path / "openspec" / "changes" / "archive" / "foo"
    bad.mkdir(parents=True)
    (bad / "proposal.md").write_text("x\n", encoding="utf-8")
    _git_commit(tmp_path, "bad archive dir")

    _, non_conforming, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert non_conforming == ["openspec/changes/archive/foo/proposal.md"]


def _change_dir_in_any_form(repo_root: Path, change_id: str) -> Path | None:
    """Locate a change directory in active or archived form (None if neither).

    Reviewers found the first draft of the protected-artifact test hard-coded the
    *active* path, so the mandatory archive move turned it into a
    ``FileNotFoundError`` landmine — and the ``origin/master...HEAD`` trigger
    re-fired for every future PR touching the same file. Resolving both forms
    and keying off tree state (not a remote ref) keeps the check honest wherever
    it runs.
    """
    active = repo_root / "openspec" / "changes" / change_id
    if (active / "workflow-events.jsonl").exists():
        return active
    archive_root = repo_root / "openspec" / "changes" / "archive"
    if archive_root.exists():
        for candidate in sorted(archive_root.glob(f"*-{change_id}")):
            # Glob `*-<id>` is a suffix match, so a decoy such as
            # `2026-01-01-add-<id>` would match too. Require an exact
            # `<date>-<id>` archive name (building-review R3 finding 3).
            if not (candidate / "workflow-events.jsonl").exists():
                continue
            if _strip_archive_date_prefix(candidate.name) != change_id:
                continue
            return candidate
    return None


def _strip_archive_date_prefix(dir_name: str) -> str:
    match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", dir_name)
    return match.group(1) if match else dir_name


def test_change_dir_in_any_form_rejects_suffix_decoy(tmp_path):
    """building-review R3 finding 3：`glob("*-<id>")` 是后缀匹配，诱饵目录会排在前。

    例如 change_id = `fix-issue-235` 时，`2026-01-01-add-fix-issue-235` 也匹配
    `*-fix-issue-235`，且按字典序可能排在真身之前；若诱饵带着事件日志，测试会
    假绿。修复要求归档名去掉日期前缀后**精确等于** change_id。
    """
    change_id = "fix-issue-235"
    archive = tmp_path / "openspec" / "changes" / "archive"
    decoy = archive / f"2026-01-01-add-{change_id}"
    decoy.mkdir(parents=True)
    (decoy / "workflow-events.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")

    # 只有诱饵时：不得被当成目标 change
    assert _change_dir_in_any_form(tmp_path, change_id) is None

    real = archive / f"2026-09-23-{change_id}"
    real.mkdir(parents=True)
    (real / "workflow-events.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")
    assert _change_dir_in_any_form(tmp_path, change_id) == real


def test_own_change_explains_protected_artifact_with_its_own_event():
    """本 change 改了受保护文件 `docs/known-debt.md`，必须由**它自己**的
    workflow-events.jsonl 给出 `protected_artifact_explained` 事件。

    既存机制弱点是全仓 rglob 命中事件（`_protected_artifact_explanation_errors`
    搜全仓、`_change_id_for_event_log` 用事件日志自身目录推导 expected id），
    所以别的 change 的陈旧事件也能让门禁变绿——CI 绿不等于承诺的证据存在。

    触发条件是**本树里的本 change 事件日志存在**（active 或 archive 形态皆可），
    不依赖 `origin/master`（CI 上只有 `github.event.pull_request.base.sha`）；
    两个形态都不存在时说明该 change 已离开本树，跳过而非误红。
    """
    repo_root = Path(__file__).resolve().parents[1]
    change_dir = _change_dir_in_any_form(repo_root, "fix-issue-235-completion-gate")
    if change_dir is None:
        pytest.skip("本 change 不在本树（active/archive 均无）")

    events = [
        json.loads(line)
        for line in (change_dir / "workflow-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    explained = [
        e for e in events
        if e.get("event_type") == "protected_artifact_explained"
        and e.get("artifact_path") == "docs/known-debt.md"
    ]
    assert explained, (
        f"{change_dir.name} 改了 docs/known-debt.md，但其自己的 workflow-events.jsonl "
        "没有 protected_artifact_explained 事件（此时门禁若变绿，证据来自别的 change）"
    )
    assert explained[0].get("reason"), "protected_artifact_explained 事件缺 reason"


def test_backlog_has_no_duplicate_section_headings():
    """本 change 的立项提交曾把 `### 3.` 标题复制成 `### 3. …### 3. …`。

    那是一次 Edit 的误伤（`old_string` 命中后把整行重写了两遍），既弄脏了文档、
    也会让 backlog 的章节结构错乱。加一条机械锁：未实现队列里的 `### N. \\`id\\``
    标题不得在同一次提交里被拼接成一行出现两次。
    """
    backlog = Path(__file__).resolve().parents[1] / "docs" / "openspec-change-backlog.md"
    text = backlog.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("### "):
            continue
        assert stripped.count("### ") == 1, f"backlog 标题重复拼接: {stripped!r}"

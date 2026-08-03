from pathlib import Path
import json

from scripts.check_openspec_artifacts import (
    check_backlog_consistency,
    check_change,
    check_protected_path_explanations,
    main,
    parse_change_type,
)
from agent.workflow.manager import WorkflowManager


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


def test_check_change_rejects_handoff_projection_mismatch(tmp_path):
    change = tmp_path / "tampered-change"
    mgr = WorkflowManager(change, repo_root=tmp_path)
    mgr.init("tampered-change")
    mgr.advance_sub_state("writing_proposal")
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
        lambda repo_root, base_ref: {"docs/known-issues.md"},
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

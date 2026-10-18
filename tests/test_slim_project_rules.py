"""瘦 checker 的六条项目规则：正例 + 否定用例。

判据来自退役前的 `scripts/check_openspec_artifacts.py`；本文件只覆盖保留面：
RIR / Impact Analysis / benchmark smoke / tasks + 归档点完成度 / backlog 一致性 /
building review 的 `## 闭环出口`。事件、manifest、grill stage 证据由 witnessloop 承担，
唯一例外是「非代码 change 的归档点 grill 证据」——它是旧归档完成度的一部分。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.check_openspec_artifacts as mod


VALID_IMPACT = """## Impact Analysis

- Code: none.
- Tests: covered.
"""

VALID_RIR = """## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: Routine enhancement; established pattern applied locally.
- findings:
  - Reference repositories keep one aggregate check script.
- design impact:
  - Keep one slim checker.
"""

VALID_DESIGN = """## Context

Background.

## Goals / Non-Goals

Goals.

## Decisions

Decisions.

## Pre-Implementation Review

Resolved.

## Risks / Trade-offs

None.

## Testing Strategy

Tests.
"""

VALID_GRILL = """# Grill

## Confirmed Decisions

- **决策**: 决策一；理由: 理由一；来源: run-1
- **决策**: 决策二；理由: 理由二；来源: run-1
- **决策**: 决策三；理由: 理由三；来源: run-1

## Open Questions

无

## User Confirmation

- 本 change 的 Open Question 数为 0
"""

ALL_CHECKED = "## 1. Work\n\n- [x] done.\n"


def proposal(
    change_type: str,
    *,
    impact: bool = True,
    rir: bool = True,
    extra: str = "",
) -> str:
    text = (
        "# Proposal\n\n## Change Type\n\n"
        f"- primary: {change_type}\n- secondary: []\n\n## Why\n\nReason.\n"
    )
    if impact:
        text += "\n" + VALID_IMPACT
    if rir and change_type != "docs":
        text += "\n" + VALID_RIR
    return text + extra


def make_change(
    parent: Path,
    *,
    name: str = "demo",
    change_type: str = "feature",
    proposal_text: str | None = None,
    design: str | None = VALID_DESIGN,
    tasks: str = ALL_CHECKED,
    spec_delta: str | None = None,
    building_review: str | None = None,
    grill_design: str | None = None,
    grill_adversarial: bool = False,
) -> Path:
    change = parent / name if name == "demo" else parent / name
    change.mkdir(parents=True, exist_ok=True)
    (change / "proposal.md").write_text(
        proposal_text if proposal_text is not None else proposal(change_type),
        encoding="utf-8",
    )
    if design is not None:
        (change / "design.md").write_text(design, encoding="utf-8")
    if tasks is not None:
        (change / "tasks.md").write_text(tasks, encoding="utf-8")
    if spec_delta:
        delta = change / "specs" / spec_delta / "spec.md"
        delta.parent.mkdir(parents=True)
        delta.write_text("# delta\n", encoding="utf-8")
    reviews = change / "reviews"
    if building_review is not None:
        reviews.mkdir(exist_ok=True)
        (reviews / "building-review.md").write_text(building_review, encoding="utf-8")
    if grill_design is not None:
        reviews.mkdir(exist_ok=True)
        (reviews / "grill-design.md").write_text(grill_design, encoding="utf-8")
    if grill_adversarial:
        reviews.mkdir(exist_ok=True)
        (reviews / "grill-adversarial.md").write_text("## 闭环出口\n\nPASS\n", encoding="utf-8")
    return change


def _change_type(change_type: str = "feature"):
    ct, errors = mod.parse_change_type(proposal(change_type))
    assert errors == []
    assert ct is not None
    return ct


# ── RIR ──────────────────────────────────────────────────────────────


def test_rir_structure_gate_rejects_missing_section(tmp_path):
    change = make_change(tmp_path, change_type="process", proposal_text=proposal("process", rir=False))
    assert any(
        "Reference Implementation Research" in e for e in mod.check_change(change)
    )


def test_rir_structure_gate_requires_tier(tmp_path):
    body = VALID_RIR.replace("- research_tier: light\n", "")
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
    )
    assert any("research_tier" in e for e in mod.check_change(change))


def test_rir_full_requires_research_questions(tmp_path):
    body = """## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: New protocol.
- findings:
  - Finding.
- design impact:
  - Impact.
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
    )
    assert any("research questions" in e for e in mod.check_change(change))


def test_rir_light_questions_optional(tmp_path):
    change = make_change(tmp_path, change_type="process")
    assert mod.check_change(change) == []


def test_rir_disabled_requires_reason(tmp_path):
    body = """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason:
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
    )
    assert any("reason" in e for e in mod.check_change(change))


def test_rir_content_gate_fires_when_tasks_complete(tmp_path):
    body = """## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 调研在途。
- research questions:
  - Q.
- findings:
  - 尚未完成。
- design impact:
  - Impact.
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
        tasks=ALL_CHECKED,
    )
    errors = mod.check_change(change)
    assert any("尚未完成" in e for e in errors)


def test_rir_full_disabled_rejected_when_tasks_complete(tmp_path):
    body = """## Reference Implementation Research

- research_tier: full
- status: disabled
- reason: 调研在途。
- research questions:
  - Q.
- findings:
  - Done.
- design impact:
  - Impact.
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
        tasks=ALL_CHECKED,
    )
    assert any(
        "disabled" in e for e in mod.check_change(change)
    )


def test_rir_content_gate_skipped_while_tasks_incomplete(tmp_path):
    body = """## Reference Implementation Research

- research_tier: full
- status: disabled
- reason: 调研在途。
- research questions:
  - Q.
- findings:
  - 尚未完成。
- design impact:
  - Impact.
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
        tasks="## 1. Work\n\n- [x] done.\n- [ ] pending.\n",
    )
    assert mod.check_change(change) == []


def test_rir_exempt_requires_evidence_when_tasks_complete(tmp_path):
    body = """## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 与已有模块 X 等价改造。
"""
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", rir=False) + "\n" + body,
        tasks=ALL_CHECKED,
    )
    assert any("exempt 证据校验不通过" in e for e in mod.check_change(change))


# ── Impact Analysis ─────────────────────────────────────────────────


def test_non_docs_requires_impact(tmp_path):
    change = make_change(
        tmp_path, change_type="process", proposal_text=proposal("process", impact=False)
    )
    assert any("Impact Analysis" in e for e in mod.check_change(change))


def test_impact_may_live_in_design(tmp_path):
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=proposal("process", impact=False),
        design=VALID_DESIGN + "\n" + VALID_IMPACT,
    )
    assert mod.check_change(change) == []


def test_placeholder_impact_rejected(tmp_path):
    text = proposal("process", impact=False) + "\n## Impact Analysis\n\n<!-- fill -->\n"
    change = make_change(tmp_path, change_type="process", proposal_text=text)
    assert any("Impact Analysis" in e for e in mod.check_change(change))


def test_docs_change_exempt_from_impact_and_rir(tmp_path):
    change = make_change(
        tmp_path,
        change_type="docs",
        proposal_text=proposal("docs", impact=False, rir=False),
        design=None,
        spec_delta=None,
    )
    assert mod.check_change(change) == []


# ── benchmark smoke ─────────────────────────────────────────────────


def test_benchmark_smoke_required_for_tool_system(tmp_path):
    text = proposal("process", extra="\n## Capabilities\n\n- `tool-system`: change.\n")
    change = make_change(tmp_path, change_type="process", proposal_text=text)
    assert any("benchmark smoke" in e for e in mod.check_change(change))


def test_benchmark_smoke_satisfied_by_file_level_text(tmp_path):
    text = proposal("process", extra="\n## Capabilities\n\n- `tool-system`: change.\n")
    change = make_change(
        tmp_path,
        change_type="process",
        proposal_text=text,
        tasks="## 4. Verify\n\n- [x] benchmark-gate baseline.\n- [x] smoke recorded.\n",
    )
    assert mod.check_change(change) == []


def test_benchmark_smoke_not_required_for_unrelated_change(tmp_path):
    change = make_change(tmp_path, change_type="process")
    assert mod.check_change(change) == []


# ── building review ─────────────────────────────────────────────────


def test_completed_feature_requires_building_review(tmp_path):
    change = make_change(tmp_path, spec_delta="web-ui")
    assert any("building-review.md missing" in e for e in mod.check_change(change))


def test_completed_feature_accepts_pass_exit(tmp_path):
    change = make_change(tmp_path, spec_delta="web-ui", building_review="## 闭环出口\n\nPASS\n")
    assert mod.check_change(change) == []


def test_completed_feature_rejects_blocked_exit(tmp_path):
    change = make_change(
        tmp_path, building_review="## 闭环出口\n\nBLOCKED（成因：未收口）\n"
    )
    assert any("BLOCKED" in e for e in mod.check_change(change))


def test_partial_feature_undecided_exit_is_not_flagged(tmp_path):
    change = make_change(
        tmp_path,
        tasks="## 1. Work\n\n- [x] done.\n- [ ] pending.\n",
        building_review="## 闭环出口\n\n未定\n",
    )
    assert mod.check_change(change) == []


def test_partial_feature_blocked_exit_is_wide_triggered(tmp_path):
    change = make_change(
        tmp_path,
        tasks="## 1. Work\n\n- [x] done.\n- [ ] pending.\n",
        building_review="## 闭环出口\n\nCHANGES_REQUESTED\n",
    )
    assert any("CHANGES_REQUESTED" in e for e in mod.check_change(change))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("## 闭环出口\n\nPASS\n", ("ok", "PASS")),
        ("## 闭环出口（仅在终结时填写）\n\nPASS\n", ("ok", "PASS")),
        ("## 闭环出口\n\n**PASS**（此前已收口）\n", ("ok", "PASS")),
        ("## 闭环出口\n\n`PASS`\n", ("ok", "PASS")),
        ("## 闭环出口\n\n> PASS\n", ("ok", "PASS")),
        ("## 闭环出口\n\npass\n", ("ok", "PASS")),
        ("## 闭环出口\n\n```markdown\n## 闭环出口\nBLOCKED\n```\n\nPASS\n", ("ok", "PASS")),
        ("## 闭环出口\n\nBLOCKED（成因：x）\n", ("ok", "BLOCKED")),
        ("## 闭环出口\n\nCHANGES_REQUESTED（保持本轮）\n", ("ok", "CHANGES_REQUESTED")),
        ("## 闭环出口\n\nPASSED\n", ("empty", None)),
        ("## 闭环出口\n\nPASS | BLOCKED（成因） | BLOCKED（超上限）\n", ("ambiguous", None)),
        ("## 闭环出口\n\nPASS ｜ BLOCKED（成因）\n", ("ambiguous", None)),
        ("## 闭环出口\n\n1. PASS\n", ("ok", "PASS")),
        ("## 闭环出口\n\n不是 PASS\n", ("empty", None)),
        ("## 闭环出口\n\n未定\n", ("empty", None)),
        ("## 闭环出口\n\n## 闭环出口\n\nPASS\n", ("duplicate", None)),
        ("# Review\n\n## Verdict\n\nPASS\n", ("missing", None)),
    ],
)
def test_review_exit_verdict_parser_edges(text, expected):
    assert mod._review_exit_verdict(text) == expected


def test_no_spec_delta_does_not_require_building_review(tmp_path):
    change = make_change(tmp_path, spec_delta=None)
    assert mod.check_change(change) == []


# ── backlog consistency ─────────────────────────────────────────────


def _backlog_setup(tmp_path: Path) -> tuple[Path, Path]:
    changes = tmp_path / "openspec" / "changes"
    (changes / "archive").mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    return changes, backlog


def test_backlog_rejects_archived_change(tmp_path):
    changes, backlog = _backlog_setup(tmp_path)
    (changes / "archive" / "2026-01-01-done").mkdir()
    backlog.write_text(
        "# Q\n\n## 未实现队列\n\n### 1. `done`\n\n## 已完成待归档\n\n当前无。\n",
        encoding="utf-8",
    )
    assert mod.check_backlog_consistency(changes, backlog) == [
        "backlog references archived change `done`; remove it from backlog"
    ]


def test_backlog_rejects_missing_active_change(tmp_path):
    changes, backlog = _backlog_setup(tmp_path)
    backlog.write_text(
        "# Q\n\n## 未实现队列\n\n### 1. `missing`\n\n## 已完成待归档\n\n当前无。\n",
        encoding="utf-8",
    )
    assert mod.check_backlog_consistency(changes, backlog) == [
        "backlog references missing active change `missing`"
    ]


def test_backlog_accepts_active_change(tmp_path):
    changes, backlog = _backlog_setup(tmp_path)
    (changes / "active").mkdir()
    backlog.write_text(
        "# Q\n\n## 未实现队列\n\n### 1. `active`\n\n## 已完成待归档\n\n当前无。\n",
        encoding="utf-8",
    )
    assert mod.check_backlog_consistency(changes, backlog) == []


# ── archive completion ──────────────────────────────────────────────


def _archive_change(
    tmp_path: Path,
    *,
    name: str = "2026-10-18-demo",
    change_type: str = "feature",
    proposal_text: str | None = None,
    tasks: str = ALL_CHECKED,
    spec_delta: str | None = "web-ui",
    building_review: str | None = "## 闭环出口\n\nPASS\n",
    grill_design: str | None = VALID_GRILL,
    grill_adversarial: bool = True,
) -> Path:
    parent = tmp_path / "openspec" / "changes" / "archive"
    parent.mkdir(parents=True, exist_ok=True)
    return make_change(
        parent,
        name=name,
        change_type=change_type,
        proposal_text=proposal_text,
        tasks=tasks,
        spec_delta=spec_delta,
        building_review=building_review,
        grill_design=grill_design,
        grill_adversarial=grill_adversarial,
    )


def test_archive_gate_untagged_unchecked_task(tmp_path):
    change = _archive_change(
        tmp_path, tasks="## 1. Work\n\n- [x] done.\n- [ ] forgot.\n"
    )
    assert any("忘记勾" in e or "forgot" in e for e in mod._check_archived_completion_gate(change))


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] (post-merge) 收尾",
        "- [ ] 5.5 (post-merge) 收尾",
        "- [ ] **6.9** (post-merge) 收尾",
        "- [ ] （post-merge）收尾",
        "- [ ] (POST-MERGE) 收尾",
        "+ [ ] (post-merge) 收尾",
        "* [ ] (post-merge) 收尾",
        "  - [ ] (post-merge) 收尾",
    ],
)
def test_archive_gate_post_merge_variants_exempt(tmp_path, line):
    change = _archive_change(tmp_path, tasks=f"## 1. Work\n\n- [x] done.\n{line}\n")
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
def test_archive_gate_post_merge_negatives_reported(tmp_path, line):
    change = _archive_change(tmp_path, tasks=f"## 1. Work\n\n- [x] done.\n{line}\n")
    assert any("未勾" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_flags_missing_tasks(tmp_path):
    change = _archive_change(tmp_path)
    (change / "tasks.md").unlink()
    assert any("tasks.md 缺失" in e for e in mod._check_archived_completion_gate(change))


@pytest.mark.parametrize("body", ["prose only\n", ""])
def test_archive_gate_flags_tasks_without_checkboxes(tmp_path, body):
    change = _archive_change(tmp_path, tasks=body)
    assert any("无任何 checkbox 行" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_flags_all_unchecked(tmp_path):
    change = _archive_change(tmp_path, tasks="## 1. Work\n\n- [ ] (post-merge) 关 issue。\n")
    assert any("全部未勾选" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_requires_grill_design(tmp_path):
    change = _archive_change(tmp_path, grill_design=None)
    assert any("grill-design.md missing" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_requires_three_decisions(tmp_path):
    change = _archive_change(
        tmp_path,
        grill_design="# G\n\n## Confirmed Decisions\n\n- **决策**: one；理由: r；来源: s\n",
    )
    assert any("不足 3 条" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_requires_confirmed_open_questions(tmp_path):
    grill = VALID_GRILL.replace(
        "## Open Questions\n\n无\n", "## Open Questions\n\n- **Q1**: 未决项。\n"
    )
    change = _archive_change(tmp_path, grill_design=grill)
    assert any("未确认的 Open Question" in e for e in mod._check_archived_completion_gate(change))


def test_archive_gate_requires_grill_adversarial(tmp_path):
    change = _archive_change(tmp_path, grill_adversarial=False)
    assert any(
        "grill-adversarial.md missing" in e
        for e in mod._check_archived_completion_gate(change)
    )


def test_archive_gate_bugfix_exempt_from_grill(tmp_path):
    change = _archive_change(
        tmp_path,
        change_type="bugfix",
        grill_design=None,
        grill_adversarial=False,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("grill-" in e for e in errors), errors


def test_archive_gate_docs_exempt_from_grill_and_building_review(tmp_path):
    change = _archive_change(
        tmp_path,
        change_type="docs",
        tasks="## 1. Docs\n\n- [x] written.\n",
        spec_delta=None,
        building_review=None,
        grill_design=None,
        grill_adversarial=False,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("grill-" in e for e in errors), errors
    assert not any("building-review" in e for e in errors), errors


def test_archive_gate_no_spec_delta_exempt_from_building_review(tmp_path):
    change = _archive_change(tmp_path, spec_delta=None, building_review=None)
    errors = mod._check_archived_completion_gate(change)
    assert not any("building-review" in e for e in errors), errors


def test_archive_gate_flags_missing_impact_section_only_in_active_not_archive(tmp_path):
    """Impact 只按退役前矩阵在 active change 上评估；归档门不新增该检查。"""
    change = _archive_change(
        tmp_path,
        proposal_text=proposal("feature", impact=False),
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("Impact Analysis" in e for e in errors), errors


# ── archive diff detection ─────────────────────────────────────────


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        errors="replace",
    ).stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def test_archive_diff_catches_pure_rename(tmp_path):
    _init_repo(tmp_path)
    change = tmp_path / "openspec" / "changes" / "my-change"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("x\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "openspec" / "changes" / "archive").mkdir(parents=True)
    _git(
        tmp_path,
        "mv",
        "openspec/changes/my-change",
        "openspec/changes/archive/2026-09-23-my-change",
    )
    _commit(tmp_path, "archive")
    dirs, bad, warning = mod._new_archive_dirs_since_base(tmp_path, base)
    assert dirs == ["2026-09-23-my-change"]
    assert bad == []
    assert warning is None


def test_archive_diff_ignores_file_added_to_existing_archive(tmp_path):
    _init_repo(tmp_path)
    old = tmp_path / "openspec" / "changes" / "archive" / "2026-09-01-old"
    old.mkdir(parents=True)
    (old / "proposal.md").write_text("x\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (old / "reviews").mkdir()
    (old / "reviews" / "notes.json").write_text("{}", encoding="utf-8")
    _commit(tmp_path, "add file")
    dirs, bad, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert dirs == []
    assert bad == []


def test_archive_diff_reports_non_dated_directory(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    bad_dir = tmp_path / "openspec" / "changes" / "archive" / "foo"
    bad_dir.mkdir(parents=True)
    (bad_dir / "proposal.md").write_text("x\n", encoding="utf-8")
    _commit(tmp_path, "bad")
    _, bad, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert "openspec/changes/archive/foo/proposal.md" in bad


def test_archive_diff_ignores_plain_files_under_archive_root(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    root = tmp_path / "openspec" / "changes" / "archive"
    root.mkdir(parents=True)
    (root / ".gitkeep").write_text("", encoding="utf-8")
    (root / "notes.md").write_text("x\n", encoding="utf-8")
    _commit(tmp_path, "files")
    dirs, bad, _ = mod._new_archive_dirs_since_base(tmp_path, base)
    assert dirs == []
    assert bad == []


# ── CLI semantics ───────────────────────────────────────────────────


def test_empty_base_ref_is_treated_as_omitted(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _commit(tmp_path, "base")
    resolved = mod._resolve_base_ref(tmp_path, "")
    assert resolved != ""


def test_main_fails_closed_when_base_unresolvable(tmp_path, monkeypatch):
    changes = tmp_path / "openspec" / "changes"
    (changes / "archive").mkdir(parents=True)
    backlog = tmp_path / "docs" / "openspec-change-backlog.md"
    backlog.parent.mkdir()
    backlog.write_text(
        "# Q\n\n## 未实现队列\n\n当前无。\n\n## 已完成待归档\n\n当前无。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "_new_archive_dirs_since_base",
        lambda *a, **k: ([], [], "could not resolve base ref 'x'"),
    )
    code = mod.main(
        [
            "--changes-root",
            str(changes),
            "--backlog",
            str(backlog),
            "--base-ref",
            "x",
            "--require-base",
        ]
    )
    assert code == 1


def test_change_type_invalid_is_reported(tmp_path):
    change = make_change(
        tmp_path,
        proposal_text="# Proposal\n\n## Change Type\n\n- primary: nonsense\n",
    )
    assert any("invalid change type" in e for e in mod.check_change(change))

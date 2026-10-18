"""Regression tests for retire-manifest-check (issue #316, first cut).

Locks the retirement of the asterwynd review-manifest verification and the
minimal replacement that keeps the only criterion witnessloop does not read:
the building review's terminal ``## 闭环出口`` verdict.

The tests are split by surface:

* parser: ``_review_exit_verdict`` edge cases;
* active gate: ``_check_building_review`` (wide terminal non-PASS + completion);
* archive-point gate: ``_check_archived_completion_gate``;
* ``--check-archived``: manifest drift detection is retired, event-log
  projectability remains;
* docs guard: normative docs no longer require the ast manifest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import scripts.check_openspec_artifacts as mod
from tests.test_openspec_artifact_checker import (
    VALID_DESIGN,
    proposal_for,
    write_change,
    write_spec_delta,
    write_tasks,
)


# ── helpers ──────────────────────────────────────────────────────────


def _change_type(kind: str):
    change_type, errors = mod.parse_change_type(proposal_for(kind))
    assert errors == []
    return change_type


def _make_change(
    tmp_path: Path,
    *,
    change_type: str = "feature",
    all_tasks_done: bool = True,
    spec_delta: bool = True,
    review_text: str | None = None,
    archived: bool = False,
) -> Path:
    if archived:
        change = (
            tmp_path
            / "openspec"
            / "changes"
            / "archive"
            / "2026-10-17-retire-manifest-check-sample"
        )
    else:
        change = tmp_path / "openspec" / "changes" / "sample-change"
    write_change(
        change,
        proposal_for(change_type),
        design=VALID_DESIGN if change_type != "docs" else None,
    )
    tasks = "## 1. 实现\n\n- [x] 已完成。\n"
    if not all_tasks_done:
        tasks += "- [ ] 后续批。\n"
    write_tasks(change, tasks)
    if spec_delta:
        write_spec_delta(change, "web-ui")
    if review_text is not None:
        review_dir = change / "reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "building-review.md").write_text(review_text, encoding="utf-8")
    return change


PASS_EXIT = "## 闭环出口\n\nPASS\n"
BLOCKED_EXIT = "## 闭环出口\n\nBLOCKED（成因：未收口）\n"
UNDECIDED_EXIT = "## 闭环出口\n\n未定\n"


# ── parser ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (PASS_EXIT, ("ok", "PASS")),
        (
            "## 闭环出口（仅在终结时填写；轮内写「未定」）\n\nPASS\n",
            ("ok", "PASS"),
        ),
        (
            "## 闭环出口\n\n**PASS**（此前 CHANGES_REQUESTED 已收口）\n",
            ("ok", "PASS"),
        ),
        ("## 闭环出口\n\n`PASS`\n", ("ok", "PASS")),
        ("## 闭环出口\n\n> PASS\n", ("ok", "PASS")),
        ("## 闭环出口\n\npass\n", ("ok", "PASS")),
        (
            "## 闭环出口\n\n```markdown\n## 闭环出口\nBLOCKED\n```\n\nPASS\n",
            ("ok", "PASS"),
        ),
        ("## 闭环出口\n\nBLOCKED（成因：x）\n", ("ok", "BLOCKED")),
        (
            "## 闭环出口\n\nCHANGES_REQUESTED（保持本轮）\n",
            ("ok", "CHANGES_REQUESTED"),
        ),
        ("## 闭环出口\n\nPASSED\n", ("empty", None)),
        (
            "## 闭环出口\n\nPASS | BLOCKED（成因） | BLOCKED（超上限）\n",
            ("ambiguous", None),
        ),
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


# ── active gate ──────────────────────────────────────────────────────


def test_completed_feature_with_pass_exit_needs_no_manifest(tmp_path):
    change = _make_change(tmp_path, review_text=PASS_EXIT)
    errors = mod._check_building_review(change, _change_type("feature"))
    assert errors == []


def test_completed_feature_with_blocked_exit_is_rejected(tmp_path):
    change = _make_change(tmp_path, review_text=BLOCKED_EXIT)
    errors = mod._check_building_review(change, _change_type("feature"))
    assert any("闭环出口" in e and "BLOCKED" in e for e in errors), errors


def test_completed_feature_without_exit_is_rejected(tmp_path):
    change = _make_change(tmp_path, review_text="# Review\n\nPASS\n")
    errors = mod._check_building_review(change, _change_type("feature"))
    assert any("缺少 `## 闭环出口`" in e for e in errors), errors


def test_completed_feature_without_report_is_rejected(tmp_path):
    change = _make_change(tmp_path)
    errors = mod._check_building_review(change, _change_type("feature"))
    assert any("building-review.md missing" in e for e in errors), errors


@pytest.mark.parametrize(
    "review_text",
    [
        "## 闭环出口\n\nPASS | BLOCKED（成因）\n",
        "## 闭环出口\n\nPASSED\n",
        "## 闭环出口\n\n## 闭环出口\n\nPASS\n",
    ],
)
def test_completed_feature_rejects_malformed_exit_end_to_end(tmp_path, review_text):
    change = _make_change(tmp_path, review_text=review_text)
    errors = mod._check_building_review(change, _change_type("feature"))
    assert any("闭环出口" in e for e in errors), errors


def test_partial_change_undecided_exit_is_not_flagged(tmp_path):
    change = _make_change(
        tmp_path, all_tasks_done=False, review_text=UNDECIDED_EXIT
    )
    errors = mod._check_building_review(change, _change_type("feature"))
    assert errors == []


def test_partial_change_blocked_exit_is_flagged(tmp_path):
    """Wide trigger: terminal non-PASS is rejected regardless of task state."""
    change = _make_change(
        tmp_path, all_tasks_done=False, review_text=BLOCKED_EXIT
    )
    errors = mod._check_building_review(change, _change_type("feature"))
    assert any("BLOCKED" in e for e in errors), errors


def test_docs_change_blocked_exit_is_flagged(tmp_path):
    """Wide trigger: docs changes are not exempt from the terminal verdict."""
    change = _make_change(
        tmp_path, change_type="docs", spec_delta=False, review_text=BLOCKED_EXIT
    )
    errors = mod._check_building_review(change, _change_type("docs"))
    assert any("BLOCKED" in e for e in errors), errors


def test_docs_change_undecided_exit_is_not_flagged(tmp_path):
    change = _make_change(
        tmp_path, change_type="docs", spec_delta=False, review_text=UNDECIDED_EXIT
    )
    errors = mod._check_building_review(change, _change_type("docs"))
    assert errors == []


def test_no_spec_delta_process_change_blocked_exit_is_flagged(tmp_path):
    change = _make_change(
        tmp_path, change_type="process", spec_delta=False, review_text=BLOCKED_EXIT
    )
    errors = mod._check_building_review(change, _change_type("process"))
    assert any("BLOCKED" in e for e in errors), errors


# ── archive-point gate ───────────────────────────────────────────────


def test_archived_completion_gate_accepts_pass_exit(tmp_path):
    change = _make_change(tmp_path, archived=True, review_text=PASS_EXIT)
    errors = mod._check_archived_completion_gate(change)
    assert not any("闭环出口" in e for e in errors), errors


def test_archived_completion_gate_rejects_blocked_exit(tmp_path):
    change = _make_change(tmp_path, archived=True, review_text=BLOCKED_EXIT)
    errors = mod._check_archived_completion_gate(change)
    assert any("闭环出口" in e and "BLOCKED" in e for e in errors), errors


def test_archived_completion_gate_still_requires_report_for_spec_delta(tmp_path):
    change = _make_change(tmp_path, archived=True)
    errors = mod._check_archived_completion_gate(change)
    assert any("building-review.md missing" in e for e in errors), errors


def test_archived_docs_change_blocked_exit_is_flagged(tmp_path):
    change = _make_change(
        tmp_path,
        change_type="docs",
        spec_delta=False,
        archived=True,
        review_text=BLOCKED_EXIT,
    )
    errors = mod._check_archived_completion_gate(change)
    assert any("BLOCKED" in e for e in errors), errors


def test_archived_docs_change_undecided_exit_is_not_flagged(tmp_path):
    change = _make_change(
        tmp_path,
        change_type="docs",
        spec_delta=False,
        archived=True,
        review_text=UNDECIDED_EXIT,
    )
    errors = mod._check_archived_completion_gate(change)
    assert not any("闭环出口" in e for e in errors), errors


# ── --check-archived retirement ──────────────────────────────────────


def _write_archived_manifest_change(root: Path, *, report: str) -> Path:
    change = root / "archive" / "2026-08-02-sample-change"
    (change / "reviews").mkdir(parents=True)
    (change / "specs").mkdir()
    (change / "tasks.md").write_text("- [x] task\n", encoding="utf-8")
    (change / "proposal.md").write_text(
        "# Proposal\n\n## Change Type\n\n- primary: process\n", encoding="utf-8"
    )
    (change / "reviews" / "building-review.md").write_text(report, encoding="utf-8")
    (change / "reviews" / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "sample-change",
                "phase": "building",
                "verdict": "PASS",
                "reviewer_run_id": "r1",
                "base_sha": "a" * 40,
                "head_sha": "b" * 40,
                "tasks_hash": "sha256:stale",
                "spec_hash": "sha256:stale",
                "diff_hash": "sha256:stale",
                "report_hash": "sha256:stale",
            }
        ),
        encoding="utf-8",
    )
    return change


def test_check_archived_ignores_retired_manifest_drift(tmp_path, capsys):
    changes_root = tmp_path / "openspec" / "changes"
    _write_archived_manifest_change(changes_root, report="# Review\n\n## Verdict\n\n**PASS**\n")

    exit_code = mod.main(
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
    assert "spec hash mismatch" not in captured.err
    assert "tasks hash mismatch" not in captured.err
    assert "tasks_hash 已按归档语境跳过" not in captured.err


def test_check_archived_still_checks_event_log_projectability(tmp_path, capsys):
    changes_root = tmp_path / "openspec" / "changes"
    change = _write_archived_manifest_change(changes_root, report=PASS_EXIT)
    (change / "workflow-events.jsonl").write_text("not-json\n", encoding="utf-8")

    exit_code = mod.main(
        [
            "--changes-root",
            str(changes_root),
            "--check-archived",
            "--skip-protected-paths",
            "--skip-backlog",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "不可投影" in captured.err


# ── docs guard ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
NORMATIVE_DOCS = (
    "AGENTS.md",
    "README.md",
    "README_EN.md",
    "docs/development-guide.md",
    "docs/requirements-process.md",
    "docs/interview-script/questions/Q12-ci-testing.md",
    "docs/interview-script/questions/Q14-dev-process.md",
)
OLD_AST_MANIFEST_MARKERS = (
    "building-review-manifest.json",
    "write_review_manifest",
)
MANIFEST_USAGE_PATTERNS = (
    re.compile(r"workflow_state\.py\s+review-manifest"),
    re.compile(r"agent\.workflow\.review_manifest"),
)
RETIREMENT_WORDS = ("已删除", "已退役", "已移除", "不存在", "删除", "已随")
IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+agent\.workflow\.review_manifest\b", re.MULTILINE
)


def _manifest_usage_errors(text: str) -> list[str]:
    """Flag live call/import instructions.

    A retirement word only excuses the match when it follows the match in the same
    clause (within a short window). A line that merely mentions "已退役" somewhere
    earlier does not make a later "作为 legacy 通道保留" instruction legitimate.
    """
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern in MANIFEST_USAGE_PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            tail = line[match.end(): match.end() + 80]
            if any(word in tail for word in RETIREMENT_WORDS):
                continue
            errors.append(f"line {lineno}: {line.strip()}")
            break
    return errors


def test_doc_guard_has_positive_and_negative_controls():
    """Guard must flag a live call and allow an explicit retirement sentence."""
    assert _manifest_usage_errors(
        "run `workflow_state.py review-manifest --change x --phase building`"
    )
    assert _manifest_usage_errors(
        "`workflow_state.py review-manifest` 已删除；调用会报未知子命令"
    ) == []
    # 退役词出现在匹配之前、且匹配之后仍是「保留」指令 ⇒ 必须报错（AGENTS.md:115 形态）。
    assert _manifest_usage_errors(
        "**漂移检测已退役**：`agent/workflow/review_manifest.py` 与 "
        "`workflow_state.py review-manifest` 作为 legacy 通道保留，由第二刀处置"
    )


def test_legacy_module_removed_and_not_imported():
    """Module file is gone and no Python source imports it (issue #316 第二刀)."""
    assert not (REPO_ROOT / "agent" / "workflow" / "review_manifest.py").exists()

    offenders: list[str] = []
    this_file = Path(__file__).resolve()
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        if any(part in {".venv", ".dev", ".git"} for part in rel.parts):
            continue
        if rel.parts[:3] == ("openspec", "changes", "archive"):
            continue
        if path.resolve() == this_file:
            continue
        if IMPORT_RE.search(path.read_text(encoding="utf-8", errors="replace")):
            offenders.append(str(rel))
    assert not offenders, offenders


def test_normative_docs_no_longer_require_ast_manifest():
    failures: list[str] = []
    for rel in NORMATIVE_DOCS:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for marker in OLD_AST_MANIFEST_MARKERS:
            if marker in text:
                failures.append(f"{rel}: {marker}")
        for error in _manifest_usage_errors(text):
            failures.append(f"{rel}: {error}")
    assert not failures, failures


def test_normative_docs_mention_witnessloop_single_manifest():
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs/development-guide.md").read_text(encoding="utf-8")
    requirements = (REPO_ROOT / "docs/requirements-process.md").read_text(
        encoding="utf-8"
    )
    for name, text in (
        ("AGENTS.md", agents),
        ("docs/development-guide.md", guide),
        ("docs/requirements-process.md", requirements),
    ):
        assert "witnessloop" in text and "manifest" in text, name
        assert "## 闭环出口" in text, name
    assert "witnessloop manifest build" in guide
    assert "witnessloop manifest build" in requirements


def test_full_check_commands_pin_origin_master():
    """Documented full checks pin ``origin/master`` explicitly.

    The implicit default now uses the merge-base of ``HEAD`` and
    ``origin/master`` (issue #319), but the documented command stays explicit
    for deterministic CI-like behaviour.
    """
    for rel in (
        "AGENTS.md",
        "docs/requirements-process.md",
        "docs/development-guide.md",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "--base-ref origin/master --require-base" in text, rel

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


def test_normative_docs_no_longer_require_ast_manifest():
    failures: list[str] = []
    for rel in NORMATIVE_DOCS:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for marker in OLD_AST_MANIFEST_MARKERS:
            if marker in text:
                failures.append(f"{rel}: {marker}")
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

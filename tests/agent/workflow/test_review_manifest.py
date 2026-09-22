from __future__ import annotations

import json
import subprocess

from agent.workflow.review_manifest import artifact_hash, file_sha256, verify_review_manifest


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_review_report_without_manifest_is_rejected(tmp_path):
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    (review_dir / "building-review.md").write_text(
        "## Review\n\nPASS\n",
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("review manifest missing" in e for e in errors)


def test_review_report_hash_mismatch_is_rejected(tmp_path):
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    (review_dir / "building-review.md").write_text(
        "## Review\n\nPASS after edit\n",
        encoding="utf-8",
    )
    (review_dir / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "test-change",
                "phase": "building",
                "verdict": "PASS",
                "report_hash": "sha256:old",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("review report hash mismatch" in e for e in errors)


def test_manifest_missing_review_evidence_fields_is_rejected(tmp_path):
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    report_path = review_dir / "building-review.md"
    report_path.write_text("## Review\n\nPASS\n", encoding="utf-8")
    (review_dir / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "test-change",
                "phase": "building",
                "verdict": "PASS",
                "report_hash": file_sha256(report_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("review manifest missing required field: reviewer_run_id" in e for e in errors)
    assert any("review manifest missing required field: tasks_hash" in e for e in errors)


def test_matching_pass_manifest_is_accepted(tmp_path):
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    report_path = review_dir / "building-review.md"
    report_path.write_text("## Review\n\nPASS\n", encoding="utf-8")
    (review_dir / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "test-change",
                "phase": "building",
                "verdict": "PASS",
                "reviewer_run_id": "reviewer-1",
                "base_sha": "base",
                "head_sha": "head",
                "tasks_hash": artifact_hash(tmp_path / "openspec" / "changes" / "test-change" / "tasks.md"),
                "spec_hash": artifact_hash(tmp_path / "openspec" / "changes" / "test-change" / "specs"),
                "diff_hash": "sha256:diff",
                "report_hash": file_sha256(report_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    assert verify_review_manifest(tmp_path, "test-change", "building") == []


def test_tasks_hash_mismatch_is_rejected(tmp_path):
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    report_path = review_dir / "building-review.md"
    report_path.write_text("## Review\n\nPASS\n", encoding="utf-8")
    tasks_path = tmp_path / "openspec" / "changes" / "test-change" / "tasks.md"
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    tasks_path.write_text("- [x] changed after review\n", encoding="utf-8")
    (review_dir / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "test-change",
                "phase": "building",
                "verdict": "PASS",
                "reviewer_run_id": "reviewer-1",
                "base_sha": "base",
                "head_sha": "head",
                "tasks_hash": "sha256:old",
                "spec_hash": artifact_hash(tmp_path / "openspec" / "changes" / "test-change" / "specs"),
                "diff_hash": "sha256:diff",
                "report_hash": file_sha256(report_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("tasks hash mismatch" in e for e in errors)


def _write_manifest(change_dir, filename, **overrides):
    """Write a review manifest next to a change, with valid defaults.

    ``change_dir`` is the resolved change directory (active or archived); the
    manifest is written into its ``reviews/`` sibling. Default hashes bind the
    current artifacts so a test only has to override the field under test.
    """
    review_dir = change_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    report = review_dir / "building-review.md"
    report.write_text("# Review\n\nPASS\n", encoding="utf-8")
    manifest = {
        "schema": "review-manifest/v1",
        "change_id": "sample-change",
        "phase": "building",
        "verdict": "PASS",
        "reviewer_run_id": "r1",
        "base_sha": "abc123",
        "head_sha": "def456",
        "tasks_hash": artifact_hash(change_dir / "tasks.md"),
        "spec_hash": artifact_hash(change_dir / "specs"),
        "diff_hash": "sha256:unavailable",
        "report_hash": file_sha256(report),
    }
    manifest.update(overrides)
    (review_dir / filename).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _make_change(tmp_path, *, archived):
    """Create a change with tasks/specs/report present and a bound manifest."""
    if archived:
        change_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-08-02-sample-change"
    else:
        change_dir = tmp_path / "openspec" / "changes" / "sample-change"
    (change_dir / "specs").mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [x] task\n", encoding="utf-8")
    _write_manifest(change_dir, "building-review-manifest.json")
    return change_dir


def test_archived_tasks_hash_drift_is_not_an_error(tmp_path):
    """A′: archived changes tolerate tasks.md drift (post-PASS checklist ticks).

    The return value must stay a pure error list — the visible "tasks_hash
    skipped" note lives in the caller, not here (note-in-return would make the
    caller print it as an ERROR and fail the check)."""
    change_dir = _make_change(tmp_path, archived=True)

    # Post-PASS 收尾勾选 / 行内描述编辑 → tasks.md 字节哈希漂移。
    (change_dir / "tasks.md").write_text(
        "- [x] task\n- [x] added during closing\n", encoding="utf-8"
    )

    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)

    assert errors == []
    # 判别性契约：返回值是纯错误列表，降级说明不得混入。
    assert not any("tasks_hash" in e or "skip" in e.lower() for e in errors)


def test_same_tasks_drift_is_rejected_in_active_context(tmp_path):
    """判别性对照：同一漂移在 active 语境必须仍报 `tasks hash mismatch`。

    这条锁住 A′ 只放宽归档语境——若实现把降级误扩到 active（或把 `not
    archived` 写成反向条件），本用例转红。"""
    change_dir = _make_change(tmp_path, archived=False)

    (change_dir / "tasks.md").write_text(
        "- [x] task\n- [x] added during closing\n", encoding="utf-8"
    )

    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=False)

    assert any("tasks hash mismatch" in e for e in errors)


def test_archived_spec_hash_drift_is_still_rejected(tmp_path):
    """归档语境其余校验保留：spec_hash 漂移仍判失败。"""
    change_dir = _make_change(tmp_path, archived=True)
    (change_dir / "specs" / "extra.md").write_text("spec changed\n", encoding="utf-8")

    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)

    assert any("spec hash mismatch" in e for e in errors)


def test_archived_report_hash_drift_is_still_rejected(tmp_path):
    """归档语境其余校验保留：report_hash 漂移仍判失败。"""
    change_dir = _make_change(tmp_path, archived=True)
    (change_dir / "reviews" / "building-review.md").write_text(
        "# Review\n\nPASS (edited after manifest)\n", encoding="utf-8"
    )

    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)

    assert any("review report hash mismatch" in e for e in errors)


def test_archived_missing_manifest_is_still_rejected(tmp_path):
    """归档语境其余校验保留：缺 manifest 仍判失败。"""
    change_dir = _make_change(tmp_path, archived=True)
    (change_dir / "reviews" / "building-review-manifest.json").unlink()

    errors = verify_review_manifest(tmp_path, "sample-change", "building", archived=True)

    assert any("review manifest missing" in e for e in errors)


def test_git_diff_hash_mismatch_is_rejected(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "reviewer@example.test")
    _git(tmp_path, "config", "user.name", "Reviewer")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "base")
    base_sha = _git(tmp_path, "rev-parse", "HEAD")
    tracked.write_text("after\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "head")
    head_sha = _git(tmp_path, "rev-parse", "HEAD")

    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [x] reviewed\n", encoding="utf-8")
    review_dir = tmp_path / "openspec" / "changes" / "test-change" / "reviews"
    review_dir.mkdir(parents=True)
    report_path = review_dir / "building-review.md"
    report_path.write_text("## Review\n\nPASS\n", encoding="utf-8")
    (review_dir / "building-review-manifest.json").write_text(
        json.dumps(
            {
                "schema": "review-manifest/v1",
                "change_id": "test-change",
                "phase": "building",
                "verdict": "PASS",
                "reviewer_run_id": "reviewer-1",
                "base_sha": base_sha,
                "head_sha": head_sha,
                "tasks_hash": artifact_hash(change_dir / "tasks.md"),
                "spec_hash": artifact_hash(change_dir / "specs"),
                "diff_hash": "sha256:wrong",
                "report_hash": file_sha256(report_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("git diff hash mismatch" in e for e in errors)

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
    review_dir = tmp_path / ".handoff" / "test-change"
    review_dir.mkdir(parents=True)
    (review_dir / "building-review.md").write_text(
        "## Review\n\nPASS\n",
        encoding="utf-8",
    )

    errors = verify_review_manifest(tmp_path, "test-change", "building")

    assert any("review manifest missing" in e for e in errors)


def test_review_report_hash_mismatch_is_rejected(tmp_path):
    review_dir = tmp_path / ".handoff" / "test-change"
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
    review_dir = tmp_path / ".handoff" / "test-change"
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
    review_dir = tmp_path / ".handoff" / "test-change"
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
    review_dir = tmp_path / ".handoff" / "test-change"
    review_dir.mkdir(parents=True)
    report_path = review_dir / "building-review.md"
    report_path.write_text("## Review\n\nPASS\n", encoding="utf-8")
    tasks_path = tmp_path / "openspec" / "changes" / "test-change" / "tasks.md"
    tasks_path.parent.mkdir(parents=True)
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
    review_dir = tmp_path / ".handoff" / "test-change"
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

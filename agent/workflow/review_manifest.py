from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any

REVIEW_MANIFEST_SCHEMA = "review-manifest/v1"
REVIEW_MANIFEST_FILENAME_SUFFIX = "-review-manifest.json"
REQUIRED_REVIEW_FIELDS = (
    "reviewer_run_id",
    "base_sha",
    "head_sha",
    "tasks_hash",
    "spec_hash",
    "diff_hash",
    "report_hash",
)


def review_report_path(repo_root: str | Path, change_id: str, phase: str) -> Path:
    return (
        Path(repo_root)
        / "openspec"
        / "changes"
        / change_id
        / "reviews"
        / f"{phase}-review.md"
    )


def review_manifest_path(repo_root: str | Path, change_id: str, phase: str) -> Path:
    return (
        Path(repo_root)
        / "openspec"
        / "changes"
        / change_id
        / "reviews"
        / f"{phase}-review-manifest.json"
    )


def build_review_manifest(
    repo_root: str | Path,
    change_id: str,
    phase: str,
    *,
    reviewer_run_id: str,
    base_sha: str,
    head_sha: str | None = None,
    verdict: str = "PASS",
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    head = head_sha or _git_text(repo_root, "rev-parse", "HEAD")
    if not head:
        raise ValueError("review manifest requires head sha or a git repository")
    report_path = review_report_path(repo_root, change_id, phase)
    if not report_path.exists():
        raise FileNotFoundError(f"review report missing: {report_path}")

    change_dir = repo_root / "openspec" / "changes" / change_id
    manifest: dict[str, Any] = {
        "schema": REVIEW_MANIFEST_SCHEMA,
        "change_id": change_id,
        "phase": phase,
        "verdict": verdict,
        "reviewer_run_id": reviewer_run_id,
        "base_sha": base_sha,
        "head_sha": head,
        "tasks_hash": artifact_hash(change_dir / "tasks.md"),
        "spec_hash": artifact_hash(change_dir / "specs"),
        "diff_hash": git_diff_hash(repo_root, base_sha, head) or "sha256:unavailable",
        "report_hash": file_sha256(report_path),
    }
    return manifest


def write_review_manifest(
    repo_root: str | Path,
    change_id: str,
    phase: str,
    *,
    reviewer_run_id: str,
    base_sha: str,
    head_sha: str | None = None,
    verdict: str = "PASS",
) -> Path:
    manifest = build_review_manifest(
        repo_root,
        change_id,
        phase,
        reviewer_run_id=reviewer_run_id,
        base_sha=base_sha,
        head_sha=head_sha,
        verdict=verdict,
    )
    path = review_manifest_path(repo_root, change_id, phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def verify_review_manifest(repo_root: str | Path, change_id: str, phase: str) -> list[str]:
    manifest_path = review_manifest_path(repo_root, change_id, phase)
    if not manifest_path.exists():
        return [f"review manifest missing: {manifest_path}"]

    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"review manifest invalid JSON: {exc}"]

    errors: list[str] = []
    if manifest.get("schema") != REVIEW_MANIFEST_SCHEMA:
        errors.append(f"review manifest schema invalid: {manifest.get('schema')}")
    if manifest.get("change_id") != change_id:
        errors.append(f"review manifest change_id mismatch: {manifest.get('change_id')}")
    if manifest.get("phase") != phase:
        errors.append(f"review manifest phase mismatch: {manifest.get('phase')}")
    if manifest.get("verdict") != "PASS":
        errors.append(f"review manifest verdict is not PASS: {manifest.get('verdict')}")
    for field in REQUIRED_REVIEW_FIELDS:
        if not manifest.get(field):
            errors.append(f"review manifest missing required field: {field}")
    report_path = review_report_path(repo_root, change_id, phase)
    if not report_path.exists():
        errors.append(f"review report missing: {report_path}")
    elif manifest.get("report_hash") != file_sha256(report_path):
        errors.append("review report hash mismatch")
    change_dir = Path(repo_root) / "openspec" / "changes" / change_id
    if manifest.get("tasks_hash") and manifest.get("tasks_hash") != artifact_hash(change_dir / "tasks.md"):
        errors.append("tasks hash mismatch")
    if manifest.get("spec_hash") and manifest.get("spec_hash") != artifact_hash(change_dir / "specs"):
        errors.append("spec hash mismatch")
    if _is_git_repo(Path(repo_root)):
        errors.extend(_verify_git_span(Path(repo_root), manifest))
    return errors


def file_sha256(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def artifact_hash(path: str | Path) -> str:
    resolved = Path(path)
    if not resolved.exists():
        return "sha256:missing"
    if resolved.is_file():
        return file_sha256(resolved)

    entries: list[str] = []
    for file_path in sorted(p for p in resolved.rglob("*") if p.is_file()):
        rel = file_path.relative_to(resolved).as_posix()
        entries.append(f"{rel}\0{file_sha256(file_path)}")
    data = "\n".join(entries).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git_diff_hash(repo_root: str | Path, base_sha: str, head_sha: str) -> str | None:
    result = subprocess.run(
        ["git", "diff", "--binary", base_sha, head_sha],
        cwd=repo_root,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return "sha256:" + hashlib.sha256(result.stdout).hexdigest()


def _verify_git_span(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    base_sha = manifest.get("base_sha")
    head_sha = manifest.get("head_sha")
    if not isinstance(base_sha, str) or not isinstance(head_sha, str):
        return errors

    base_exists = _git_commit_exists(repo_root, base_sha)
    head_exists = _git_commit_exists(repo_root, head_sha)

    # Git span validation is best-effort. On CI the checkout may be a shallow
    # clone or PR head whose base/head shas are not present as git objects; on
    # a rebased local branch the original shas may no longer exist either. In
    # both cases we skip git-span checks rather than false-positive. The
    # content-hash checks (tasks/spec/report) bind the review to the actual
    # artifacts and remain authoritative; diff_hash is informational.
    if not base_exists or not head_exists:
        return errors

    if manifest.get("diff_hash"):
        expected = git_diff_hash(repo_root, base_sha, head_sha)
        if expected is not None and manifest.get("diff_hash") != expected:
            errors.append("git diff hash mismatch")
    return errors


def _is_git_repo(repo_root: Path) -> bool:
    return _git_text(repo_root, "rev-parse", "--is-inside-work-tree") == "true"


def _git_commit_exists(repo_root: Path, sha: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _git_text(repo_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()

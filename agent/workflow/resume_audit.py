from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.workflow.event_log import (
    RESUME_AUDIT_RECONCILED_EVENT_TYPE,
    append_resume_audit_reconciled_event,
    event_log_path,
)
from agent.workflow.routing import load_workflow_methods

BASELINE_SCHEMA = "workflow-resume-baseline/v1"
DEFAULT_BASELINE_PATH = ".dev/workflow-resume-baseline.json"


@dataclass(frozen=True)
class ResumeAuditResult:
    repo_root: Path
    baseline_path: Path
    baseline_present: bool
    baseline_sha: str | None = None
    head_sha: str | None = None
    changed_paths: tuple[str, ...] = ()
    changed_paths_hash: str = ""
    active_changes: tuple[str, ...] = ()
    reconciled_by_event: str | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def needs_reconciliation(self) -> bool:
        return bool(self.errors)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_path": str(self.baseline_path),
            "baseline_present": self.baseline_present,
            "baseline_sha": self.baseline_sha,
            "head_sha": self.head_sha,
            "changed_paths": list(self.changed_paths),
            "changed_paths_hash": self.changed_paths_hash,
            "active_changes": list(self.active_changes),
            "reconciled_by_event": self.reconciled_by_event,
            "needs_reconciliation": self.needs_reconciliation,
            "passed": self.passed,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def get_resume_baseline_path(repo_root: str | Path = ".") -> Path:
    root = Path(repo_root)
    methods = load_workflow_methods(root)
    workflow = methods.get("workflow", {})
    if not isinstance(workflow, dict):
        return root / DEFAULT_BASELINE_PATH
    audit = workflow.get("resume_audit", {})
    if not isinstance(audit, dict):
        return root / DEFAULT_BASELINE_PATH
    configured = audit.get("baseline_path", DEFAULT_BASELINE_PATH)
    if not isinstance(configured, str) or not configured.strip():
        configured = DEFAULT_BASELINE_PATH
    return root / configured


def write_resume_baseline(
    repo_root: str | Path = ".",
    *,
    created_by: str,
    reason: str,
) -> Path:
    root = Path(repo_root)
    path = get_resume_baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = {
        "schema": BASELINE_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "reason": reason,
        "head_sha": _git_stdout(root, ["rev-parse", "HEAD"]) or "",
        "dirty_paths": list(_changed_paths(root, "HEAD")),
    }
    path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_resume_audit(repo_root: str | Path = ".") -> ResumeAuditResult:
    root = Path(repo_root)
    baseline_path = get_resume_baseline_path(root)
    if not baseline_path.exists():
        return ResumeAuditResult(
            repo_root=root,
            baseline_path=baseline_path,
            baseline_present=False,
        )

    warnings: list[str] = []
    errors: list[str] = []
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ResumeAuditResult(
            repo_root=root,
            baseline_path=baseline_path,
            baseline_present=True,
            errors=(f"workflow resume baseline is invalid JSON: {exc}",),
        )

    if baseline.get("schema") != BASELINE_SCHEMA:
        errors.append(f"workflow resume baseline has invalid schema: {baseline.get('schema')}")

    baseline_sha = baseline.get("head_sha")
    if not isinstance(baseline_sha, str) or not baseline_sha:
        errors.append("workflow resume baseline missing head_sha")
        baseline_sha = None

    head_sha = _git_stdout(root, ["rev-parse", "HEAD"])
    if head_sha is None:
        errors.append("unable to read current git HEAD for workflow resume audit")

    dirty_at_disable = baseline.get("dirty_paths", [])
    if isinstance(dirty_at_disable, list) and dirty_at_disable:
        warnings.append(
            "workflow was disabled while the worktree was already dirty; "
            "resume audit can only compare against that dirty baseline"
        )

    changed_paths = _changed_paths(root, baseline_sha) if baseline_sha else ()
    changed_paths_hash = _fingerprint_changed_paths(root, changed_paths)
    active_changes = _active_change_ids(root)
    reconciled_by = _find_reconciliation_event(
        root,
        baseline_sha=baseline_sha,
        head_sha=head_sha,
        changed_paths_hash=changed_paths_hash,
    )

    if changed_paths and reconciled_by is None and not errors:
        active_note = (
            f" 当前活跃 change: {', '.join(active_changes)}。"
            if active_changes
            else " 当前没有活跃 change。"
        )
        errors.append(
            "workflow resume audit found changes since workflow was disabled:"
            f" {', '.join(changed_paths)}.{active_note} "
            "请把这些改动归入一个 change，然后运行 "
            "`python3 scripts/workflow_state.py resume-audit --reconcile-change <id> "
            "--approved-by <who> --reason <reason>`。"
        )

    return ResumeAuditResult(
        repo_root=root,
        baseline_path=baseline_path,
        baseline_present=True,
        baseline_sha=baseline_sha,
        head_sha=head_sha,
        changed_paths=changed_paths,
        changed_paths_hash=changed_paths_hash,
        active_changes=active_changes,
        reconciled_by_event=reconciled_by,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def record_resume_reconciliation(
    repo_root: str | Path,
    change_id: str,
    *,
    approved_by: str,
    reason: str,
    audit_result: ResumeAuditResult | None = None,
    clear_baseline: bool = True,
) -> Path:
    root = Path(repo_root)
    audit = audit_result or run_resume_audit(root)
    if not audit.baseline_present:
        raise ValueError("workflow resume baseline is missing")
    if not audit.baseline_sha or not audit.head_sha:
        raise ValueError("workflow resume audit is missing baseline/head sha")
    change_dir = _resolve_change_dir(root, change_id)
    if change_dir is None:
        raise ValueError(f"change not found for resume reconciliation: {change_id}")

    append_resume_audit_reconciled_event(
        change_dir,
        _event_change_id(change_dir),
        artifact_path=_repo_relative(root, audit.baseline_path),
        reason=reason,
        approved_by=approved_by,
        baseline_sha=audit.baseline_sha,
        head_sha=audit.head_sha,
        changed_paths_hash=audit.changed_paths_hash,
        changed_paths=list(audit.changed_paths),
    )

    if clear_baseline and audit.baseline_path.exists():
        audit.baseline_path.unlink()

    return event_log_path(change_dir)


def _changed_paths(repo_root: Path, baseline_sha: str) -> tuple[str, ...]:
    paths: set[str] = set()
    diff = _git_stdout(repo_root, ["diff", "--name-only", baseline_sha, "HEAD"])
    if diff:
        paths.update(line.strip() for line in diff.splitlines() if line.strip())

    status = _git_stdout(repo_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    if status:
        for line in status.splitlines():
            path = _status_path(line)
            if path:
                paths.add(path)

    return tuple(sorted(path for path in paths if not _is_resume_audit_ignored(path)))


def _fingerprint_changed_paths(repo_root: Path, changed_paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for rel_path in changed_paths:
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        path = repo_root / rel_path
        if path.exists() and path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        else:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def _active_change_ids(repo_root: Path) -> tuple[str, ...]:
    changes_root = repo_root / "openspec" / "changes"
    if not changes_root.exists():
        return ()
    active: list[str] = []
    for change_dir in sorted(changes_root.iterdir()):
        if not change_dir.is_dir() or change_dir.name == "archive":
            continue
        handoff = change_dir / "handoff.json"
        if not handoff.exists():
            continue
        try:
            data = json.loads(handoff.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            active.append(change_dir.name)
            continue
        if data.get("state", {}).get("phase") != "done":
            active.append(change_dir.name)
    return tuple(active)


def _find_reconciliation_event(
    repo_root: Path,
    *,
    baseline_sha: str | None,
    head_sha: str | None,
    changed_paths_hash: str,
) -> str | None:
    if not baseline_sha or not head_sha:
        return None
    changes_root = repo_root / "openspec" / "changes"
    if not changes_root.exists():
        return None
    for event_log in sorted(changes_root.rglob("workflow-events.jsonl")):
        try:
            lines = event_log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") != RESUME_AUDIT_RECONCILED_EVENT_TYPE:
                continue
            if (
                event.get("baseline_sha") == baseline_sha
                and event.get("head_sha") == head_sha
                and event.get("changed_paths_hash") == changed_paths_hash
            ):
                return _repo_relative(repo_root, event_log)
    return None


def _resolve_change_dir(repo_root: Path, change_id: str) -> Path | None:
    active = repo_root / "openspec" / "changes" / change_id
    if active.exists():
        return active
    archive_root = repo_root / "openspec" / "changes" / "archive"
    if archive_root.exists():
        for path in sorted(archive_root.iterdir()):
            if not path.is_dir():
                continue
            if path.name == change_id or path.name.endswith(f"-{change_id}"):
                return path
    return None


def _event_change_id(change_dir: Path) -> str:
    if change_dir.parent.name == "archive":
        parts = change_dir.name.split("-", 3)
        if len(parts) == 4:
            return parts[3]
    return change_dir.name


def _status_path(line: str) -> str | None:
    if len(line) < 4:
        return None
    path = line[3:].strip()
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1]
    return path.strip('"') or None


def _is_resume_audit_ignored(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith(".dev/")
        or normalized.startswith(".handoff/")
        or normalized.startswith(".git/")
        or normalized == "scripts/workflow_methods.json"
        or normalized == "scripts/workflow_hook.example.json"
        or normalized.endswith("/workflow-events.jsonl")
        or normalized.endswith("-review-manifest.json")
    )


def _git_stdout(repo_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)

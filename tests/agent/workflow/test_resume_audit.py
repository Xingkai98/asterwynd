from __future__ import annotations

import subprocess
from pathlib import Path

from agent.workflow.manager import WorkflowManager
from agent.workflow.resume_audit import (
    record_resume_reconciliation,
    run_resume_audit,
    write_resume_baseline,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")


def test_resume_audit_detects_changed_paths_since_baseline(tmp_path):
    _init_repo(tmp_path)
    write_resume_baseline(tmp_path, created_by="human", reason="pause workflow")

    changed = tmp_path / "agent" / "feature.py"
    changed.parent.mkdir()
    changed.write_text("print('changed')\n", encoding="utf-8")

    result = run_resume_audit(tmp_path)

    assert result.baseline_present is True
    assert result.needs_reconciliation is True
    assert result.changed_paths == ("agent/feature.py",)
    assert any("resume-audit --reconcile-change" in e for e in result.errors)


def test_resume_audit_ignores_workflow_management_files(tmp_path):
    _init_repo(tmp_path)
    write_resume_baseline(tmp_path, created_by="human", reason="pause workflow")

    config = tmp_path / "scripts" / "workflow_methods.json"
    config.parent.mkdir()
    config.write_text('{"workflow": {"enabled": false}}\n', encoding="utf-8")

    result = run_resume_audit(tmp_path)

    assert result.needs_reconciliation is False
    assert result.changed_paths == ()


def test_resume_reconciliation_event_satisfies_audit_and_clears_baseline(tmp_path):
    _init_repo(tmp_path)
    baseline = write_resume_baseline(tmp_path, created_by="human", reason="pause workflow")
    changed = tmp_path / "agent" / "feature.py"
    changed.parent.mkdir()
    changed.write_text("print('changed')\n", encoding="utf-8")

    change_dir = tmp_path / "openspec" / "changes" / "recovery-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("recovery-change")

    audit_before = run_resume_audit(tmp_path)
    event_path = record_resume_reconciliation(
        tmp_path,
        "recovery-change",
        approved_by="human",
        reason="adopt disabled-period edits into recovery-change",
        audit_result=audit_before,
        clear_baseline=True,
    )

    audit_after = run_resume_audit(tmp_path)
    events = event_path.read_text(encoding="utf-8")

    assert baseline.exists() is False
    assert audit_before.needs_reconciliation is True
    assert audit_after.needs_reconciliation is False
    assert '"event_type": "resume_audit_reconciled"' in events
    assert '"artifact_path": ".dev/workflow-resume-baseline.json"' in events


def test_resume_audit_accepts_matching_reconciliation_event(tmp_path):
    _init_repo(tmp_path)
    write_resume_baseline(tmp_path, created_by="human", reason="pause workflow")
    changed = tmp_path / "agent" / "feature.py"
    changed.parent.mkdir()
    changed.write_text("print('changed')\n", encoding="utf-8")

    change_dir = tmp_path / "openspec" / "changes" / "recovery-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("recovery-change")
    audit = run_resume_audit(tmp_path)
    record_resume_reconciliation(
        tmp_path,
        "recovery-change",
        approved_by="human",
        reason="adopt disabled-period edits into recovery-change",
        audit_result=audit,
        clear_baseline=False,
    )

    reconciled = run_resume_audit(tmp_path)

    assert reconciled.needs_reconciliation is False
    assert reconciled.reconciled_by_event is not None

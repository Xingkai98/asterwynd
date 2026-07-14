from __future__ import annotations

import subprocess
from pathlib import Path

from workflow_control import (
    ActivationMode,
    ManagedWorkspaceConfig,
    WorkflowActivationGate,
)


def test_outside_managed_roots_enters_zero_token_bypass(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed"
    unmanaged_root = tmp_path / "unmanaged"
    managed_root.mkdir()
    unmanaged_root.mkdir()
    gate = WorkflowActivationGate(
        ManagedWorkspaceConfig(managed_roots=(managed_root,)),
    )

    decision = gate.preflight(unmanaged_root, session_id="session-1")

    assert decision.mode == ActivationMode.BYPASS
    assert decision.workflow_prompt_enabled is False
    assert decision.model_call_allowed is True
    assert decision.reason == "cwd_not_in_managed_roots"


def test_managed_root_match_canonicalizes_symlinks(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed"
    nested = managed_root / "project"
    nested.mkdir(parents=True)
    link = tmp_path / "link-to-managed"
    link.symlink_to(managed_root, target_is_directory=True)
    gate = WorkflowActivationGate(
        ManagedWorkspaceConfig(managed_roots=(link,)),
    )

    decision = gate.preflight(nested, session_id="session-1")

    assert decision.mode == ActivationMode.MANAGED
    assert decision.managed_root == managed_root.resolve()
    assert decision.workflow_prompt_enabled is True


def test_git_worktree_is_managed_by_common_dir(tmp_path: Path) -> None:
    managed_root = tmp_path / "repo"
    sibling_worktree = tmp_path / "repo-worktree"
    managed_root.mkdir()
    _git(managed_root, "init")
    _git(managed_root, "config", "user.email", "test@example.com")
    _git(managed_root, "config", "user.name", "Test User")
    (managed_root / "README.md").write_text("# test\n", encoding="utf-8")
    _git(managed_root, "add", "README.md")
    _git(managed_root, "commit", "-m", "init")
    _git(managed_root, "worktree", "add", str(sibling_worktree), "-b", "feature/test")
    gate = WorkflowActivationGate(
        ManagedWorkspaceConfig(managed_roots=(managed_root,)),
    )

    decision = gate.preflight(sibling_worktree, session_id="session-1")

    assert decision.mode == ActivationMode.MANAGED
    assert decision.managed_root == managed_root.resolve()
    assert decision.git_common_dir is not None
    assert managed_root.resolve() in decision.git_common_dir.parents


def test_bypass_is_sticky_for_session_until_explicit_attach(tmp_path: Path) -> None:
    managed_root = tmp_path / "managed"
    unmanaged_root = tmp_path / "unmanaged"
    managed_root.mkdir()
    unmanaged_root.mkdir()
    gate = WorkflowActivationGate(
        ManagedWorkspaceConfig(managed_roots=(managed_root,)),
    )

    first = gate.preflight(unmanaged_root, session_id="session-1")
    second = gate.preflight(managed_root, session_id="session-1")
    attached = gate.preflight(
        managed_root,
        session_id="session-1",
        attach_root=managed_root,
    )

    assert first.mode == ActivationMode.BYPASS
    assert second.mode == ActivationMode.BYPASS
    assert second.reason == "sticky_bypass"
    assert attached.mode == ActivationMode.MANAGED
    assert attached.reason == "explicit_attach"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

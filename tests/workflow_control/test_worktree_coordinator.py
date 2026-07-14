from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workflow_control import (
    RequirementsDraft,
    WorktreeCoordinator,
    WorktreeCoordinatorConfig,
    WorkflowValidationError,
)


def test_worktree_promotion_materialization_commit_binding_and_cleanup(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))
    draft = RequirementsDraft.empty().update_goal("automate workflow").freeze()

    binding = coordinator.promote_requirements(
        change_id="change-one",
        approved_requirements=draft,
        date="2026-07-14",
    )

    assert binding.branch == "change-one/2026-07-14"
    assert binding.worktree_path.exists()
    assert (binding.worktree_path / "openspec" / "changes" / "change-one" / "proposal.md").exists()
    assert (binding.worktree_path / "openspec" / "changes" / "change-one" / "workflow-manifest.json").exists()
    assert coordinator.current_branch(binding.worktree_path) == binding.branch

    phase_commit = coordinator.commit_phase(binding.worktree_path, message="complete planning")
    assert phase_commit.head_sha
    gate_binding = coordinator.build_phase_gate_binding(
        worktree_path=binding.worktree_path,
        phase="planning",
        state_version=4,
        evidence_hash="sha256:evidence",
    )
    assert gate_binding.head_sha == phase_commit.head_sha

    coordinator.cleanup_worktree(binding.worktree_path)
    assert not binding.worktree_path.exists()


def test_dirty_worktree_blocks_gate_binding(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))
    binding = coordinator.create_or_reuse_worktree("change-one", date="2026-07-14")
    (binding.worktree_path / "dirty.txt").write_text("dirty", encoding="utf-8")

    with pytest.raises(WorkflowValidationError, match="dirty worktree"):
        coordinator.build_phase_gate_binding(binding.worktree_path, "building", 5, "sha256:evidence")


def test_conflicting_active_branch_is_rejected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))
    coordinator.create_or_reuse_worktree("change-one", date="2026-07-14")

    with pytest.raises(WorkflowValidationError, match="already bound"):
        coordinator.create_or_reuse_worktree("change-one", date="2026-07-14", force_new=True)


def test_base_branch_preflight_detects_dirty_or_diverged_base(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))

    assert coordinator.check_base_branch(repo, base_branch="master", allow_local_base=True).ok
    (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
    result = coordinator.check_base_branch(repo, base_branch="master", allow_local_base=True)

    assert result.ok is False
    assert result.reason == "dirty_base"


def test_design_artifacts_are_written_only_in_bound_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    coordinator = WorktreeCoordinator(WorktreeCoordinatorConfig(canonical_repo=repo, worktrees_root=tmp_path / "worktrees"))
    binding = coordinator.create_or_reuse_worktree("change-one", date="2026-07-14")

    coordinator.write_design_artifacts(binding.worktree_path, "change-one", design="design", tasks="tasks")

    assert not (repo / "openspec" / "changes" / "change-one" / "design.md").exists()
    assert (binding.worktree_path / "openspec" / "changes" / "change-one" / "design.md").exists()


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    return path


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result.stdout.strip()

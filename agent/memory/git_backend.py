"""Git-backed memory history, diff, and revert (#99).

``MemoryGitBackend`` exposes the reversibility primitives on top of the
per-memory git repository maintained by ``PersistentMemory``:

- ``history``: commit log for one memory file.
- ``diff``: diff of one memory file between two commits.
- ``revert``: restore a memory to a prior commit, keeping the index and
  change log consistent.

Revert is deliberately a **two-step commit** (grill Q9 / design Decision 3):
first snapshot the current state (as the undo credential), apply the revert
plus index rebuild plus change-log entry, then commit the revert result so the
revert history is immediately visible in ``git log -- <name>.md`` and the next
destructive write snapshots a clean state instead of carrying revert noise.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.memory.persistent import PersistentMemory, _run_git


class MemoryGitBackend:
    """history / diff / revert over the memory git repo."""

    def __init__(self, memory: "PersistentMemory") -> None:
        self._memory = memory

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        from agent.memory.persistent import _run_git

        return _run_git(self._memory.memory_dir, *args)

    @staticmethod
    def _check_name(name: str) -> str | None:
        from agent.memory.persistent import _validate_name

        return _validate_name(name)

    def history(self, name: str) -> str:
        """Return the commit log for one memory file."""
        name_error = self._check_name(name)
        if name_error is not None:
            return f"Error: {name_error}"
        proc = self._git("log", "--format=%h %s", "--", f"{name}.md")
        if proc.returncode != 0:
            return f"Error: git log failed: {proc.stderr}"
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        if not lines:
            return f"No git history for memory '{name}'."
        return "\n".join(lines)

    def diff(self, name: str, commit_a: str, commit_b: str) -> str:
        """Return the diff of one memory file between two commits."""
        name_error = self._check_name(name)
        if name_error is not None:
            return f"Error: {name_error}"
        proc = self._git("diff", commit_a, commit_b, "--", f"{name}.md")
        if proc.returncode != 0:
            return f"Error: git diff failed: {proc.stderr}"
        if not proc.stdout.strip():
            return f"No diff for memory '{name}' between {commit_a} and {commit_b}."
        return proc.stdout

    def revert(self, name: str, commit: str) -> str:
        """Restore a memory to a prior commit, keeping index and change log consistent.

        Two-step commit (design Decision 3):
          1. snapshot current state (undo credential),
          2. checkout old body + rebuild index line + append change log,
             then commit the revert result so history is immediately visible.
        """
        name_error = self._check_name(name)
        if name_error is not None:
            return f"Error: {name_error}"
        if self._memory._load_entry_by_name(name) is None:
            return f"Error: memory '{name}' not found."

        # Step 1: snapshot the current (to-be-overwritten) state.
        self._memory._git_commit("revert", name, f"before revert to {commit}")

        # Apply the revert: checkout old body.
        proc = self._git("checkout", commit, "--", f"{name}.md")
        if proc.returncode != 0:
            return f"Error: git checkout failed: {proc.stderr}"

        # Rebuild the index line from the reverted frontmatter so MEMORY.md
        # stays consistent with the restored body (grill Q9 / spec scenario).
        entry = self._memory._load_entry_by_name(name)
        if entry is not None:
            self._memory._update_index(name, entry.description, existed=True)
        # Append change log entry (audit history is preserved, not rolled back).
        self._memory._append_changelog("revert", name, commit)

        # Step 2: commit the revert result so history is immediately visible.
        self._memory._git_commit("revert", name, f"revert to {commit}")

        return f"Memory '{name}' reverted to {commit}."

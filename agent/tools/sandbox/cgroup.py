"""cgroup v2 resource controller — per-run CPU/memory limits for ProcessBackend.

Design (sandbox-hardening design.md Decision 5):

- Every ``ProcessBackend.run`` that requests limits creates its OWN ephemeral
  child cgroup under the current process's cgroup (unique dir name), so
  concurrent runs (foreground + background + subagents share one backend
  instance) never share a memory budget or OOM-kill each other.
- ``create()`` writes ``memory.max``/``memory.swap.max`` (hard no-swap cap) and
  ``cpu.max``, and initializes ``cpuset.cpus/cpuset.mems`` from the parent when
  the cpuset controller is enabled (a cgroup v2 gotcha: a fresh child has empty
  cpuset files and pid attach fails with EINVAL/EBUSY until populated).
- ``is_supported()`` is only a cheap pre-filter; ``create()``/``attach()``
  failure is the authoritative "unsupported" signal — the caller degrades to
  plain timeout and surfaces ``degraded``.
- ``oom_killed()`` compares the cumulative ``memory.events oom_kill`` counter
  to a baseline captured at create (counters never decrement).
- ``cleanup()`` removes the child cgroup in a finally; ``cgroup.kill`` is only
  issued when the attached pid is verified to still be ours (starttime guard)
  to avoid killing an unrelated process after pid reuse.

The controller is mock-friendly: all filesystem access goes through an
injectable ``fs_root`` and the class implements the ``CgroupController``
Protocol so ProcessBackend can swap in a fake.
"""
from __future__ import annotations

import os
import re
import time
from itertools import count
from pathlib import Path
from typing import Protocol

DEFAULT_FS_ROOT = Path("/sys/fs/cgroup")
_NAME_COUNTER = count(1)


class CgroupController(Protocol):
    def create(self) -> None: ...
    def attach(self, pid: int, *, starttime: int | None = None) -> bool: ...
    def oom_killed(self) -> bool: ...
    def cleanup(self) -> None: ...


def _own_cgroup_path() -> str:
    """cgroup v2 path of the current process (e.g. ``/`` or ``/foo/bar``)."""
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            line = f.read().strip()
        if "::" in line:
            return line.split("::", 1)[1]
        return "/"
    except OSError:
        return "/"


def _pid_starttime(pid: int) -> int | None:
    """Starttime (clock ticks since boot) of a pid, or None if not readable.

    Used to verify a pid still refers to our process before issuing
    ``cgroup.kill`` (pid-reuse guard). ``comm`` may contain spaces/parens, so
    parse from the last ``)``: starttime is field 22 overall == index 19 of the
    remainder.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            data = f.read()
        idx = data.rfind(")")
        if idx == -1:
            return None
        rest = data[idx + 1 :].split()
        if len(rest) <= 19:
            return None
        return int(rest[19])
    except (OSError, ValueError, IndexError):
        return None


class CgroupV2Controller:
    """Per-run cgroup v2 child group implementing the CgroupController seam."""

    def __init__(
        self,
        *,
        memory_mb: int | None = None,
        cpus: float | None = None,
        fs_root: Path | str = DEFAULT_FS_ROOT,
    ) -> None:
        if memory_mb is not None and memory_mb <= 0:
            raise ValueError("memory_mb must be a positive integer")
        if cpus is not None and cpus <= 0:
            raise ValueError("cpus must be a positive float")
        self.memory_bytes = memory_mb * 1024 * 1024 if memory_mb is not None else None
        self.cpus = cpus
        self.fs_root = Path(fs_root)
        self._path: Path | None = None
        self._oom_baseline = 0
        self._pid: int | None = None
        self._starttime: int | None = None

    @staticmethod
    def is_supported(fs_root: Path | str = DEFAULT_FS_ROOT) -> bool:
        """Cheap pre-filter: controllers file exists AND we can create a child
        cgroup. Not authoritative — create()/attach() failure is."""
        root = Path(fs_root)
        if not (root / "cgroup.controllers").is_file():
            return False
        probe = root / f".asterwynd-probe-{os.getpid()}"
        try:
            probe.mkdir()
            try:
                probe.rmdir()
            except OSError:
                pass
            return True
        except OSError:
            return False

    # --- lifecycle ---------------------------------------------------------

    def create(self) -> None:
        if self._path is not None:
            return
        own = _own_cgroup_path()
        parent = self.fs_root / own.lstrip("/")
        name = f"asterwynd-{os.getpid()}-{next(_NAME_COUNTER)}"
        path = parent / name
        try:
            path.mkdir(exist_ok=False)
        except FileExistsError:
            raise OSError(f"cgroup dir already exists: {path}")
        self._path = path
        self._oom_baseline = self._read_oom_kills()
        try:
            self._apply_limits()
        except Exception:
            try:
                path.rmdir()
            except OSError:
                pass
            self._path = None
            raise

    def attach(self, pid: int, *, starttime: int | None = None) -> bool:
        if self._path is None:
            return False
        self._pid = pid
        self._starttime = starttime
        try:
            self._write("cgroup.procs", str(pid))
            return True
        except OSError:
            return False

    def oom_killed(self) -> bool:
        return self._read_oom_kills() > self._oom_baseline

    def cleanup(self) -> None:
        if self._path is None:
            return
        path = self._path
        self._path = None
        # Kill lingering processes ONLY if the attached pid is still ours
        # (starttime match) — never an unrelated process after pid reuse.
        if (
            self._pid is not None
            and self._starttime is not None
            and _pid_starttime(self._pid) == self._starttime
        ):
            try:
                self._write_to(path, "cgroup.kill", "1")
            except OSError:
                pass
        # The processes were killed / reaped; rmdir with a brief retry for
        # reap. On a real cgroup v2 fs the control files are virtual and do not
        # block rmdir; on a plain filesystem (tests) unlink them so the dir can
        # be reclaimed.
        for _ in range(50):
            try:
                path.rmdir()
                return
            except OSError:
                for child in path.iterdir():
                    try:
                        child.unlink()
                    except OSError:
                        pass
                time.sleep(0.02)

    # --- internals ---------------------------------------------------------

    def _apply_limits(self) -> None:
        if self.memory_bytes is not None:
            self._write("memory.max", str(self.memory_bytes))
            # Hard no-swap cap so a malloc bomb cannot spill past memory.max
            # into swap and evade the OOM killer. CONFIG_MEMCG_SWAP-less hosts
            # lack this file -> per-dimension degrade (ENOENT tolerated).
            try:
                self._write("memory.swap.max", "0")
            except OSError:
                pass
        if self.cpus is not None:
            # cpu.max is "$quota $period" (us); period 100000 (100ms), quota =
            # round(cpus * 100000). Kernel minimum quota is ~1000us.
            quota = max(1000, round(self.cpus * 100000))
            self._write("cpu.max", f"{quota} 100000")
        # cpuset: a fresh child has empty cpuset.cpus/mems; pid attach fails
        # until populated. Copy the parent's values when the controller is on.
        if "cpuset" in self._parent_subtree_control():
            cpus = self._read_parent("cpuset.cpus")
            mems = self._read_parent("cpuset.mems")
            if cpus:
                self._write("cpuset.cpus", cpus)
            if mems:
                self._write("cpuset.mems", mems)

    def _read_oom_kills(self) -> int:
        if self._path is None:
            return 0
        try:
            text = (self._path / "memory.events").read_text(encoding="utf-8")
        except OSError:
            return 0
        m = re.search(r"\boom_kill\s+(\d+)", text)
        return int(m.group(1)) if m else 0

    def _parent_subtree_control(self) -> str:
        if self._path is None:
            return ""
        try:
            return (self._path.parent / "cgroup.subtree_control").read_text(
                encoding="utf-8"
            )
        except OSError:
            return ""

    def _read_parent(self, filename: str) -> str:
        if self._path is None:
            return ""
        try:
            return (self._path.parent / filename).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _write(self, filename: str, value: str) -> None:
        if self._path is None:
            raise OSError("cgroup not created")
        self._write_to(self._path, filename, value)

    @staticmethod
    def _write_to(path: Path, filename: str, value: str) -> None:
        (path / filename).write_text(value, encoding="utf-8")

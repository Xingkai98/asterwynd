"""CgroupV2Controller unit tests against an injectable fake filesystem.

The real host cannot create cgroups (root-owned /sys/fs/cgroup, memory not in
subtree_control), so the controller is tested with ``fs_root`` pointed at a
tmp_path that simulates the cgroup v2 files.
"""
from __future__ import annotations

import pytest

from agent.tools.sandbox.cgroup import CgroupV2Controller


@pytest.fixture
def cg_root(tmp_path):
    """Simulated cgroup v2 filesystem root."""
    (tmp_path / "cgroup.controllers").write_text(
        "cpuset cpu io memory hugetlb pids rdma misc\n"
    )
    return tmp_path


@pytest.fixture
def parent(cg_root):
    """Parent cgroup (own path is '/' in this env), with subtree_control."""
    (cg_root / "cgroup.subtree_control").write_text("cpuset cpu pids\n")
    (cg_root / "cpuset.cpus").write_text("0-3\n")
    (cg_root / "cpuset.mems").write_text("0\n")
    return cg_root


def _child_dirs(cg_root):
    return [p for p in cg_root.iterdir() if p.name.startswith("asterwynd-")]


class TestIsSupported:
    def test_true_when_controllers_present_and_writable(self, cg_root):
        assert CgroupV2Controller.is_supported(cg_root) is True

    def test_false_when_controllers_missing(self, tmp_path):
        assert CgroupV2Controller.is_supported(tmp_path) is False

    def test_false_when_not_writable(self, cg_root, monkeypatch):
        # Simulate an unwritable root: a sibling file at the probe path that
        # makes mkdir fail with FileExistsError (not an OSError subclass check
        # here — mkdir of an existing dir raises FileExistsError, which is an
        # OSError, so is_supported returns False).
        (cg_root / f".asterwynd-probe-{__import__('os').getpid()}").write_text("x")
        assert CgroupV2Controller.is_supported(cg_root) is False


class TestCreate:
    def test_writes_memory_max_and_swap(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=512, fs_root=cg_root)
        ctrl.create()
        child = _child_dirs(cg_root)[0]
        assert (child / "memory.max").read_text() == str(512 * 1024 * 1024)
        assert (child / "memory.swap.max").read_text() == "0"

    def test_writes_cpu_max(self, cg_root):
        ctrl = CgroupV2Controller(cpus=1.5, fs_root=cg_root)
        ctrl.create()
        child = _child_dirs(cg_root)[0]
        assert (child / "cpu.max").read_text() == "150000 100000"

    def test_copies_cpuset_from_parent_when_enabled(self, parent):
        ctrl = CgroupV2Controller(cpus=1.0, fs_root=parent)
        ctrl.create()
        child = _child_dirs(parent)[0]
        assert (child / "cpuset.cpus").read_text() == "0-3"
        assert (child / "cpuset.mems").read_text() == "0"

    def test_no_cpuset_copy_when_controller_off(self, cg_root):
        (cg_root / "cgroup.subtree_control").write_text("cpu pids\n")
        ctrl = CgroupV2Controller(cpus=1.0, fs_root=cg_root)
        ctrl.create()
        child = _child_dirs(cg_root)[0]
        assert not (child / "cpuset.cpus").exists()

    def test_unique_names_for_concurrent_controllers(self, cg_root):
        a = CgroupV2Controller(memory_mb=128, fs_root=cg_root)
        b = CgroupV2Controller(memory_mb=128, fs_root=cg_root)
        a.create()
        b.create()
        dirs = _child_dirs(cg_root)
        assert len(dirs) == 2
        assert dirs[0].name != dirs[1].name

    def test_raises_on_invalid_limits(self, cg_root):
        with pytest.raises(ValueError):
            CgroupV2Controller(memory_mb=0, fs_root=cg_root)
        with pytest.raises(ValueError):
            CgroupV2Controller(cpus=-1, fs_root=cg_root)


class TestSweepStale:
    def _make_dir(self, cg_root, name):
        d = cg_root / name
        d.mkdir()
        (d / "memory.max").write_text("0")
        return d

    def test_removes_dead_pid_cgroups(self, cg_root):
        # 999999 is (almost certainly) not a live pid.
        stale = self._make_dir(cg_root, "asterwynd-999999-1")
        removed = CgroupV2Controller.sweep_stale(cg_root)
        assert removed == 1
        assert not stale.exists()

    def test_keeps_live_pid_cgroups(self, cg_root):
        import os

        live = self._make_dir(cg_root, f"asterwynd-{os.getpid()}-1")
        removed = CgroupV2Controller.sweep_stale(cg_root)
        assert removed == 0
        assert live.exists()

    def test_create_sweeps_stale_first(self, cg_root):
        self._make_dir(cg_root, "asterwynd-999999-1")
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        ctrl.create()
        # The stale dir is gone and a fresh one exists.
        names = [p.name for p in cg_root.iterdir()]
        assert not any("999999" in n for n in names)
        assert any(n.startswith("asterwynd-") and "999999" not in n for n in names)


class TestAttachAndOom:
    def test_attach_writes_pid(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        ctrl.create()
        assert ctrl.attach(4242) is True
        child = _child_dirs(cg_root)[0]
        assert (child / "cgroup.procs").read_text() == "4242"

    def test_attach_false_when_not_created(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        assert ctrl.attach(4242) is False

    def test_oom_killed_baseline_compare(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        ctrl.create()
        child = _child_dirs(cg_root)[0]
        (child / "memory.events").write_text("oom 0\noom_kill 0\n")
        assert ctrl.oom_killed() is False
        (child / "memory.events").write_text("oom 1\noom_kill 1\n")
        assert ctrl.oom_killed() is True


class TestCleanup:
    def test_removes_child_dir(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        ctrl.create()
        assert len(_child_dirs(cg_root)) == 1
        ctrl.cleanup()
        assert _child_dirs(cg_root) == []

    def test_cleanup_idempotent(self, cg_root):
        ctrl = CgroupV2Controller(memory_mb=64, fs_root=cg_root)
        ctrl.create()
        ctrl.cleanup()
        ctrl.cleanup()  # second call is a no-op
        assert _child_dirs(cg_root) == []

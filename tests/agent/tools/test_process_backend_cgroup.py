"""ProcessBackend cgroup v2 integration tests (design.md Decision 5).

The real host cannot create cgroups, so enforcement is tested with an injected
fake CgroupController and the degradation path (the one that actually runs in
this environment) is exercised explicitly.
"""
from __future__ import annotations

import pytest

from agent.sandbox_events import current_sandbox_sink, set_sandbox_sink
from agent.tools.sandbox.process_backend import ProcessBackend


class FakeCgroup:
    def __init__(self) -> None:
        self.created = False
        self.attached = False
        self.cleaned = False
        self.attach_ok = True
        self.oom = False

    def create(self) -> None:
        self.created = True

    def attach(self, pid: int, *, starttime: int | None = None) -> bool:
        self.attached = True
        return self.attach_ok

    def oom_killed(self) -> bool:
        return self.oom

    def cleanup(self) -> None:
        self.cleaned = True


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, **data) -> None:
        self.events.append((event, data))


@pytest.mark.asyncio
async def test_limits_apply_cgroup_when_supported():
    fake = FakeCgroup()
    backend = ProcessBackend(
        memory_mb=64, cgroup_supported=True, controller_factory=lambda: fake
    )
    # The command must outlive the attach call, otherwise a fast `echo hi` can
    # exit first and the attach is skipped (deterministic test).
    result = await backend.run("sleep 0.2; echo hi")
    assert result.exit_code == 0
    assert fake.created is True
    assert fake.attached is True
    assert fake.cleaned is True
    assert result.degraded is False
    assert result.oom_killed is False


def test_attach_skipped_when_process_already_exited():
    """Regression (review fix 9.5): a process that exits before attach is
    skipped (None), NOT a degradation."""
    fake = FakeCgroup()
    backend = ProcessBackend(
        memory_mb=64, cgroup_supported=True, controller_factory=lambda: fake
    )

    class ExitedProc:
        returncode = 0
        pid = 12345

    assert backend._attach(fake, ExitedProc()) is None
    assert fake.attached is False


@pytest.mark.asyncio
async def test_oom_detection_records_result_and_event():
    fake = FakeCgroup()
    fake.oom = True
    sink = RecordingSink()
    prev = current_sandbox_sink()
    set_sandbox_sink(sink)
    try:
        backend = ProcessBackend(
            memory_mb=64, cgroup_supported=True, controller_factory=lambda: fake
        )
        result = await backend.run("echo hi")
    finally:
        set_sandbox_sink(prev)

    assert result.oom_killed is True
    oom_events = [(e, d) for e, d in sink.events if e == "oom"]
    assert len(oom_events) == 1
    assert oom_events[0][1]["reason"] == "memory_limit"
    assert oom_events[0][1]["backend"] == "process"


@pytest.mark.asyncio
async def test_unsupported_cgroup_degrades():
    """配置了限制但宿主无 cgroup：结果标记 degraded + 事件（每实例一次）。"""
    sink = RecordingSink()
    prev = current_sandbox_sink()
    set_sandbox_sink(sink)
    try:
        backend = ProcessBackend(memory_mb=64, cgroup_supported=False)
        r1 = await backend.run("echo one")
        r2 = await backend.run("echo two")
    finally:
        set_sandbox_sink(prev)

    assert r1.degraded is True
    assert r2.degraded is True
    degraded = [(e, d) for e, d in sink.events if e == "degraded"]
    assert len(degraded) == 1  # emitted once per backend instance
    assert degraded[0][1]["reason"] == "cgroup_unavailable"


@pytest.mark.asyncio
async def test_setup_failure_degrades():
    class FailingCgroup(FakeCgroup):
        def create(self) -> None:
            raise OSError("cannot enter cgroup")

    backend = ProcessBackend(
        memory_mb=64, cgroup_supported=True, controller_factory=FailingCgroup
    )
    result = await backend.run("echo hi")
    assert result.degraded is True
    assert result.exit_code == 0  # plain execution still works


@pytest.mark.asyncio
async def test_attach_failure_degrades():
    fake = FakeCgroup()
    fake.attach_ok = False
    backend = ProcessBackend(
        memory_mb=64, cgroup_supported=True, controller_factory=lambda: fake
    )
    # The command must outlive the attach call so the fake's attach actually
    # runs and fails (a process that exits first is skipped, not degraded).
    result = await backend.run("sleep 0.1; echo hi")
    assert result.degraded is True


@pytest.mark.asyncio
async def test_no_limits_skips_cgroup():
    fake = FakeCgroup()
    backend = ProcessBackend(controller_factory=lambda: fake)
    result = await backend.run("echo hi")
    assert fake.created is False
    assert result.degraded is False


@pytest.mark.asyncio
async def test_timeout_with_cgroup_still_kills():
    fake = FakeCgroup()
    backend = ProcessBackend(
        timeout=5.0,
        memory_mb=64,
        cgroup_supported=True,
        controller_factory=lambda: fake,
    )
    result = await backend.run("sleep 60", timeout=0.2)
    assert result.timed_out is True
    assert fake.cleaned is True


@pytest.mark.asyncio
async def test_non_oserror_setup_failure_still_degrades():
    """Regression: a controller that raises a non-OSError must degrade (mark
    degraded + event), not lose the flag and crash the run."""

    class ExplodingCgroup(FakeCgroup):
        def create(self) -> None:
            raise RuntimeError("unexpected controller error")

    backend = ProcessBackend(
        memory_mb=64, cgroup_supported=True, controller_factory=ExplodingCgroup
    )
    result = await backend.run("echo hi")
    assert result.degraded is True
    assert result.exit_code == 0

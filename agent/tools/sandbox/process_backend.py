"""ProcessBackend — subprocess-based ExecutionBackend (default).

The original ``SandboxExecutor`` logic, refactored to implement the
``ExecutionBackend`` protocol. Runs commands via ``subprocess(shell=True)`` on
the host with a timeout; when ``memory_mb``/``cpus`` are configured and cgroup
v2 is available, each ``run`` gets its own ephemeral child cgroup enforcing the
limits (design.md Decision 5).

cgroup v2 enforcement is degrade-first: if the host cannot create a child
cgroup (no write access / memory controller not delegated), the run falls back
to plain timeout and the result carries ``degraded=True`` plus a one-time
``degraded`` sandbox event — the operator is never silently told a limit is
enforced when it is not.
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

from agent.sandbox_events import emit_sandbox_event
from agent.tools.sandbox.base import (
    BackgroundProcessHandle,
    ExecutionBackend,
    SandboxResult,
    _SubprocessHandle,
)
from agent.tools.sandbox.cgroup import (
    CgroupController,
    CgroupV2Controller,
    DEFAULT_FS_ROOT,
    _pid_starttime,
)


def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """SIGKILL the command's whole process group.

    ``run`` spawns the shell with ``start_new_session=True`` so the child is a
    session/process-group leader (pgid == pid); ``killpg`` then kills the shell
    and every descendant. Without this, a timed-out command's children (e.g.
    ``sleep 60`` under ``sh -c``) survive as orphans and hold the pipes open.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _default_controller_factory(
    memory_mb: int | None,
    cpus: float | None,
    fs_root: Path,
) -> Callable[[], CgroupController]:
    def _make() -> CgroupController:
        return CgroupV2Controller(memory_mb=memory_mb, cpus=cpus, fs_root=fs_root)

    return _make


class ProcessBackend:
    """Subprocess-based backend: runs commands on the host with a timeout."""

    def __init__(
        self,
        timeout: float = 30.0,
        memory_mb: int | None = None,
        cpus: float | None = None,
        controller_factory: Callable[[], CgroupController] | None = None,
        cgroup_fs_root: Path | str = DEFAULT_FS_ROOT,
        cgroup_supported: bool | None = None,
    ) -> None:
        if memory_mb is not None and memory_mb <= 0:
            raise ValueError("memory_mb must be a positive integer")
        if cpus is not None and cpus <= 0:
            raise ValueError("cpus must be a positive float")
        self.timeout = timeout
        self.memory_mb = memory_mb
        self.cpus = cpus
        self._fs_root = Path(cgroup_fs_root)
        self._controller_factory = controller_factory or _default_controller_factory(
            memory_mb, cpus, self._fs_root
        )
        # None = lazily probe cgroup support on first limited run.
        self._cgroup_supported = cgroup_supported
        self._cgroup_probed = False
        self._degraded_emitted = False

    def is_available(self) -> bool:
        return True

    # --- resource-limit enforcement ----------------------------------------

    def _cgroup_available(self) -> bool:
        if self._cgroup_supported is None:
            if not self._cgroup_probed:
                self._cgroup_supported = CgroupV2Controller.is_supported(self._fs_root)
                self._cgroup_probed = True
        return bool(self._cgroup_supported)

    def _setup_cgroup(self) -> tuple[CgroupController | None, bool]:
        """Return (controller, degraded).

        ``degraded`` is True when limits were requested but cgroup v2 could not
        enforce them (unsupported host or setup failure). The event is emitted
        at most once per backend instance; every affected run still reports
        ``degraded`` on the result.
        """
        needs_limits = self.memory_mb is not None or self.cpus is not None
        if not needs_limits:
            return None, False
        if not self._cgroup_available():
            self._emit_degraded_once()
            return None, True
        try:
            controller = self._controller_factory()
            controller.create()
            return controller, False
        except Exception:
            # OSError is the primary failure (permission/cgroup setup), but any
            # controller failure must degrade rather than lose the flag.
            self._emit_degraded_once()
            return None, True

    def _emit_degraded_once(self) -> None:
        if not self._degraded_emitted:
            self._degraded_emitted = True
            emit_sandbox_event("degraded", reason="cgroup_unavailable", backend="process")

    def _attach(
        self, controller: CgroupController | None, proc: asyncio.subprocess.Process
    ) -> bool | None:
        """Attach the pid to the cgroup.

        Returns True on success, False on attach failure (real degradation),
        and None when there is no controller or the process already exited
        (nothing to constrain — not a degradation).
        """
        if controller is None:
            return None
        if proc.returncode is not None:
            return None  # process already exited — skip the attach race
        return bool(controller.attach(proc.pid, starttime=_pid_starttime(proc.pid)))

    # --- ExecutionBackend ---------------------------------------------------

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: Path | None = None,
    ) -> SandboxResult:
        timeout = timeout or self.timeout
        start = time.perf_counter()
        controller, degraded = self._setup_cgroup()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
                start_new_session=True,
            )
            attached = self._attach(controller, proc)
            # Degraded means a REQUESTED limit could not be enforced (no cgroup
            # support, setup failure, or attach failure). A process that exited
            # before attach (None) is not a degradation. When no limits were
            # requested there is no controller and no degradation.
            effective_degraded = degraded or (attached is False)
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                oom = bool(controller and controller.oom_killed())
                if oom:
                    emit_sandbox_event(
                        "oom",
                        reason="memory_limit",
                        command=command,
                        backend="process",
                    )
                duration_ms = (time.perf_counter() - start) * 1000
                return SandboxResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_bytes.decode(errors="replace").strip(),
                    stderr=stderr_bytes.decode(errors="replace").strip(),
                    duration_ms=round(duration_ms, 1),
                    timed_out=False,
                    oom_killed=oom,
                    degraded=effective_degraded,
                )
            except asyncio.TimeoutError:
                emit_sandbox_event(
                    "kill", reason="timeout", command=command, backend="process"
                )
                _kill_process_tree(proc)
                await proc.wait()
                oom = bool(controller and controller.oom_killed())
                if oom:
                    emit_sandbox_event(
                        "oom",
                        reason="memory_limit",
                        command=command,
                        backend="process",
                    )
                duration_ms = (time.perf_counter() - start) * 1000
                return SandboxResult(
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_ms=round(duration_ms, 1),
                    timed_out=True,
                    oom_killed=oom,
                    degraded=effective_degraded,
                )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=round(duration_ms, 1),
                timed_out=False,
                degraded=degraded,
            )
        finally:
            if controller is not None:
                controller.cleanup()

    async def run_background(
        self,
        command: str,
        *,
        cwd: Path | None = None,
    ) -> BackgroundProcessHandle:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=__import__("os").setsid,
        )
        return _SubprocessHandle(process)

    def run_sync(
        self,
        command: str,
        timeout: float | None = None,
        cwd: str | Path | None = None,
    ) -> SandboxResult:
        # run_sync has no cgroup enforcement (unused helper; design.md scopes
        # cgroup to the async run() path).
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                exit_code=result.returncode,
                stdout=(result.stdout or "").strip(),
                stderr=(result.stderr or "").strip(),
                duration_ms=round(duration_ms, 1),
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                exit_code=-1,
                stdout=(e.stdout or b"").decode(errors="replace").strip() if e.stdout else "",
                stderr=(e.stderr or b"").decode(errors="replace").strip() if e.stderr else "",
                duration_ms=round(duration_ms, 1),
                timed_out=True,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=round(duration_ms, 1),
                timed_out=False,
            )

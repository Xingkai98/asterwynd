"""ProcessBackend — subprocess-based ExecutionBackend (default).

The original ``SandboxExecutor`` logic, refactored to implement the
``ExecutionBackend`` protocol. Runs commands via ``subprocess(shell=True)`` on
the host with a timeout; no OS-level isolation (the command guard runs first).
"""
from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from agent.tools.sandbox.base import (
    BackgroundProcessHandle,
    ExecutionBackend,
    SandboxResult,
    _SubprocessHandle,
)


class ProcessBackend:
    """Subprocess-based backend: runs commands on the host with a timeout."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def is_available(self) -> bool:
        return True

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: Path | None = None,
    ) -> SandboxResult:
        timeout = timeout or self.timeout
        start = time.perf_counter()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                duration_ms = (time.perf_counter() - start) * 1000
                return SandboxResult(
                    exit_code=proc.returncode or 0,
                    stdout=stdout_bytes.decode(errors="replace").strip(),
                    stderr=stderr_bytes.decode(errors="replace").strip(),
                    duration_ms=round(duration_ms, 1),
                    timed_out=False,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration_ms = (time.perf_counter() - start) * 1000
                return SandboxResult(
                    exit_code=-1,
                    stdout="",
                    stderr="",
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

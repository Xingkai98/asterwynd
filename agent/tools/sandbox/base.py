"""Execution backend abstraction — the pluggable sandbox seam.

The execution of shell commands is abstracted behind ``ExecutionBackend`` so
that different sandbox strategies (subprocess, Docker container, later gVisor)
are swappable. ``SandboxResult`` and ``BackgroundProcessHandle`` are the
unified return types, reused from the original ``SandboxExecutor``.

This is the "boundary" of defense-in-depth: the command guard (a guardrail,
not a boundary) runs first, then the backend enforces isolation.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


class BackgroundProcessHandle(ABC):
    """后台进程句柄协议。不暴露 raw subprocess.Process，换容器时只需改适配器。"""

    @abstractmethod
    async def poll(self) -> int | None:
        """检查进程是否结束，返回 exit_code 或 None（仍在运行）。"""

    @abstractmethod
    async def read_chunk(self, size: int = 4096) -> bytes:
        """读一块 stdout 数据，返回空字节表示 EOF。"""

    @abstractmethod
    async def terminate(self) -> None:
        """SIGTERM。"""

    @abstractmethod
    async def kill(self) -> None:
        """SIGKILL。"""

    @abstractmethod
    async def wait(self) -> None:
        """等待进程退出。"""

    @abstractmethod
    def force_kill_sync(self, wait_timeout: float = 0.5) -> None:
        """同步强制终止，仅用于 cleanup 紧急路径。不做任何异步操作。"""


class _SubprocessHandle(BackgroundProcessHandle):
    """asyncio.subprocess.Process 适配器。"""

    def __init__(self, process: subprocess.Popen):
        self._process = process

    async def poll(self) -> int | None:
        return self._process.returncode

    async def read_chunk(self, size: int = 4096) -> bytes:
        if self._process.stdout is None:
            return b""
        try:
            return await self._process.stdout.read(size)
        except Exception:
            return b""

    async def terminate(self) -> None:
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            self._process.terminate()

    async def kill(self) -> None:
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            self._process.kill()

    async def wait(self) -> None:
        await self._process.wait()

    def force_kill_sync(self, wait_timeout: float = 0.5) -> None:
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(wait_timeout)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                self._process.kill()
            except Exception:
                pass


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool

    def __str__(self) -> str:
        if self.timed_out:
            return f"[Timeout after {self.duration_ms:.0f}ms] {self.stdout}{self.stderr}".strip()
        if self.exit_code != 0:
            parts = [self.stdout, self.stderr]
            return f"[Exit {self.exit_code}] {' '.join(p for p in parts if p)}".strip()
        return (self.stdout + self.stderr).strip()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@runtime_checkable
class ExecutionBackend(Protocol):
    """Pluggable command execution backend (sandbox boundary).

    Implementations: ``ProcessBackend`` (subprocess) and ``DockerBackend``
    (container isolation). A backend receives a command and returns a
    ``SandboxResult`` — the interface is deliberately minimal so backends are
    swappable behind the factory.
    """

    def is_available(self) -> bool:
        """Whether the backend is usable in this environment (daemon reachable)."""
        ...

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: Path | None = None,
    ) -> SandboxResult:
        """Run a command synchronously and return the result.

        ``timeout`` defaults to the backend's configured timeout.
        """
        ...

    async def run_background(
        self,
        command: str,
        *,
        cwd: Path | None = None,
    ) -> BackgroundProcessHandle:
        """Start a background process and return a handle."""
        ...

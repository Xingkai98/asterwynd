# agent/tools/sandbox.py
import asyncio
import json
import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path


class BackgroundProcessHandle(ABC):
    """后台进程句柄协议。不暴露 raw subprocess.Process，未来换容器时只需改适配器。"""

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

    def __init__(self, process: asyncio.subprocess.Process):
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


class SandboxExecutor:
    """基于 subprocess 的沙箱执行器，限制资源"""

    def __init__(
        self,
        timeout: float = 30.0,
        max_memory_mb: int = 512,
        allowed_dirs: Optional[list[str]] = None,
    ):
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.allowed_dirs = allowed_dirs or ["/tmp", "/var/tmp"]

    async def run(
        self,
        command: str,
        timeout: Optional[float] = None,
        cwd: Optional[str | Path] = None,
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
        cwd: str | Path | None = None,
    ) -> BackgroundProcessHandle:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
        return _SubprocessHandle(process)

    def run_sync(
        self,
        command: str,
        timeout: Optional[float] = None,
        cwd: Optional[str | Path] = None,
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

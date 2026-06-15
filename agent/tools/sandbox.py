# agent/tools/sandbox.py
import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path


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
        except subprocess.TimeoutExpired:
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

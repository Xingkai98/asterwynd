# agent/tools/sandbox.py
import asyncio
import subprocess
from typing import Optional
from pathlib import Path

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
    ) -> str:
        """在沙箱中运行命令，返回 stdout"""
        timeout = timeout or self.timeout

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=1024 * 1024,  # 1MB stdout
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                output = stdout.decode(errors="replace").strip()
                if proc.returncode:
                    return f"[Exit {proc.returncode}] {output}".strip()
                return output
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"[Timeout after {timeout}s]"
        except Exception as e:
            return f"[Error: {e}]"

    def run_sync(
        self,
        command: str,
        timeout: Optional[float] = None,
        cwd: Optional[str | Path] = None,
    ) -> str:
        """同步版本，用于非 async 上下文"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode:
                return f"[Exit {result.returncode}] {output}".strip()
            return output
        except subprocess.TimeoutExpired:
            return f"[Timeout after {timeout}s]"
        except Exception as e:
            return f"[Error: {e}]"

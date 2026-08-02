"""DockerBackend — Docker container ExecutionBackend (real sandbox boundary).

Runs commands inside a throwaway container with network, filesystem, and
resource isolation:

- ``--network none``: no network (cannot exfiltrate or reach external hosts)
- ``--memory`` / ``--cpus``: resource limits (container-level, replaces cgroup)
- ``-v <workspace>:/workspace -w /workspace``: only the workspace is mounted
- ``--rm``: container removed after run
- timeout: bounded wait then ``docker kill``

Docker daemon access: the current user must be in the ``docker`` group (or use
``sg docker``); ``is_available()`` probes ``docker info``.
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
)


def _needs_sg() -> bool:
    """Whether the current process can reach the Docker daemon directly.

    In this environment the shell's supplementary groups are stale (does not
    include ``docker`` in the process group), so ``sg docker -c`` must be used
    to access the daemon.
    """
    try:
        probe = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return probe.returncode != 0
    except Exception:
        return True


def _docker_argv(subcommand: list[str]) -> list[str]:
    """Build the docker invocation argv.

    Direct: ``["docker", *subcommand]``.
    Via sg: ``["sg", "docker", "-c", "docker <subcommand>"]`` (sg -c takes a
    single shell command string, so arguments are shell-quoted to preserve
    quoting of nested ``sh -c "<command>"``).
    """
    if not _needs_sg():
        return ["docker", *subcommand]
    import shlex

    shell_cmd = "docker " + " ".join(shlex.quote(arg) for arg in subcommand)
    return ["sg", "docker", "-c", shell_cmd]


class DockerBackend:
    """Docker container backend: isolated execution via ``docker run``."""

    def __init__(
        self,
        image: str = "alpine:latest",
        memory_mb: int | None = None,
        cpus: float | None = None,
        timeout: float = 30.0,
    ) -> None:
        # memory/cpus default to None: the --memory/--cpus flags require cgroup
        # v2 domain controllers that some hosts (incl. this dev environment)
        # do not configure, causing docker run to fail. They are opt-in.
        self.image = image
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            proc = subprocess.run(
                _docker_argv(["info"]),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _run_cmd(self, command: str, cwd: Path | None) -> list[str]:
        # docker run <opts> <image> sh -c "<command>"
        run_args = [
            "run", "--rm",
            "--network", "none",
        ]
        if self.memory_mb is not None:
            run_args += ["--memory", f"{self.memory_mb}m"]
        if self.cpus is not None:
            run_args += ["--cpus", str(self.cpus)]
        if cwd is not None:
            run_args += ["-v", f"{cwd.resolve()}:/workspace", "-w", "/workspace"]
        run_args += [self.image, "sh", "-c", command]
        return _docker_argv(run_args)

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: Path | None = None,
    ) -> SandboxResult:
        timeout = timeout or self.timeout
        start = time.perf_counter()
        cmd = self._run_cmd(command, cwd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
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
        # DockerBackend does not support background execution yet; the
        # contract requires the method, so raise a clear error.
        raise NotImplementedError("DockerBackend background execution is not implemented")

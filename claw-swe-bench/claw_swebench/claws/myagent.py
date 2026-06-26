"""MyAgent adapter for Claw-SWE-Bench evaluation.

Wraps MyAgent (Python AgentLoop) inside SWE-bench Docker containers via
`docker exec`. MyAgent's source and venv are bind-mounted into the
container, and the agent runs headless on /testbed.

Isolation: MyAgent is stateless across instances — each invocation runs
in its own container with an independent workspace. No agent
registration or teardown needed.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path

from claw_swebench.claws.base import BaseClawAdapter, decode_output
from claw_swebench.types import AgentResult

logger = logging.getLogger(__name__)

# Sentinels printed by myagent_solve.py
_RESULT_RE = re.compile(
    r"MYAGENT_RESULT\s+finish_reason=(\S+)\s+exit_code=(\d+)\s+duration=([\d.]+)s"
)

# Extra buffer beyond agent timeout for subprocess
_SUBPROCESS_TIMEOUT_BUFFER = 60

# Environment variables to forward into the container
_FORWARDED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "MYAGENT_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)


class MyAgentAdapter(BaseClawAdapter):
    """Drives MyAgent (Python AgentLoop) inside a SWE-bench container.

    Bind-mounts the MyAgent venv and source tree into the container,
    then runs the headless solve script via docker exec.
    """

    name = "myagent"

    def __init__(self, model: str, timeout: int, max_turns: int | None = None):
        super().__init__(model, timeout, max_turns)
        self._myagent_venv = os.environ.get(
            "MYAGENT_VENV", "/opt/myagent-venv"
        )
        self._myagent_src = os.environ.get(
            "MYAGENT_SRC", "/opt/myagent"
        )
        # Python binary inside the container (bind-mounted from host)
        self._python_bin = os.environ.get(
            "CLAW_PYTHON_BIN", "/usr/local/bin/python3.12"
        )

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def container_run_args(self, instance_id: str) -> list[str]:
        """Mount myagent venv + source into the container (read-only)."""
        return [
            "-v", f"{self._myagent_src}:/opt/myagent:ro",
            "-v", f"{self._myagent_venv}:/opt/myagent-venv:ro",
        ]

    # ------------------------------------------------------------------
    # Agent lifecycle (stateless — no-op)
    # ------------------------------------------------------------------

    def create_agent(self, agent_id: str) -> None:
        pass

    def delete_agent(self, agent_id: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Session backup
    # ------------------------------------------------------------------

    def backup_session(self, agent_id: str, dest: Path) -> None:
        """No-op: MyAgent doesn't persist sessions across runs."""
        pass

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def send_task(
        self,
        prompt: str,
        agent_id: str,
        container_name: str,
        artifact_dir: Path | None = None,
        instance_id: str | None = None,
    ) -> AgentResult:
        """Run MyAgent headless on the given prompt inside the container."""
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        # Build docker exec command
        # Mount the venv's Python and site-packages via PYTHONPATH
        cmd = [
            "docker", "exec",
            "-w", "/testbed",
            "-e", f"PYTHONPATH=/opt/myagent:/opt/myagent-venv/lib/python3.12/site-packages",
            "-e", f"MYAGENT_SRC=/opt/myagent",
            "-e", f"MYAGENT_VENV=/opt/myagent-venv",
        ]
        for env_name in _FORWARDED_ENV_VARS:
            val = os.environ.get(env_name)
            if val:
                cmd.extend(["-e", f"{env_name}={val}"])

        # Also set MYAGENT_MODEL from adapter model parameter
        if self.model:
            cmd.extend(["-e", f"MYAGENT_MODEL={self.model}"])

        cmd.extend([
            container_name,
            self._python_bin,
            "/opt/myagent/claw_solve.py",
            "--timeout", str(self.timeout),
            "--max-iterations", str(self.max_turns or 300),
        ])

        logger.info("Starting MyAgent for %s (agent=%s)...", instance_id or "...", agent_id)

        start_time = time.time()
        timed_out = False
        exit_code = 0
        stdout_text = ""
        stderr_text = ""

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout_text, stderr_text = proc.communicate(
                input=prompt,
                timeout=self.timeout + _SUBPROCESS_TIMEOUT_BUFFER,
            )
            exit_code = proc.returncode if proc.returncode is not None else -1
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = -1
            stdout_text = decode_output(getattr(e, "stdout", None) or b"")
            stderr_text = decode_output(getattr(e, "stderr", None) or b"")
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
            logger.warning("MyAgent subprocess timed out after %ds",
                           self.timeout + _SUBPROCESS_TIMEOUT_BUFFER)

        duration = time.time() - start_time

        # Save logs
        if stdout_path:
            stdout_path.write_text(stdout_text)
        if stderr_path:
            stderr_path.write_text(stderr_text)

        # Parse the sentinel from stdout or stderr
        combined = (stdout_text or "") + "\n" + (stderr_text or "")
        match = _RESULT_RE.search(combined)
        if match:
            finish_reason = match.group(1)
            parsed_exit_code = int(match.group(2))
            parsed_duration = float(match.group(3))
            if not timed_out:
                exit_code = parsed_exit_code
                duration = parsed_duration
        else:
            if timed_out:
                finish_reason = "timeout"
            elif exit_code != 0:
                finish_reason = "error"
            else:
                finish_reason = "stop"

        # Collect token usage from stderr (MyAgent prints token stats there)
        usage = self._parse_usage(combined)

        return AgentResult(
            success=(finish_reason == "stop" and exit_code == 0),
            timeout=timed_out,
            exit_code=exit_code,
            finish_reason=finish_reason,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            session_id=None,
            duration_seconds=round(duration, 1),
            usage=usage,
        )

    def collect_usage(self, workspace, artifact_dir: Path) -> dict:
        """Collect token usage from agent stderr log."""
        stderr_log = artifact_dir / "agent_stderr.log"
        if not stderr_log.exists():
            return {}
        text = stderr_log.read_text(errors="replace")
        return self._parse_usage(text)

    @staticmethod
    def _parse_usage(text: str) -> dict:
        """Extract token usage from MyAgent output."""
        # MyAgent uses Anthropic API — look for usage in stderr logs
        # The AnthropicLLM doesn't print structured usage by default,
        # but we can try to extract from common patterns.
        usage: dict[str, int] = {}
        # Check for [myagent] tokens=N in output
        m = re.search(r"tokens=(\d+)", text)
        if m:
            usage["total_tokens"] = int(m.group(1))
        return usage

"""Aider adapter for Claw-SWE-Bench evaluation.

Runs Aider headlessly inside SWE-bench Docker containers via `docker exec`.
Aider is a CLI coding assistant that edits files directly; we bind-mount
its venv, write the prompt to a temp file, run it with --yes, and collect
the resulting git diff.
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

_RESULT_RE = re.compile(
    r"AIDER_RESULT\s+finish_reason=(\S+)\s+exit_code=(\d+)\s+duration=([\d.]+)s"
)

_SUBPROCESS_TIMEOUT_BUFFER = 60

_FORWARDED_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "DEEPSEEK_API_KEY",
)


class AiderAdapter(BaseClawAdapter):
    """Drives Aider headlessly inside a SWE-bench container."""

    name = "aider"

    def __init__(self, model: str, timeout: int, max_turns: int | None = None):
        super().__init__(model, timeout, max_turns)
        self._aider_venv = os.environ.get(
            "AIDER_VENV", "/opt/aider-venv"
        )
        self._python_bin = os.environ.get(
            "CLAW_PYTHON_BIN", "/opt/python3.12/bin/python3.12"
        )

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def container_run_args(self, instance_id: str) -> list[str]:
        """Mount aider venv + Python into the container (read-only)."""
        python_home = os.environ.get(
            "CLAW_PYTHON_HOME",
            "/root/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu",
        )
        return [
            "-v", f"{self._aider_venv}:/opt/aider-venv:ro",
            "-v", f"{python_home}:/opt/python3.12:ro",
        ]

    # ------------------------------------------------------------------
    # Agent lifecycle (stateless)
    # ------------------------------------------------------------------

    def create_agent(self, agent_id: str) -> None:
        pass

    def delete_agent(self, agent_id: str) -> None:
        pass

    def backup_session(self, agent_id: str, dest: Path) -> None:
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
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = artifact_dir / "agent_stdout.log" if artifact_dir else None
        stderr_path = artifact_dir / "agent_stderr.log" if artifact_dir else None

        # Map model name to Aider's model format
        # DeepSeek V4 Pro via OpenAI-compatible endpoint
        aider_model = self._map_model(self.model)

        # Write prompt to file inside container
        prompt_path = "/tmp/aider_prompt.txt"
        write_cmd = [
            "docker", "exec", "-i", container_name,
            "bash", "-c", f"cat > {prompt_path}",
        ]
        try:
            sp = subprocess.run(write_cmd, input=prompt, capture_output=True, text=True, timeout=30)
            if sp.returncode != 0:
                logger.warning("Failed to write prompt file: %s", sp.stderr)
        except subprocess.TimeoutExpired:
            logger.warning("Timeout writing prompt file")

        # Use standalone Python 3.12 (mounted at /opt/python3.12) with aider's
        # site-packages on PYTHONPATH. The aider venv's python symlink resolves
        # to a host path that doesn't exist inside the container.
        python_bin = "/opt/python3.12/bin/python3.12"
        aider_script = "/opt/aider-venv/bin/aider"
        aider_site = "/opt/aider-venv/lib/python3.12/site-packages"

        # Build env vars (all must come before container_name)
        env_args = [
            "-e", f"PYTHONPATH={aider_site}",
        ]
        for env_name in _FORWARDED_ENV_VARS:
            val = os.environ.get(env_name)
            if val:
                env_args.extend(["-e", f"{env_name}={val}"])

        cmd = [
            "docker", "exec", "-i",
            "-w", "/testbed",
        ] + env_args + [
            container_name,
            python_bin,
            aider_script,
            "--yes",
            "--no-auto-commits",
            "--no-stream",
            "--no-suggest-shell-commands",
            "--model", aider_model,
            "--message-file", prompt_path,
        ]

        logger.info("Starting Aider for %s (agent=%s, model=%s)...",
                     instance_id or "...", agent_id, aider_model)

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
            logger.warning("Aider subprocess timed out after %ds",
                           self.timeout + _SUBPROCESS_TIMEOUT_BUFFER)

        duration = time.time() - start_time

        if stdout_path:
            stdout_path.write_text(stdout_text)
        if stderr_path:
            stderr_path.write_text(stderr_text)

        combined = (stdout_text or "") + "\n" + (stderr_text or "")
        match = _RESULT_RE.search(combined)
        if match:
            finish_reason = match.group(1)
            exit_code = int(match.group(2))
            duration = float(match.group(3))
        else:
            if timed_out:
                finish_reason = "timeout"
            elif exit_code != 0:
                finish_reason = "error"
            else:
                finish_reason = "stop"

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
        stderr_log = artifact_dir / "agent_stderr.log"
        if not stderr_log.exists():
            return {}
        return self._parse_usage(stderr_log.read_text(errors="replace"))

    @staticmethod
    def _parse_usage(text: str) -> dict:
        usage: dict[str, int] = {}
        m = re.search(r"tokens[:\s]+(\d[\d,]*)", text)
        if m:
            usage["total_tokens"] = int(m.group(1).replace(",", ""))
        return usage

    @staticmethod
    def _map_model(model: str) -> str:
        """Map model names to Aider's provider/name format."""
        # Aider uses openai/<model> for OpenAI-compatible endpoints
        known = {
            "deepseek-v4-pro": "openai/deepseek-v4-pro",
            "deepseek-v4-flash": "openai/deepseek-v4-flash",
            "claude-opus-4.6": "anthropic/claude-opus-4-20250514",
            "claude-sonnet-4.6": "anthropic/claude-sonnet-4-20250514",
        }
        return known.get(model, f"openai/{model}")

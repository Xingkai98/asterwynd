"""OpenCode adapter for Claw-SWE-Bench evaluation.

Runs OpenCode headlessly inside SWE-bench Docker containers via `docker exec`.
OpenCode is a Go-based coding agent; we bind-mount the binary, write the
prompt to a temp file, run `opencode run`, and collect the resulting git diff.
"""
from __future__ import annotations

import json
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
    r"OPECODE_RESULT\s+finish_reason=(\S+)\s+exit_code=(\d+)\s+duration=([\d.]+)s"
)

_SUBPROCESS_TIMEOUT_BUFFER = 60

_FORWARDED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "DEEPSEEK_API_KEY",
)


class OpenCodeAdapter(BaseClawAdapter):
    """Drives OpenCode headlessly inside a SWE-bench container."""

    name = "opencode"

    def __init__(self, model: str, timeout: int, max_turns: int | None = None):
        super().__init__(model, timeout, max_turns)
        self._opencode_bin = os.environ.get(
            "OPECODE_BIN", "/usr/local/bin/opencode"
        )
        self._host_opencode_bin = self._find_host_binary()

    @staticmethod
    def _find_host_binary() -> str:
        """Find the opencode binary on the host."""
        candidates = [
            os.environ.get("OPECODE_HOST_BIN", ""),
            os.path.expanduser("~/.npm-global/bin/opencode"),
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return candidates[1]  # fallback

    # ------------------------------------------------------------------
    # Container integration
    # ------------------------------------------------------------------

    def container_run_args(self, instance_id: str) -> list[str]:
        """Mount opencode binary into the container (read-only)."""
        return [
            "-v", f"{self._host_opencode_bin}:/usr/local/bin/opencode:ro",
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

        opencode_model = self._map_model(self.model)

        # Write prompt to file inside container (OpenCode reads from positional arg;
        # use shell to read file and pass as argument)
        prompt_path = "/tmp/opencode_prompt.txt"
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

        # Build env vars
        env_args = []
        for env_name in _FORWARDED_ENV_VARS:
            val = os.environ.get(env_name)
            if val:
                env_args.extend(["-e", f"{env_name}={val}"])

        # Run opencode with prompt from file via shell substitution
        shell_cmd = (
            f'cd /testbed && '
            f'{self._opencode_bin} run '
            f'--model {opencode_model} '
            f'--format json '
            f'--dangerously-skip-permissions '
            f'"$(cat {prompt_path})" '
            f'2>&1; '
            f'echo "OPECODE_RESULT finish_reason=stop exit_code=$? duration=0s"'
        )

        cmd = [
            "docker", "exec", "-i",
            "-w", "/testbed",
        ] + env_args + [
            container_name,
            "bash", "-c", shell_cmd,
        ]

        logger.info("Starting OpenCode for %s (agent=%s, model=%s)...",
                     instance_id or "...", agent_id, opencode_model)

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
            logger.warning("OpenCode subprocess timed out after %ds",
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
        try:
            for line in text.splitlines():
                if '"usage"' in line or '"tokens"' in line:
                    data = json.loads(line.strip())
                    if "usage" in data:
                        u = data["usage"]
                        usage["input_tokens"] = u.get("input_tokens", 0)
                        usage["output_tokens"] = u.get("output_tokens", 0)
                        usage["total_tokens"] = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        except (json.JSONDecodeError, KeyError):
            pass
        return usage

    @staticmethod
    def _map_model(model: str) -> str:
        """Map model names to OpenCode's provider/name format."""
        known = {
            "deepseek-v4-pro": "anthropic/deepseek-v4-pro",
            "deepseek-v4-flash": "anthropic/deepseek-v4-flash",
            "claude-opus-4.6": "anthropic/claude-opus-4-20250514",
            "claude-sonnet-4.6": "anthropic/claude-sonnet-4-20250514",
        }
        return known.get(model, f"anthropic/{model}")

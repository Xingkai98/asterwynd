from __future__ import annotations

import glob
import json
import shlex
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

# Paths inside the sandbox container
_AGENT_LOG_DIR = "/logs/agent"
_TRACE_PATH = Path(_AGENT_LOG_DIR) / "trace.json"
_CONTAINER_WHEEL_DIR = "/tmp/asterwynd-wheel"


class AsterwyndAgent(BaseInstalledAgent):
    """Harbor adapter for Asterwynd Coding Agent.

    Installs Asterwynd from a pre-built wheel (uploaded via environment.upload()),
    then calls ``asterwynd run --auto-approve`` inside the sandbox container.

    This adapter requires the Harbor SDK to be available at import time.
    The Harbor SDK is provided by the ``harbor`` CLI environment and is not
    a dependency of the Asterwynd project itself.
    """

    @staticmethod
    def name() -> str:
        return "asterwynd"

    def get_version_command(self) -> str | None:
        return "asterwynd --version"

    async def install(self, environment: BaseEnvironment) -> None:
        dist_dir = Path(__file__).resolve().parent / "environment" / "dist"
        wheels = sorted(glob.glob(str(dist_dir / "asterwynd-*.whl")))
        if not wheels:
            raise FileNotFoundError(
                f"No asterwynd wheel found in {dist_dir}"
            )
        wheel_path = Path(wheels[-1])
        container_path = f"{_CONTAINER_WHEEL_DIR}/{wheel_path.name}"

        # Ensure pip is available; install python3 if the image lacks it
        pip_cmd = "python3 -m pip"
        check = await environment.exec(
            command="python3 -m pip --version 2>/dev/null || python3 --version 2>/dev/null || echo MISSING",
            user="root",
        )
        if "MISSING" in (check.stdout or ""):
            await self.exec_as_root(
                environment,
                command=(
                    "apt-get update -qq && "
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-pip && "
                    "apt-get clean && rm -rf /var/lib/apt/lists/*"
                ),
                timeout_sec=120,
            )
            pip_cmd = "python3 -m pip"

        await self.exec_as_root(
            environment,
            command=f"mkdir -p {_CONTAINER_WHEEL_DIR}",
        )
        await environment.upload_file(str(wheel_path), container_path)
        await self.exec_as_root(
            environment,
            command=(
                f"({pip_cmd} install --no-cache-dir --break-system-packages "
                f"{container_path}) || "
                f"({pip_cmd} install --no-cache-dir {container_path})"
            ),
            env={"PIP_REQUIRE_VIRTUALENV": "false"},
        )

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        prompt = shlex.quote(instruction)
        await self.exec_as_agent(
            environment,
            command=(
                f"asterwynd run --auto-approve --provider anthropic "
                f"--output-dir {_AGENT_LOG_DIR} "
                "--max-iterations 30 "
                f"{prompt}"
            ),
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        trace_path = self.logs_dir / "trace.json"
        try:
            trace = json.loads(trace_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return

        steps = trace.get("steps", [])
        tool_call_count = sum(1 for s in steps if s.get("type") == "tool_call")
        edit_count = sum(1 for s in steps if s.get("type") == "edit")

        completion = next(
            (s for s in reversed(steps) if s.get("type") == "completion"), None
        )
        if completion:
            comp_status = completion.get("data", {}).get("status", "")
            if comp_status == "completed":
                status = "completed"
            elif comp_status in ("max_iterations", "timeout"):
                status = comp_status
            else:
                status = "error"
        else:
            status = "interrupted"

        llm_iterations = [s for s in steps if s.get("type") == "llm_iteration"]

        context.metadata = {
            "tool_calls": tool_call_count,
            "edit_count": edit_count,
            "status": status,
            "duration_seconds": trace.get("duration_seconds", 0),
            "iterations": len(llm_iterations),
        }

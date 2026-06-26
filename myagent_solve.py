"""Headless MyAgent solver for Claw-SWE-Bench.

Runs inside the Docker container via `docker exec`. Reads the problem
statement from stdin, runs the AgentLoop against /testbed, and exits.

Usage:
    cat prompt.txt | python3 /opt/myagent/claw_solve.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# MyAgent source is bind-mounted at /opt/myagent
_MYAGENT_SRC = os.environ.get("MYAGENT_SRC", "/opt/myagent")
if _MYAGENT_SRC not in sys.path:
    sys.path.insert(0, _MYAGENT_SRC)

# Ensure the myagent venv site-packages are on the path
_MYAGENT_VENV = os.environ.get("MYAGENT_VENV", "/opt/myagent-venv")
_VENV_SITE = f"{_MYAGENT_VENV}/lib/python3.12/site-packages"
if _VENV_SITE not in sys.path:
    sys.path.insert(0, _VENV_SITE)

from agent.loop import AgentLoop
from agent.llm import AnthropicLLM
from agent.run_config import AgentRunConfig, AgentMode
from agent.workspace_policy import WorkspacePolicy
from agent.memory.manager import MemoryManager
from agent.subagent.manager import SubAgentManager
from agent.tools.factory import build_coding_tool_registry
from agent.tools.registry import ModePolicy
from agent.trace_recorder import TraceRecorder
from agent.config import MyAgentConfig
from benchmarks.prompt import CodingPromptBuilder
from benchmarks.task_schema import TaskSpec


async def main():
    parser = argparse.ArgumentParser(description="MyAgent headless SWE-bench solver")
    parser.add_argument("--workspace", default="/testbed")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--max-iterations", type=int, default=300)
    args = parser.parse_args()

    problem_statement = sys.stdin.read().strip()
    if not problem_statement:
        print("ERROR: empty problem statement", file=sys.stderr)
        sys.exit(1)

    workspace = Path(args.workspace)

    model = os.environ.get("MYAGENT_MODEL", "deepseek-v4-pro")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")

    print(f"[myagent] workspace={workspace} model={model} timeout={args.timeout}s",
          file=sys.stderr)

    llm = AnthropicLLM(api_key=api_key, base_url=base_url, model=model)
    llm.stream = False

    config = MyAgentConfig()
    run_config = AgentRunConfig(mode=AgentMode.BUILD)
    policy = WorkspacePolicy(workspace, command_denylist=config.tools.command_denylist)

    registry = build_coding_tool_registry(
        policy=policy,
        mode_policy=ModePolicy(
            run_config,
            deny_tools_by_mode=config.deny_tools_by_mode(),
        ),
        ignore_patterns=config.tools.ignore_patterns,
        code_intelligence_config=config.tools.code_intelligence,
    )

    subagent_manager = SubAgentManager(
        llm=llm,
        config=config,
        workspace_policy=policy,
        parent_mode=run_config.mode,
    )

    agent = AgentLoop(
        llm=llm,
        tool_registry=registry,
        memory=MemoryManager(max_tokens=80_000),
        max_iterations=args.max_iterations,
        subagent_manager=subagent_manager,
        expose_subagent_tools=True,
        run_config=run_config,
        tool_result_display=config.tools.display,
    )

    prompt_builder = CodingPromptBuilder()
    # Build a minimal TaskSpec for the prompt builder
    task = TaskSpec(
        id="claw-swe-task",
        repo="unknown",
        base_commit="HEAD",
        problem_statement_file="",
        test_command="",
        timeout_seconds=args.timeout,
    )
    messages = prompt_builder.build_messages(
        task=task,
        problem_statement=problem_statement,
    )

    trace = TraceRecorder(task_id="claw-swe-task", mode="build")
    start_time = time.time()
    finish_reason = "stop"
    exit_code = 0

    try:
        result = await asyncio.wait_for(
            agent.run(messages=messages, trace_recorder=trace),
            timeout=args.timeout,
        )
        print(f"[myagent] done: stop_reason={result.stop_reason.value} "
              f"tool_calls={len(result.tool_calls_made)} "
              f"tokens={result.total_tokens} "
              f"duration={time.time() - start_time:.1f}s",
              file=sys.stderr)
    except asyncio.TimeoutError:
        finish_reason = "timeout"
        exit_code = 1
        print("[myagent] TIMEOUT", file=sys.stderr)
    except Exception as e:
        finish_reason = "error"
        exit_code = 1
        print(f"[myagent] ERROR: {e}", file=sys.stderr)

    duration = time.time() - start_time
    # Sentinel for the adapter to parse
    print(f"MYAGENT_RESULT finish_reason={finish_reason} "
          f"exit_code={exit_code} "
          f"duration={duration:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())

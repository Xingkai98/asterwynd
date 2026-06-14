from __future__ import annotations

import asyncio
import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from agent.loop import AgentLoop
from agent.memory.manager import MemoryManager
from agent.tools import ToolRegistry, get_coding_tools
from agent.trace_recorder import TraceRecorder
from agent.workspace_policy import WorkspacePolicy
from benchmarks.models import AgentRunResult, FailureCategory
from benchmarks.prompt import CodingPromptBuilder
from benchmarks.task_schema import TaskSpec


class AgentRunner(ABC):
    @abstractmethod
    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        ...


class FakeAgentRunner(AgentRunner):
    def __init__(
        self,
        edit_file: str | None = None,
        old_string: str | None = None,
        new_string: str | None = None,
        status: str = "completed",
        iterations: int = 1,
        tool_calls: int = 1,
    ):
        self.edit_file = edit_file
        self.old_string = old_string
        self.new_string = new_string
        self.status = status
        self.iterations = iterations
        self.tool_calls = tool_calls

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        trace.record_iteration(
            0,
            assistant_preview=f"Fake agent received task: {problem_statement[:120]}",
            tool_calls=[],
        )
        edit_count = 0
        if self.edit_file and self.old_string is not None and self.new_string is not None:
            target = workspace / self.edit_file
            trace.record_tool_call(
                "FakeEdit",
                {"path": self.edit_file, "old_string": self.old_string},
            )
            if not target.exists():
                trace.record_tool_result("FakeEdit", "error", 0, "file not found")
                return AgentRunResult(
                    status="error",
                    failure_category=FailureCategory.EDIT_VALIDATION.value,
                    output="file not found",
                )
            content = target.read_text(errors="replace")
            if self.old_string not in content:
                trace.record_tool_result("FakeEdit", "error", 0, "old_string not found")
                return AgentRunResult(
                    status="error",
                    failure_category=FailureCategory.EDIT_VALIDATION.value,
                    output="old_string not found",
                )
            target.write_text(content.replace(self.old_string, self.new_string, 1), errors="replace")
            edit_count = 1
            trace.record_tool_result("FakeEdit", "ok", 0, "edit applied")
            trace.record_edit(self.edit_file, "ok", "1 replacement")

        return AgentRunResult(
            status=self.status,
            iterations=self.iterations,
            tool_calls=self.tool_calls,
            edit_count=edit_count,
            output="fake agent completed",
        )


class ShellCommandRunner(AgentRunner):
    def __init__(self, command: str, timeout_seconds: int = 300):
        self.command = command
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        start = time.time()
        trace.record_tool_call("ShellAgent", {"command": self.command})

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                self.command,
                cwd=workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=os.environ.copy(),
            )

        try:
            result = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            trace.record_tool_result(
                "ShellAgent",
                "timeout",
                (time.time() - start) * 1000,
                f"timeout after {self.timeout_seconds}s",
            )
            return AgentRunResult(
                status="error",
                tool_calls=1,
                failure_category=FailureCategory.TOOL_ERROR.value,
                output="timeout",
            )

        output = (result.stdout or "") + (result.stderr or "")
        status = "completed" if result.returncode == 0 else "error"
        trace.record_tool_result(
            "ShellAgent",
            "ok" if result.returncode == 0 else "error",
            (time.time() - start) * 1000,
            output,
        )
        return AgentRunResult(
            status=status,
            tool_calls=1,
            failure_category=None if result.returncode == 0 else FailureCategory.TOOL_ERROR.value,
            output=output,
        )


class CountingLLM:
    def __init__(self, llm):
        self.llm = llm
        self.call_count = 0

    async def chat(self, *args, **kwargs):
        self.call_count += 1
        return await self.llm.chat(*args, **kwargs)


class MyAgentRunner(AgentRunner):
    def __init__(
        self,
        llm,
        model: str = "",
        max_iterations: int = 20,
        prompt_builder: CodingPromptBuilder | None = None,
    ):
        self.llm = llm
        self.model = model
        self.max_iterations = max_iterations
        self.prompt_builder = prompt_builder or CodingPromptBuilder()

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        policy = WorkspacePolicy(workspace)
        registry = ToolRegistry()
        for tool in get_coding_tools(policy=policy):
            registry.register(tool)

        counting_llm = CountingLLM(self.llm)
        agent = AgentLoop(
            llm=counting_llm,
            tool_registry=registry,
            memory=MemoryManager(max_tokens=80_000),
            max_iterations=self.max_iterations,
        )
        messages = self.prompt_builder.build_messages(
            task=task,
            problem_statement=problem_statement,
            workspace=str(workspace),
        )
        result = await agent.run(messages, trace_recorder=trace)
        edit_count = sum(1 for call in result.tool_calls_made if call.name == "Edit")
        return AgentRunResult(
            status="completed" if result.stop_reason.value == "end_turn" else "error",
            iterations=counting_llm.call_count,
            tool_calls=len(result.tool_calls_made),
            edit_count=edit_count,
            failure_category=(
                None
                if result.stop_reason.value == "end_turn"
                else FailureCategory.MAX_ITERATIONS.value
            ),
            output=result.content,
        )

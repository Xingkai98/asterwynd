import asyncio

import pytest

from agent.trace_recorder import TraceRecorder
from benchmarks.agent_runner import MyAgentRunner
from benchmarks.task_schema import TaskSpec


class HangingLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_myagent_runner_times_out(tmp_path):
    task = TaskSpec(
        id="timeout-task",
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="true",
        timeout_seconds=1,
    )
    trace = TraceRecorder(task_id=task.id)
    runner = MyAgentRunner(llm=HangingLLM(), max_iterations=5)

    result = await runner.run(task, "Do something", tmp_path, tmp_path / "out", trace)

    assert result.status == "error"
    assert result.failure_category == "model_failure"
    assert "timed out" in result.output

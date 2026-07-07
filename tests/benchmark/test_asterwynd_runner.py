import json

import pytest

from agent.llm import LLMResponse, ToolCallDelta
from benchmarks.agent_runner import AsterwyndRunner
from benchmarks.prompt import CodingPromptBuilder
from benchmarks.task_schema import TaskSpec
from agent.trace_recorder import TraceRecorder
from agent.run_config import AgentMode
from tests.support.llm_harness import ScriptedLLM


def benchmark_scripted_llm() -> ScriptedLLM:
    return ScriptedLLM([
        LLMResponse(
            content="I will edit app.py.",
            tool_calls=[
                ToolCallDelta(
                    id="edit-1",
                    name="Edit",
                    arguments=json.dumps(
                        {
                            "path": "app.py",
                            "old_string": "Version 1",
                            "new_string": "Version 2",
                        }
                    ),
                )
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(
            content="I will inspect the diff.",
            tool_calls=[
                ToolCallDelta(
                    id="diff-1",
                    name="InspectGitDiff",
                    arguments=json.dumps({"path": "app.py"}),
                )
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Done. app.py updated.", stop_reason="end_turn"),
    ])


def test_coding_prompt_builder_includes_task_and_not_patch_names():
    task = TaskSpec(
        id="task",
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="pytest -q",
        gold_patch_file="gold.patch",
        test_patch_file="test.patch",
    )

    messages = CodingPromptBuilder().build_messages(task, "Fix the bug", "/tmp/repo")

    joined = "\n".join(message.content for message in messages)
    assert "Fix the bug" in joined
    assert "pytest -q" in joined
    assert "gold.patch" not in joined
    assert "test.patch" not in joined


@pytest.mark.asyncio
async def test_asterwynd_runner_uses_agent_loop_and_coding_tools(tmp_path):
    (tmp_path / "app.py").write_text("# Version 1\n")
    task = TaskSpec(
        id="task",
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="grep -q 'Version 2' app.py",
    )
    llm = benchmark_scripted_llm()
    runner = AsterwyndRunner(llm=llm, max_iterations=5)
    trace = TraceRecorder(task_id="task")

    result = await runner.run(
        task=task,
        problem_statement="Update app.py to Version 2.",
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        trace=trace,
    )

    assert result.status == "completed"
    assert result.iterations == 3
    assert result.tool_calls == 2
    assert result.edit_count == 1
    assert (tmp_path / "app.py").read_text() == "# Version 2\n"
    assert llm.closed is False  # close() is no longer called inside run()

    await runner.close()
    assert llm.closed is True
    step_types = [step.type for step in trace.steps]
    assert "llm_iteration" in step_types
    assert "tool_call" in step_types
    assert "tool_result" in step_types
    assert "edit" in step_types
    first_prompt = "\n".join(message.content for message in llm.messages_seen[0])
    assert "Update app.py to Version 2." in first_prompt


@pytest.mark.asyncio
async def test_asterwynd_runner_records_and_uses_mode(tmp_path):
    task = TaskSpec(
        id="task",
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="true",
    )
    llm = benchmark_scripted_llm()
    runner = AsterwyndRunner(llm=llm, mode="read-only", max_iterations=5)
    trace = TraceRecorder(task_id="task")

    result = await runner.run(
        task=task,
        problem_statement="Read only.",
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        trace=trace,
    )

    assert runner.run_config.mode is AgentMode.READ_ONLY
    assert trace.to_dict()["mode"] == "read_only"
    assert result.edit_count == 0

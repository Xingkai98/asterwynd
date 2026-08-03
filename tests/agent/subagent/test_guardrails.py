"""Nesting-depth and concurrency guardrails for SubAgentManager (issue 79).

Covers task 2.0 (nested-spawn prerequisite: ``expose_subagent_tools`` + depth
contextvar) and task 2.3 (concurrency/depth guardrails).
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.context import current_spawn_depth, reset_spawn_depth, set_spawn_depth
from agent.subagent.manager import SubAgentManager


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="subagent done", stop_reason="end_turn", usage=Usage(5, 5))


class SlowLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)
        return LLMResponse(content="late", stop_reason="end_turn", usage=Usage(5, 5))


class DepthProbeLLM:
    """Records the spawn-depth contextvar it observes inside the child run."""

    def __init__(self, probe: list[int]):
        self.probe = probe

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.probe.append(current_spawn_depth())
        return LLMResponse(content="probe done", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager():
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
    )


def test_build_subagent_loop_exposes_subagent_tools(manager):
    """Sub-agent loops expose the subagent tools so a child can spawn grandkids."""
    loop = manager._build_subagent_loop(AgentMode.BUILD)
    assert loop.tool_registry.get_tool("CreateSubagent") is not None
    assert loop.tool_registry.get_tool("RunSubagent") is not None
    assert loop.tool_registry.get_tool("ListSubagents") is not None


@pytest.mark.asyncio
async def test_depth_context_propagates_to_child_run():
    """The spawn-depth contextvar set before create_task is visible inside the child."""
    depths: list[int] = []
    manager = SubAgentManager(
        llm=DepthProbeLLM(depths),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
    )
    created = manager.create_subagent(name="child")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="probe",
        wait=True,
    )
    assert result["status"] == "completed"
    # root spawn => depth 1 inside the child run
    assert depths == [1]


@pytest.mark.asyncio
async def test_depth_guard_rejects_deep_nesting():
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        max_depth=1,
    )
    created = manager.create_subagent(name="child")
    token = set_spawn_depth(1)  # simulate already at depth 1
    try:
        with pytest.raises(RuntimeError, match="depth limit"):
            await manager.run_subagent(
                subagent_id=created["subagent_id"],
                task="too deep",
                wait=False,
            )
    finally:
        reset_spawn_depth(token)


@pytest.mark.asyncio
async def test_depth_guard_rejects_without_run_record():
    """A rejected spawn must not create a run record (pure pre-spawn guard)."""
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        max_depth=0,
    )
    created = manager.create_subagent(name="child")
    token = set_spawn_depth(1)
    try:
        with pytest.raises(RuntimeError, match="depth limit"):
            await manager.run_subagent(
                subagent_id=created["subagent_id"],
                task="too deep",
                wait=False,
            )
    finally:
        reset_spawn_depth(token)
    session = manager._sessions[created["subagent_id"]]
    assert session.runs == []
    assert session.active_run_id is None


@pytest.mark.asyncio
async def test_concurrency_guard_rejects_overflow():
    manager = SubAgentManager(
        llm=SlowLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        max_concurrent_runs=1,
    )
    first = manager.create_subagent(name="one")
    second = manager.create_subagent(name="two")
    await manager.run_subagent(
        subagent_id=first["subagent_id"],
        task="task one",
        wait=False,
    )
    with pytest.raises(RuntimeError, match="concurrency limit"):
        await manager.run_subagent(
            subagent_id=second["subagent_id"],
            task="task two",
            wait=False,
        )


@pytest.mark.asyncio
async def test_concurrency_limit_counts_active_runs_not_sessions():
    """Sessions may exist freely; only concurrently *running* runs are capped."""
    manager = SubAgentManager(
        llm=SlowLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        max_concurrent_runs=2,
    )
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")
    three = manager.create_subagent(name="three")
    await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    await manager.run_subagent(subagent_id=two["subagent_id"], task="t2", wait=False)
    with pytest.raises(RuntimeError, match="concurrency limit"):
        await manager.run_subagent(subagent_id=three["subagent_id"], task="t3", wait=False)

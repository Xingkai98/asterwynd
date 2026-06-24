import asyncio

import pytest

from agent.config import MyAgentConfig
from agent.llm import LLMResponse
from agent.message import Message
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager, SubagentRunRecord


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="subagent done", stop_reason="end_turn")


class FailingLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise RuntimeError("llm failed")


class SlowLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)
        return LLMResponse(content="late", stop_reason="end_turn")


@pytest.fixture
def manager():
    return SubAgentManager(
        llm=StaticLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )


def test_create_subagent_returns_session_summary(manager):
    created = manager.create_subagent(name="research", description="inspect code")
    assert created["subagent_id"]
    assert created["name"] == "research"
    assert created["mode"] == "build"
    assert created["status"] == "idle"


def test_list_subagents_returns_created_sessions(manager):
    first = manager.create_subagent(name="one")
    second = manager.create_subagent(name="two")
    items = manager.list_subagents()
    ids = {item["subagent_id"] for item in items}
    assert first["subagent_id"] in ids
    assert second["subagent_id"] in ids


def test_create_subagent_clamps_mode_to_parent():
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.READ_ONLY,
    )
    created = manager.create_subagent(name="writer", mode="build")
    assert created["mode"] == "read_only"


@pytest.mark.asyncio
async def test_run_subagent_wait_false_returns_running(manager):
    created = manager.create_subagent(name="runner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="inspect repo",
        wait=False,
    )
    assert result["subagent_id"] == created["subagent_id"]
    assert result["status"] == "running"
    assert result["run_id"]


@pytest.mark.asyncio
async def test_run_subagent_wait_true_returns_completed_result():
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )
    created = manager.create_subagent(name="runner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="inspect repo",
        wait=True,
    )
    assert result["status"] == "completed"
    assert result["summary"] == "subagent done"
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_get_subagent_run_waits_for_completion():
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )
    created = manager.create_subagent(name="runner")
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="inspect repo",
        wait=False,
    )
    result = await manager.get_subagent_run(
        subagent_id=created["subagent_id"],
        run_id=launched["run_id"],
        wait=True,
        timeout_s=1,
    )
    assert result["status"] == "completed"
    assert result["summary"] == "subagent done"


@pytest.mark.asyncio
async def test_same_subagent_rejects_concurrent_runs():
    manager = SubAgentManager(
        llm=SlowLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )
    created = manager.create_subagent(name="runner")
    await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="long task",
        wait=False,
    )
    with pytest.raises(RuntimeError, match="already has an active run"):
        await manager.run_subagent(
            subagent_id=created["subagent_id"],
            task="second task",
            wait=False,
        )


@pytest.mark.asyncio
async def test_multiple_subagents_can_run_concurrently():
    manager = SubAgentManager(
        llm=SlowLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )
    first = manager.create_subagent(name="one")
    second = manager.create_subagent(name="two")
    one = await manager.run_subagent(
        subagent_id=first["subagent_id"],
        task="task one",
        wait=False,
    )
    two = await manager.run_subagent(
        subagent_id=second["subagent_id"],
        task="task two",
        wait=False,
    )
    assert one["status"] == "running"
    assert two["status"] == "running"


@pytest.mark.asyncio
async def test_cancel_subagent_run_marks_cancelled():
    manager = SubAgentManager(
        llm=SlowLLM(),
        config=MyAgentConfig(),
        parent_mode=AgentMode.BUILD,
    )
    created = manager.create_subagent(name="runner")
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="long task",
        wait=False,
    )
    result = await manager.cancel_subagent_run(
        subagent_id=created["subagent_id"],
        run_id=launched["run_id"],
    )
    assert result["status"] == "cancelled"
    assert result["reason"] == "cancelled"


def test_inspect_transcript_summary_returns_latest_run_summary(manager):
    created = manager.create_subagent(name="runner")
    session = manager._sessions[created["subagent_id"]]
    session.runs.append(
        SubagentRunRecord(
            run_id="run-1",
            task="inspect repo",
            status="completed",
            summary="latest summary",
        )
    )
    inspected = manager.inspect_transcript(
        subagent_id=created["subagent_id"],
        scope="summary",
    )
    assert inspected["scope"] == "summary"
    assert inspected["summary"] == "latest summary"


def test_inspect_transcript_recent_messages_respects_limit(manager):
    created = manager.create_subagent(name="runner")
    session = manager._sessions[created["subagent_id"]]
    session.messages.extend(
        [
            Message(role="user", content="one"),
            Message(role="assistant", content="two"),
            Message(role="tool", content="three", tool_call_id="c1"),
        ]
    )
    inspected = manager.inspect_transcript(
        subagent_id=created["subagent_id"],
        scope="recent_messages",
        limit=2,
        include_tool_results=False,
    )
    assert inspected["scope"] == "recent_messages"
    assert inspected["truncated"] is True
    assert [msg["content"] for msg in inspected["messages"]] == ["one", "two"]

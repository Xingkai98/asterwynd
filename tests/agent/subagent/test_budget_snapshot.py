"""Budget hard-kill and snapshot/resume for SubAgentManager (issue 79).

Covers tasks 1.x (checkpoint + resume) and 2.1/2.2 (per-run token/time budget,
``budget_exceeded`` terminal state, kill-before-snapshot).
"""
import asyncio
import time

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.message import Message
from agent.run_config import AgentMode
from agent.session import SessionSnapshot
from agent.subagent.budget import BudgetExceededError, BudgetTracker
from agent.subagent.manager import SubAgentManager, SubagentRunRecord
from agent.subagent.snapshot import SubagentSnapshotStore
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="subagent done", stop_reason="end_turn", usage=Usage(5, 5))


class SlowLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)
        return LLMResponse(content="late", stop_reason="end_turn", usage=Usage(5, 5))


class TokenBurningLLM:
    """Every call burns 60 tokens; with a 100-token budget the second call trips it."""

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(
            content="working",
            stop_reason="max_tokens",
            usage=Usage(input_tokens=30, output_tokens=30),
        )


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- BudgetTracker unit ---


def test_budget_tracker_token_overrun():
    tracker = BudgetTracker(max_tokens=100)
    tracker.add(30, 30)  # 60
    assert not tracker.token_overrun()
    tracker.add(30, 30)  # 120
    assert tracker.token_overrun()


def test_budget_tracker_unbounded_when_no_limit():
    tracker = BudgetTracker(max_tokens=None)
    tracker.add(10**6, 10**6)
    assert not tracker.token_overrun()


def test_budget_exceeded_error_carries_dimension():
    err = BudgetExceededError("token", used=120, limit=100)
    assert err.dimension == "token"
    assert "120" in str(err)


# --- Token budget hard-kill ---


@pytest.mark.asyncio
async def test_token_budget_exceeded_marks_budget_exceeded(manager):
    manager.llm = TokenBurningLLM()
    created = manager.create_subagent(name="burner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="burn tokens",
        wait=True,
        max_tokens=100,
    )
    assert result["status"] == "budget_exceeded"
    assert "token" in result["reason"]


@pytest.mark.asyncio
async def test_token_budget_kill_writes_checkpoint(manager, tmp_path):
    manager.llm = TokenBurningLLM()
    created = manager.create_subagent(name="burner")
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="burn tokens",
        wait=False,
        max_tokens=100,
    )
    run_id = launched["run_id"]
    await asyncio.sleep(0.2)
    snapshot = manager._snapshot_store().load(run_id)
    assert snapshot is not None
    assert snapshot.objective == "burn tokens"


@pytest.mark.asyncio
async def test_budget_kill_backfills_usage_in_envelope(manager):
    """Review M1: a budget-exceeded run's envelope reflects real tokens consumed."""
    manager.llm = TokenBurningLLM()
    created = manager.create_subagent(name="burner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="burn tokens",
        wait=True,
        max_tokens=100,
    )
    assert result["status"] == "budget_exceeded"
    # two LLM calls at 60 tokens each before overrun
    assert result["usage"]["total_tokens"] >= 100


@pytest.mark.asyncio
async def test_checkpoint_includes_bus_summary(manager, tmp_path):
    """Review M2: a checkpoint written under an active bus carries its summary."""
    from agent.subagent.bus import MessageBus
    from agent.subagent.context import reset_bus, set_bus

    manager.llm = TokenBurningLLM()
    bus = MessageBus()
    token = set_bus(bus)
    try:
        created = manager.create_subagent(name="burner")
        launched = await manager.run_subagent(
            subagent_id=created["subagent_id"],
            task="burn tokens",
            wait=False,
            max_tokens=100,
        )
        run_id = launched["run_id"]
        await asyncio.sleep(0.2)
    finally:
        reset_bus(token)
    snapshot = manager._snapshot_store().load(run_id)
    assert snapshot is not None
    assert snapshot.bus_summary == ""  # nothing published on the bus
    # publish before the kill so the checkpoint carries it
    bus.publish(sender="w1", topic="finding", summary="found it")
    token = set_bus(bus)
    try:
        created2 = manager.create_subagent(name="burner2")
        launched2 = await manager.run_subagent(
            subagent_id=created2["subagent_id"],
            task="burn tokens",
            wait=False,
            max_tokens=100,
        )
        run_id2 = launched2["run_id"]
        await asyncio.sleep(0.2)
    finally:
        reset_bus(token)
    snapshot2 = manager._snapshot_store().load(run_id2)
    assert snapshot2 is not None
    assert "[w1/finding]" in snapshot2.bus_summary


# --- Time budget hard-kill ---


@pytest.mark.asyncio
async def test_time_budget_exceeded_marks_budget_exceeded(manager):
    manager.llm = SlowLLM()
    created = manager.create_subagent(name="slow")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="slow task",
        wait=True,
        max_time_s=0.1,
    )
    assert result["status"] == "budget_exceeded"
    assert "time" in result["reason"]


@pytest.mark.asyncio
async def test_time_budget_kill_writes_checkpoint(manager):
    manager.llm = SlowLLM()
    created = manager.create_subagent(name="slow")
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="slow task",
        wait=False,
        max_time_s=0.1,
    )
    run_id = launched["run_id"]
    # Wait past the monitor kill so the run reaches the terminal state.
    deadline = asyncio.get_event_loop().time() + 1.0
    while (
        asyncio.get_event_loop().time() < deadline
        and manager.get_subagent(created["subagent_id"])["status"] != "idle"
    ):
        await asyncio.sleep(0.05)
    snapshot = manager._snapshot_store().load(run_id)
    assert snapshot is not None
    assert snapshot.objective == "slow task"


# --- Snapshot store ---


def test_snapshot_store_roundtrip(tmp_path):
    store = SubagentSnapshotStore.for_workspace(tmp_path)
    snapshot = SessionSnapshot(
        schema_version="1.0",
        session_id="run-abc",
        created_at="2026-08-03T00:00:00+00:00",
        updated_at="2026-08-03T00:00:00+00:00",
        messages=[
            Message(role="user", content="inspect repo"),
            Message(role="assistant", content="working"),
        ],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="run-abc",
        iteration=3,
        objective="inspect repo",
        blockers=["blocked on sandbox"],
        next_steps=["retry sandbox"],
        bus_summary="[w1/finding] found it",
    )
    assert store.save(snapshot) is True
    loaded = store.load("run-abc")
    assert loaded is not None
    assert loaded.objective == "inspect repo"
    assert loaded.blockers == ["blocked on sandbox"]
    assert loaded.next_steps == ["retry sandbox"]
    assert loaded.bus_summary == "[w1/finding] found it"
    assert loaded.iteration == 3
    assert [m.content for m in loaded.messages] == ["inspect repo", "working"]


def test_snapshot_store_missing_returns_none(tmp_path):
    store = SubagentSnapshotStore.for_workspace(tmp_path)
    assert store.load("run-missing") is None


def test_snapshot_created_at_not_empty(manager, tmp_path):
    """Review M3: snapshot created_at reflects the run start (not an empty string)."""
    created = manager.create_subagent(name="runner")
    session = manager._sessions[created["subagent_id"]]
    run = SubagentRunRecord(run_id="run-t", task="task", status="running", started_at=time.time())
    session.runs.append(run)
    snapshot = manager._snapshot_store().snapshot_for_run(session, run)
    assert snapshot.created_at != ""
    assert "T" in snapshot.created_at  # ISO-8601 timestamp, not an empty string


# --- Cancel writes checkpoint, then resume ---


@pytest.mark.asyncio
async def test_cancel_writes_checkpoint_and_resume_completes(manager):
    manager.llm = SlowLLM()
    created = manager.create_subagent(name="runner")
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="long task",
        wait=False,
    )
    run_id = launched["run_id"]
    await asyncio.sleep(0.1)
    await manager.cancel_subagent_run(
        subagent_id=created["subagent_id"],
        run_id=run_id,
    )
    snapshot = manager._snapshot_store().load(run_id)
    assert snapshot is not None
    assert snapshot.objective == "long task"

    # Resume: switch the LLM to a fast one so the resumed run completes.
    manager.llm = StaticLLM()
    resumed = await manager.resume_subagent(
        subagent_id=created["subagent_id"],
        task="continue",
        run_id=run_id,
        wait=True,
    )
    assert resumed["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_missing_checkpoint_raises(manager):
    created = manager.create_subagent(name="runner")
    with pytest.raises(KeyError, match="no checkpoint"):
        await manager.resume_subagent(
            subagent_id=created["subagent_id"],
            task="continue",
            run_id="run-missing",
            wait=False,
        )

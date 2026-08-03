"""Orchestration pattern library and new subagent tools (issue 79).

Covers tasks 4.1-4.6 (OrcPattern, four patterns, bidding e2e) and task 7.x
(ResumeSubagent / RunPattern / PublishBusMessage / ReadBus tools, budget fields
in GetSubagentRun).
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.bus import MessageBus
from agent.subagent.context import current_bus, reset_bus, set_bus
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import run_pattern
from agent.tools.builtin.subagents import (
    PublishBusMessageTool,
    ReadBusTool,
    RunPatternTool,
)
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="worker result", stop_reason="end_turn", usage=Usage(5, 5))


class ScriptedLLM:
    """Returns responses by call index (for serial patterns like peer-review)."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMResponse(
            content=self.responses[idx],
            stop_reason="end_turn",
            usage=Usage(5, 5),
        )


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- run_pattern / OrcPattern ---


@pytest.mark.asyncio
async def test_run_pattern_unknown_pattern(manager):
    with pytest.raises(KeyError, match="unknown pattern"):
        await run_pattern(manager, pattern="nope", task="t")


@pytest.mark.asyncio
async def test_orchestrator_worker_aggregates(manager):
    result = await run_pattern(
        manager,
        pattern="orchestrator-worker",
        task="research",
        params={"workers": 3},
    )
    assert result["pattern"] == "orchestrator-worker"
    assert result["completed"] == 3
    assert result["failed"] == 0
    assert len(result["workers"]) == 3
    assert all(w["status"] == "completed" for w in result["workers"])


@pytest.mark.asyncio
async def test_peer_review_approves_first_round(manager):
    manager.llm = ScriptedLLM(["proposal draft", "APPROVED looks good"])
    result = await run_pattern(manager, pattern="peer-review", task="write proposal")
    assert result["pattern"] == "peer-review"
    assert result["completed"] == 2


@pytest.mark.asyncio
async def test_peer_review_critique_loop_until_approved(manager):
    manager.llm = ScriptedLLM(
        [
            "draft v1",
            "CRITIQUE missing rationale",
            "draft v2 addressing critique",
            "APPROVED now complete",
        ]
    )
    result = await run_pattern(manager, pattern="peer-review", task="write proposal")
    assert result["completed"] == 2  # producer + reviewer terminal runs
    assert manager.llm.calls >= 4  # producer + reviewer both ran twice


@pytest.mark.asyncio
async def test_bidding_selects_best(manager):
    manager.llm = ScriptedLLM(
        [
            "proposal A",
            "proposal B",
            "proposal C",
            "SELECTED 2: proposal B is most complete",
        ]
    )
    result = await run_pattern(
        manager,
        pattern="bidding",
        task="solve X",
        params={"proposers": 3},
    )
    assert result["pattern"] == "bidding"
    assert result["completed"] == 3
    assert "SELECTED 2" in result["selected"]
    assert result["selector"]["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_failure_not_fail_fast(manager):
    class FailingWorkerLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            if self.calls == 2:  # second worker fails
                raise RuntimeError("boom")
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = FailingWorkerLLM()
    result = await run_pattern(
        manager,
        pattern="orchestrator-worker",
        task="research",
        params={"workers": 2},
    )
    # gather concurrency: exactly one worker failed, the other completed
    assert result["completed"] + result["failed"] == 2
    assert result["failed"] >= 1


@pytest.mark.asyncio
async def test_run_pattern_sets_and_resets_bus_context(manager):
    assert current_bus() is None
    result = await run_pattern(manager, pattern="orchestrator-worker", task="t", params={"workers": 1})
    # bus context reset after the pattern returns
    assert current_bus() is None
    # result carries a bus snapshot payload
    assert "bus" in result
    assert "messages" in result["bus"]


# --- bus tools ---


@pytest.mark.asyncio
async def test_bus_tools_publish_and_read(manager):
    bus = MessageBus()
    token = set_bus(bus)
    try:
        pub = PublishBusMessageTool(manager)
        rd = ReadBusTool(manager)
        out = await pub.execute(sender="w1", topic="finding", content="short finding")
        assert json.loads(out)["topic"] == "finding"
        out = await rd.execute()
        data = json.loads(out)
        assert data["count"] == 1
        assert data["messages"][0]["summary"] == "short finding"
    finally:
        reset_bus(token)


@pytest.mark.asyncio
async def test_bus_tools_no_active_bus(manager):
    pub = PublishBusMessageTool(manager)
    out = await pub.execute(sender="w", topic="t", content="x")
    assert json.loads(out) == {"error": "no active message bus"}


# --- RunPattern tool ---


@pytest.mark.asyncio
async def test_run_pattern_tool(manager):
    tool = RunPatternTool(manager)
    out = await tool.execute(
        pattern="orchestrator-worker",
        task="research",
        params={"workers": 2},
    )
    data = json.loads(out)
    assert data["pattern"] == "orchestrator-worker"
    assert data["completed"] == 2


# --- budget fields in run envelope ---


@pytest.mark.asyncio
async def test_run_envelope_includes_budget_fields(manager):
    created = manager.create_subagent(name="runner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"],
        task="task",
        wait=True,
        max_tokens=500,
        max_time_s=30.0,
    )
    assert result["max_tokens"] == 500
    assert result["max_time_s"] == 30.0

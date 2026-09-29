"""编排模板语义 + bus 工具 + run 预算字段。

变化 ``workflow-builtin-templates``：``RunPattern`` / ``run_pattern`` 退役，模板语义
改经统一入口 ``RunWorkflow(template=…)`` 断言——返回体是 bounded ``parent_envelope``，
pattern 专属扁平字段（``workers`` / ``selected`` / ``selector`` / ``summary``）不再存在，
节点明细在 ``nodes[]`` 里。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.bus import MessageBus
from agent.subagent.context import current_bus, reset_bus, set_bus
from agent.subagent.manager import SubAgentManager
from agent.tools.builtin.subagents import (
    PublishBusMessageTool,
    ReadBusTool,
    RunWorkflowTool,
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


async def _run(manager, **kwargs) -> dict:
    return json.loads(await RunWorkflowTool(manager).execute(**kwargs))


def _node(envelope: dict, node_id: str) -> dict:
    return next(n for n in envelope["nodes"] if n["id"] == node_id)


# --- 模板语义（经统一入口） -------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_worker_aggregates(manager):
    out = await _run(manager, template="orchestrator-worker", task="research", params={"workers": 3})
    assert out["status"] == "completed"
    assert out["completed"] == 3  # run 口径：3 个 worker
    assert out["failed"] == 0
    assert _node(out, "workers")["status"] == "completed"
    assert _node(out, "workers")["items"] == 3


@pytest.mark.asyncio
async def test_peer_review_approves_first_round(manager):
    manager.llm = ScriptedLLM(["proposal draft", "APPROVED looks good"])
    out = await _run(manager, template="peer-review", task="write proposal")
    assert out["status"] == "completed"
    # 节点口径下是 2 条终态节点；run 口径下每节点各一次 run ⇒ 2
    assert out["completed"] == 2
    assert _node(out, "producer")["status"] == "completed"
    assert _node(out, "reviewer")["status"] == "completed"


@pytest.mark.asyncio
async def test_peer_review_critique_loop_until_approved(manager):
    manager.llm = ScriptedLLM(
        ["draft v1", "CRITIQUE missing rationale", "draft v2 addressing critique", "APPROVED now complete"]
    )
    out = await _run(manager, template="peer-review", task="write proposal")
    assert out["status"] == "completed"
    assert manager.llm.calls >= 4  # producer + reviewer both ran twice


@pytest.mark.asyncio
async def test_bidding_selects_best(manager):
    manager.llm = ScriptedLLM(
        ["proposal A", "proposal B", "proposal C", "SELECTED 2: proposal B is most complete"]
    )
    out = await _run(manager, template="bidding", task="solve X", params={"proposers": 3})
    assert out["status"] == "completed"
    selector = _node(out, "selector")
    assert selector["status"] == "completed"
    assert "SELECTED 2" in (selector.get("summary") or "")


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
    out = await _run(manager, template="orchestrator-worker", task="research", params={"workers": 2})
    # 失败不 fail-fast：图仍收敛，失败被如实计入 run 口径
    assert out["completed"] + out["failed"] == 2
    assert out["failed"] >= 1


@pytest.mark.asyncio
async def test_template_run_resets_bus_context(manager):
    """统一入口跑完后 bus context 复位（_launch_run 派发点 set/finally reset）。"""
    assert current_bus() is None
    await _run(manager, template="orchestrator-worker", task="t", params={"workers": 1})
    assert current_bus() is None


# --- bus 工具 -----------------------------------------------------------------


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

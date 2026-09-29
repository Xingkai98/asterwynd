"""截断诊断承载 ``max_rounds`` 的诚实（Q7 方案 A / D7）。

``max_rounds`` 数轮数、``recursion_limit`` 数图级 superstep，换算比依赖模板拓扑，
不存在静态上界。故诚实落在**运行期诊断**里：`graph_recursion_exceeded` 时，模板图
（携带 ``max_rounds`` 声明）的诊断 SHALL 带 ``declared_max_rounds`` /
``rounds_actually_run`` / ``limit_source``，让模型能判断截断由自身声明过大导致。

纯 DSL 图（无 ``max_rounds`` 概念）三字段为 ``null``。
"""
import pytest
from dataclasses import replace

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.bus import MessageBus
from agent.subagent.patterns import compile_pattern
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class AlwaysCritiqueLLM:
    """peer-review 永不批准 —— 图一路撞到图级 superstep 上限。"""

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="CRITIQUE needs work", stop_reason="end_turn", usage=Usage(5, 5))


def _manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=AlwaysCritiqueLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=5,
    )


@pytest.mark.asyncio
async def test_pattern_graph_truncation_reports_declared_vs_actual(tmp_path):
    """模板图带 max_rounds 声明被截断：诊断给声明值 / 实际轮数 / 界来源。

    截断场景需要图级闸先于 route 的 ``max_routes`` 触发，故显式钉住
    ``recursion_limit=25``（旧默认）——本用例测的是**截断诊断的诚实**，不是默认值
    本身（默认值回归见 ``test_recursion_limit_default.py``）。默认值调到 100 后，
    ``max_rounds=25`` 的图（77 superstep）会在默认配置下跑满，不再被图级闸截断。
    """
    manager = _manager(tmp_path)
    spec = replace(
        compile_pattern("peer-review", task="write", params={"max_rounds": 25}),
        recursion_limit=25,
    )
    scheduler = WorkflowScheduler(manager, bus=MessageBus())
    # D4：pattern 溯源（本 change 由 RunWorkflow 的 template 分支写入；此处直接置位）
    scheduler.asset_source = {
        "kind": "pattern",
        "pattern": "peer-review",
        "params": {"max_rounds": 25},
        "task": "write",
    }
    manager.register_workflow(scheduler)
    envelope = await scheduler.run(spec)

    assert envelope["status"] == "graph_recursion_exceeded"
    diag = envelope["diagnostics"]
    assert diag["declared_max_rounds"] == 25
    # 界来自 recursion_limit（默认 25），且实际轮数 < 声明值（正是「诚实」的落点）
    assert diag["limit_source"] == "recursion_limit:25"
    assert isinstance(diag["rounds_actually_run"], int)
    assert diag["rounds_actually_run"] < 25


@pytest.mark.asyncio
async def test_declared_max_rounds_survives_smaller_declaration(tmp_path):
    """声明值更小时，诊断报的是**该声明值**，不是默认。"""
    manager = _manager(tmp_path)
    spec = compile_pattern("peer-review", task="write", params={"max_rounds": 5})
    scheduler = WorkflowScheduler(manager, bus=MessageBus())
    scheduler.asset_source = {
        "kind": "pattern",
        "pattern": "peer-review",
        "params": {"max_rounds": 5},
        "task": "write",
    }
    manager.register_workflow(scheduler)
    envelope = await scheduler.run(spec)
    assert envelope["diagnostics"]["declared_max_rounds"] == 5


@pytest.mark.asyncio
async def test_plain_dsl_graph_truncation_fields_are_null(tmp_path):
    """纯 DSL 图（无 max_rounds 概念）：三字段为 null，不臆造。"""
    manager = _manager(tmp_path)
    raw = {
        "goal": "loop",
        "nodes": [
            {"id": "body", "kind": "subagent", "task": "t", "outputs": ["r"]},
            {"id": "gate", "kind": "route", "task": "g", "cases": [], "default": "body",
             "max_routes": 100000},
        ],
        "edges": [
            {"from": "body", "to": "gate"},
            {"from": "gate", "to": "body"},
        ],
        "entry": ["body"],
    }
    spec = parse_workflow_spec(raw)
    scheduler = WorkflowScheduler(manager, bus=MessageBus())
    manager.register_workflow(scheduler)
    envelope = await scheduler.run(spec)

    assert envelope["status"] == "graph_recursion_exceeded"
    diag = envelope["diagnostics"]
    assert diag["declared_max_rounds"] is None
    assert diag["rounds_actually_run"] is None
    assert diag["limit_source"] is None


@pytest.mark.asyncio
async def test_successful_run_has_no_truncation_fields(tmp_path):
    """对照的合法路径：未截断的正常图不因新字段而改变（status / 无 diagnostics 闸门）。"""
    class ApproveLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            return LLMResponse(content="APPROVED done", stop_reason="end_turn", usage=Usage(5, 5))

    manager = SubAgentManager(
        llm=ApproveLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=5,
    )
    spec = compile_pattern("peer-review", task="write", params={"max_rounds": 3})
    scheduler = WorkflowScheduler(manager, bus=MessageBus())
    scheduler.asset_source = {
        "kind": "pattern", "pattern": "peer-review", "params": {"max_rounds": 3}, "task": "write",
    }
    manager.register_workflow(scheduler)
    envelope = await scheduler.run(spec)
    assert envelope["status"] == "completed"
    # 未截断 ⇒ diagnostics 里没有我们的三个键（不污染正常路径）
    diag = envelope.get("diagnostics", {})
    assert "declared_max_rounds" not in diag
    assert "rounds_actually_run" not in diag

"""闸值钳制（Q8 = 方案 C）：在 scheduler 读取处取 ``min(declared, config)``。

核心口径（design.md D3(1)、tasks 3.5）：

- 钳制**不回写 spec**：``WorkflowSpec`` 对象保持声明值，``spec_hash`` 不被运行时
  配置污染，「加载 → 重存」判定为 ``unchanged``。
- 钳制**只作用于资产加载路径**（Q2=A）：模型当轮声明路径行为逐字不变。
- **所有对外报出限制值的出口都报实际生效值**（Q8 附加要求）。

覆盖 tasks 2.3 / 2.4b / 2.8 的钳制半程。
"""
from __future__ import annotations

import json

import pytest

from agent.config import AsterwyndConfig, WorkflowLimitsConfig, SubagentsConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.tools.builtin.subagents import RunWorkflowTool, parse_spec_for_manager
from agent.workspace_policy import WorkspacePolicy

FANOUT_SPEC = {
    "goal": "research",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "task a"},
        {"id": "b", "kind": "subagent", "task": "task b"},
        {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"},
    ],
    "edges": [
        {"from": "a", "to": "join", "reducer": "concat"},
        {"from": "b", "to": "join", "reducer": "concat"},
    ],
}


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


def _manager(tmp_path, *, recursion_limit=25, max_nodes=200, max_runs=300) -> SubAgentManager:
    config = AsterwyndConfig(
        subagents=SubagentsConfig(
            workflow=WorkflowLimitsConfig(
                recursion_limit=recursion_limit,
                max_nodes=max_nodes,
                max_runs=max_runs,
            )
        )
    )
    return SubAgentManager(
        llm=StaticLLM(),
        config=config,
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _ceiling(**overrides) -> dict[str, int]:
    base = {"recursion_limit": 25, "max_nodes": 200, "max_runs": 300}
    base.update(overrides)
    return base


# --- _eff_limit 单元 --------------------------------------------------------


def test_eff_limit_takes_min_when_ceiling_passed(tmp_path):
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000, "max_nodes": 900})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    assert scheduler._eff_limit("max_runs") == 300
    assert scheduler._eff_limit("max_nodes") == 200
    assert scheduler._eff_limit("recursion_limit") == 25


def test_eff_limit_keeps_declared_when_below_ceiling(tmp_path):
    """min 方向：声明值低于配置时**不**被抬高。"""
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 11})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    assert scheduler._eff_limit("max_runs") == 11


def test_eff_limit_without_ceiling_keeps_declared(tmp_path):
    """模型当轮声明路径（无 ceiling）行为逐字不变：声明 5000 仍是 5000。"""
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000})
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = spec
    assert scheduler._eff_limit("max_runs") == 5000


def test_clamping_does_not_rewrite_spec_or_hash(tmp_path):
    """钳制不回写 spec：对象与 spec_hash 都不被运行时配置污染。"""
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000, "max_nodes": 900})
    before_hash = spec.spec_hash
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    assert scheduler._eff_limit("max_runs") == 300
    assert spec.max_runs == 5000
    assert spec.max_nodes == 900
    assert spec.spec_hash == before_hash


# --- 出口一致性（task 2.4b：报实际生效值） ----------------------------------


def test_envelope_reports_effective_limits_when_clamped(tmp_path):
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    limits = scheduler._envelope(status="declared")["limits"]
    assert limits["max_runs"] == {"declared": 5000, "applied": 300, "clamped": True}
    assert limits["recursion_limit"]["clamped"] is False


def test_status_reports_effective_limits(tmp_path):
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    assert scheduler.status()["limits"]["max_runs"]["applied"] == 300


def test_graph_snapshot_reports_effective_limits(tmp_path):
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_nodes": 900})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    assert scheduler.workflow_graph_snapshot()["limits"]["max_nodes"]["applied"] == 200


# --- 读取落点穷举（tasks 3.5 的 9 处，逐处都被钳制覆盖） --------------------


def test_bucket_registration_uses_effective_max_runs(tmp_path):
    """``spec.max_runs * 2`` 是**派生值**，最易漏——必须用生效值。"""
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, {**FANOUT_SPEC, "max_runs": 5000})
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling())
    scheduler.spec = spec
    # 桶校准在 run() 起点执行；直接驱动该行以隔离派生值口径
    scheduler.manager.register_workflow_bucket(
        scheduler.workflow_id, scheduler._eff_limit("max_runs") * 2
    )
    assert manager._workflow_spawn_limits[scheduler.workflow_id] == 600


@pytest.mark.asyncio
async def test_clamped_run_stops_at_effective_max_runs(tmp_path):
    """端到端：声明 max_runs 远超配置时，实际按生效值收敛而非声明值。

    用一个 4 节点的 foreach 展开型图制造「声明 max_runs=1」的对照——这里只需
    证明生效值真的被主循环消费（钳到 1 时第 2 次派发被拒）。
    """
    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(
        manager,
        {
            "goal": "g",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "t"},
                {"id": "b", "kind": "subagent", "task": "t"},
                {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"},
            ],
            "edges": [
                {"from": "a", "to": "join", "reducer": "concat"},
                {"from": "b", "to": "join", "reducer": "concat"},
            ],
            "max_runs": 5000,
        },
    )
    scheduler = WorkflowScheduler(manager, limit_ceiling=_ceiling(max_runs=1))
    scheduler.manager.register_workflow(scheduler)
    envelope = await scheduler.run(spec)
    assert envelope["status"] == "graph_recursion_exceeded"
    assert envelope["limits"]["max_runs"]["applied"] == 1


# --- 模型声明路径逐字不变（Q2=A 的回归锁） ----------------------------------


@pytest.mark.asyncio
async def test_model_declared_path_is_not_clamped(tmp_path):
    """声明值**高于**配置值时仍原样生效（既有测试用 7/11 小于默认，挡不住）。

    对照面：资产加载路径在同一 spec 上会被钳到 300。
    """
    manager = _manager(tmp_path)
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            spec={**FANOUT_SPEC, "max_runs": 5000}, wait=True
        )
    )
    assert out["status"] == "completed"
    assert out["limits"]["max_runs"] == {
        "declared": 5000,
        "applied": 5000,
        "clamped": False,
    }

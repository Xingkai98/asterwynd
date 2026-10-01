"""#275 grill 复核：D2 的 node_budget 到底该用哪个计数？

grill 指出 design 的 `expanded = len(plan.nodes)` 忽略了 foreach 展开项。
本脚本实测三个候选值在「宽扇入超限」与「正常」两种图上的表现：

  A) len(plan.nodes)          —— 静态图节点数（声明 + 自动插层，foreach 算 1）
  B) scheduler._expanded_nodes —— max_nodes 闸门实际计费的高水位（foreach 每项算 1）
  C) len(scheduler._graph().nodes) —— Web UI 的「图规模权威值」

关键问题：**撞闸时哪个值能让 headroom ≤ 0**（否则报告会在已崩的图上显示正余量）。
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

WT = "/home/happy/my-agent/.claude/worktrees/workflow-limit-visibility"
sys.path.insert(0, WT)

from agent.config import AsterwyndConfig, SubagentsConfig, WorkflowLimitsConfig
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.tools.builtin.subagents import DryRunWorkflowTool
from agent.workspace_policy import WorkspacePolicy


class _LLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise AssertionError("REAL LLM MUST NOT BE CALLED")


def make_spec(items: int):
    return {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach",
             "items": [f"i{k}" for k in range(items)], "task": "work on {item}"},
            {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
        ],
        "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
        "entry": ["fan"], "terminal": ["agg"],
    }


async def probe(max_nodes: int, items: int, root: Path):
    cfg = AsterwyndConfig(subagents=SubagentsConfig(
        workflow=WorkflowLimitsConfig(max_nodes=max_nodes)))
    mgr = SubAgentManager(
        llm=_LLM(), config=cfg, parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=root),
    )
    # 直接在 scheduler 上跑，读私有计数（与实现同源）
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.tools.builtin.subagents import parse_spec_for_manager
    spec = parse_spec_for_manager(mgr, make_spec(items))
    sched = WorkflowScheduler(mgr)
    result = await sched.run(spec)

    plan_nodes = len(sched._plan.nodes) if sched._plan else None
    try:
        graph_nodes = len(sched._graph().nodes)
    except Exception as exc:  # noqa: BLE001
        graph_nodes = f"ERR:{exc}"
    return {
        "max_nodes": max_nodes, "items": items,
        "run_status": result.get("status"),
        "A_len_plan_nodes": plan_nodes,
        "B_expanded_nodes": sched._expanded_nodes,
        "C_len_graph_nodes": graph_nodes,
        "B_headroom": None if plan_nodes is None else max_nodes - sched._expanded_nodes,
        "A_headroom": None if plan_nodes is None else max_nodes - plan_nodes,
    }


async def main():
    out = []
    with tempfile.TemporaryDirectory(prefix="t275nb-") as tmp:
        root = Path(tmp)
        # 正常：20 项、max_nodes=200（设计预期 expanded>declared）
        out.append(await probe(200, 20, root))
        # 撞闸：20 项、max_nodes=5（闸门必触发）
        out.append(await probe(5, 20, root))
        # 边界：20 项、max_nodes=24（刚好 = plan(4)+items(20)，应通过）
        out.append(await probe(24, 20, root))
        # 边界：20 项、max_nodes=23（差 1，应撞闸）
        out.append(await probe(23, 20, root))
        # 窄扇入：2 项（不触发自动插层）
        out.append(await probe(200, 2, root))
    print(json.dumps(out, ensure_ascii=False, indent=2))


asyncio.run(main())

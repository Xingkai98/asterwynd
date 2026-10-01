"""#275 侦察补充：dry run 撞闸时，报告到底露出什么？（决定 spec delta 措辞边界）

三个假设：
  T1 dry run 撞 max_nodes 时，报告是否有可读的闸门信息（还是只有裸 run_status）
  T2 dry run 撞 max_nodes 时，报告是否给出生效上限值与「超了多少」
  T3 图**通过** dry run（未撞闸）时，报告是否给出任何「离闸多远」的信号（应为 0）
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


async def run_with_max_nodes(limit_nodes: int, items: int, root: Path):
    cfg = AsterwyndConfig(subagents=SubagentsConfig(
        workflow=WorkflowLimitsConfig(max_nodes=limit_nodes)))
    mgr = SubAgentManager(
        llm=_LLM(), config=cfg, parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=root),
    )
    tool = DryRunWorkflowTool(mgr)
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach",
             "items": [f"i{k}" for k in range(items)], "task": "work on {item}"},
            {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
        ],
        "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
        "entry": ["fan"], "terminal": ["agg"],
    }
    return json.loads(await tool.execute(spec=spec))


async def main():
    out = {}
    with tempfile.TemporaryDirectory(prefix="t275t-") as tmp:
        root = Path(tmp)
        # 20 项 foreach → 展开 + 自动插层 > max_nodes(3) → 必然撞闸
        trip = await run_with_max_nodes(3, 20, root)
        out["T1_trip_run_status"] = trip.get("run_status")
        out["T1_trip_status"] = trip.get("status")
        out["T1_trip_keys"] = sorted(trip.keys())
        out["T2_trip_has_limits"] = "limits" in trip
        out["T2_trip_has_diagnostics"] = "diagnostics" in trip
        out["T2_trip_warnings_head"] = (trip.get("warnings") or [])[:3]
        out["T2_trip_node_count"] = len(trip.get("nodes", []))
        # 是否给出「生效上限」或「超了多少」
        blob = json.dumps(trip, ensure_ascii=False)
        out["T2_blob_mentions_3"] = "max_nodes" in blob or "> 3" in blob or "exceed" in blob.lower()

        # 通过 dry run（max_nodes=200，20 项能过）→ 应无任何离闸信号
        ok = await run_with_max_nodes(200, 20, root)
        out["T3_ok_run_status"] = ok.get("run_status")
        out["T3_ok_has_limits"] = "limits" in ok
        out["T3_ok_keys"] = sorted(ok.keys())
        out["T3_ok_node_count"] = len(ok.get("nodes", []))

    print(json.dumps(out, ensure_ascii=False, indent=2))


asyncio.run(main())

"""#275 侦察：确认「生效上限 / 声明 vs 展开 / route max_routes」在模型可见处是否缺失。

只读探针：不调真实 LLM、不写盘、不注册。逐个检查三个假设：
  G1 dry run 报告顶层无生效上限（recursion_limit / max_nodes / max_runs）
  G2 dry run 报告无「声明节点数 vs 展开节点数」汇总（只有逐节点 auto_inserted）
  G3 dry run 报告 route 条目无生效 max_routes（模型看不到自己用了多少 / 上限多少）
  G4 DeclareWorkflow / RunWorkflow / DryRunWorkflow 的工具描述均未披露图级三闸默认值
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

WT = "/home/happy/my-agent/.claude/worktrees/workflow-limit-visibility"
sys.path.insert(0, WT)

from agent.config import AsterwyndConfig
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import limits_report, GraphRecursionError
from agent.tools.builtin.subagents import (
    DryRunWorkflowTool,
    DeclareWorkflowTool,
    RunWorkflowTool,
    _spec_bounds,
)
from agent.workspace_policy import WorkspacePolicy

results: dict[str, object] = {}


class _LLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise AssertionError("REAL LLM MUST NOT BE CALLED")


async def main():
    with tempfile.TemporaryDirectory(prefix="t275-") as tmp:
        root = Path(tmp)
        mgr = SubAgentManager(
            llm=_LLM(), config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
            workspace_policy=WorkspacePolicy(workspace_root=root),
        )
        tool = DryRunWorkflowTool(mgr)

        # 宽扇入（20 项 foreach）触发自动插层；外加一个 route 节点。
        spec = {
            "goal": "g",
            "nodes": [
                {"id": "fan", "kind": "foreach",
                 "items": [f"i{k}" for k in range(20)], "task": "work on {item}"},
                {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
                {"id": "gate", "kind": "route", "max_routes": 3,
                 "cases": [{"when": "GAPS", "to": "fan"}], "default": "agg"},
            ],
            "edges": [
                {"from": "fan", "to": "agg", "reducer": "concat"},
                {"from": "agg", "to": "gate", "channel": "summary"},
                {"from": "gate", "to": "fan"},
            ],
            "entry": ["fan"],
            "terminal": ["agg"],
        }
        rep = json.loads(await tool.execute(spec=spec))
        if "nodes" not in rep:
            print("REPORT (no nodes):", json.dumps(rep, ensure_ascii=False, indent=2)[:2000])
            return

        # --- G1：顶层有没有生效上限？ ---
        results["G1_top_level_limit_fields"] = sorted(
            k for k in rep if "limit" in k.lower() or "cap" in k.lower()
        )
        results["G1_report_has_limits_key"] = "limits" in rep

        # --- G2：有没有「声明 vs 展开」汇总？ ---
        results["G2_declared_node_count"] = len(spec["nodes"])
        results["G2_report_node_count"] = len(rep["nodes"])
        auto = [n["id"] for n in rep["nodes"] if n.get("auto_inserted")]
        results["G2_auto_inserted_count"] = len(auto)
        results["G2_top_level_count_fields"] = sorted(
            k for k in rep if "count" in k.lower() or "expand" in k.lower()
        )

        # --- G3：route 条目有没有 max_routes / 已用轮次？ ---
        gate = next((n for n in rep["nodes"] if n["id"] == "gate"), None)
        results["G3_route_entry_keys"] = sorted(gate.keys()) if gate else None
        results["G3_route_has_max_routes"] = bool(gate and "max_routes" in gate)

        # --- G4：工具描述是否披露图级三闸默认值？ ---
        bounds = _spec_bounds(mgr)
        results["G4_bounds"] = bounds
        for name, cls in (
            ("DeclareWorkflow", DeclareWorkflowTool),
            ("RunWorkflow", RunWorkflowTool),
            ("DryRunWorkflow", DryRunWorkflowTool),
        ):
            desc = getattr(cls(mgr), "description", "") or ""
            results[f"G4_{name}_desc_len"] = len(desc)
            results[f"G4_{name}_mentions_max_nodes"] = "max_nodes" in desc
            results[f"G4_{name}_mentions_recursion_limit"] = "recursion_limit" in desc
            results[f"G4_{name}_mentions_200"] = str(bounds["default_max_nodes"]) in desc

        # --- 对照：机制本身是存在的（只是没接上 dry run） ---
        from agent.tools.builtin.subagents import parse_spec_for_manager
        parsed = parse_spec_for_manager(mgr, spec)
        results["CTRL_limits_report_available"] = limits_report(parsed, {})

        # --- 对照：纯 DSL 图超限时模型实际拿到什么（订正 #275 初稿的过度断言） ---
        exc = GraphRecursionError(
            steps=100, limit=100, current_nodes=["gate"], reason="recursion_limit",
            message="GraphRecursionError: workflow reached recursion_limit 100",
        )
        results["CTRL_pure_dsl_exc_to_dict"] = exc.to_dict()

    print(json.dumps(results, ensure_ascii=False, indent=2))


asyncio.run(main())

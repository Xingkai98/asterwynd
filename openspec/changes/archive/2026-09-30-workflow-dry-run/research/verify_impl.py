"""#273 主 session 独立验证：直接调 DryRunWorkflow，核对 design 的核心承诺。

不依赖实现方的测试——用我自己构造的图与断言。
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/happy/my-agent/.claude/worktrees/workflow-dry-run")

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.tools.builtin.subagents import DryRunWorkflowTool
from agent.workspace_policy import WorkspacePolicy

ok = []
bad = []


def check(name, cond, detail=""):
    (ok if cond else bad).append(f"{name}{(' — ' + detail) if detail else ''}")


class _LLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise AssertionError("REAL LLM MUST NOT BE CALLED IN A DRY RUN")


async def run(spec, script=None, root=None):
    mgr = SubAgentManager(
        llm=_LLM(), config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=root),
    )
    tool = DryRunWorkflowTool(mgr)
    kw = {"spec": spec}
    if script is not None:
        kw["script"] = script
    return json.loads(await tool.execute(**kw)), mgr


async def main():
    with tempfile.TemporaryDirectory(prefix="t273v-") as tmp:
        root = Path(tmp)
        before = {p for p in root.rglob("*") if p.is_file()}

        # ---- 图 1：foreach + collect 聚合（验 G1 坍缩） ----
        # 注：3 项不触发 auto 层（阈值 MAX_FAN_IN=10），G3 另用 20 项图（见下）。
        spec = {
            "goal": "g",
            "nodes": [
                {"id": "fan", "kind": "foreach", "items": ["alpha", "beta", "gamma"],
                 "task": "work on {item}"},
                {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
            ],
            "edges": [{"from": "fan", "to": "merge", "reducer": "concat"}],
            "terminal": ["merge"],
        }
        rep, mgr = await run(spec, root=root)

        check("报告标记 simulated", rep.get("simulated") is True)
        check("报告无 workflow_id（D8）", "workflow_id" not in rep)

        # G1：foreach 三项各可见
        fan = next((n for n in rep["nodes"] if n["id"] == "fan"), None)
        recv = (fan or {}).get("received")
        items = json.dumps(recv, ensure_ascii=False) if recv is not None else ""
        n_items = sum(1 for it in ("alpha", "beta", "gamma") if it in items)
        check("G1 foreach 三项各自可见（不坍缩）", n_items == 3,
              f"命中 {n_items}/3 项；received={str(recv)[:120]}")

        # G3：auto 层可见 —— 必须用**宽扇入**图（MAX_FAN_IN=10，20 项才触发插层）
        spec_wide = {
            "goal": "g",
            "nodes": [
                {"id": "fan", "kind": "foreach",
                 "items": [f"i{k}" for k in range(20)], "task": "work on {item}"},
                {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
            ],
            "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
            "terminal": ["agg"],
        }
        rep_w, _ = await run(spec_wide, root=root)
        auto = [n for n in rep_w["nodes"] if n.get("auto_inserted")]
        check("G3 自动插入层出现在报告里（20 项宽扇入）", len(auto) >= 1,
              f"auto 节点={[n['id'] for n in auto]}")
        check("G3 报告节点数 > spec 节点数（自动层被算进去）", len(rep_w["nodes"]) > 2,
              f"报告 {len(rep_w['nodes'])} 个 vs spec 2 个")

        # D4b：聚合产出是有界投影，不是替身回复
        merge = next((n for n in rep["nodes"] if n["id"] == "merge"), None)
        prod = str((merge or {}).get("produced", ""))
        check("D4b 聚合产出是拼接投影（非替身回复）",
              "alpha" in prod or "beta" in prod or "gamma" in prod,
              f"produced={prod[:100]!r}")

        # 隔离
        after = {p for p in root.rglob("*") if p.is_file()}
        check("D4 调用方 workspace 零新增文件", not (after - before),
              f"新增={sorted(str(p) for p in (after - before))[:3]}")
        check("D4 调用方注册表为空", not mgr._workflows)
        check("D4 调用方无 store", not getattr(mgr, "_workflow_stores", {}))

        # ---- 图 2：a→mid→gate（验 S1 与 script 生效，避开 S2 陷阱） ----
        spec2 = {
            "goal": "g",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "ta"},
                {"id": "mid", "kind": "subagent", "task": "tm"},
                {"id": "gate", "kind": "route",
                 "cases": [{"when": "GAPS", "to": "rework"}], "default": "done"},
                {"id": "rework", "kind": "subagent", "task": "tr"},
                {"id": "done", "kind": "subagent", "task": "td"},
            ],
            "edges": [{"from": "a", "to": "mid"}, {"from": "mid", "to": "gate"},
                      {"from": "gate", "to": "rework"}, {"from": "gate", "to": "done"}],
            "terminal": ["done", "rework"],
        }
        # 盲回显：route 必走 default（S4）
        rep_blind, _ = await run(spec2, root=root)
        g = next(n for n in rep_blind["nodes"] if n["id"] == "gate")
        check("S4 盲回显时 route 走 default", g.get("used_default") is True,
              f"matched={g.get('matched')!r}")

        # script 注入：route 命中（S1 形态下 script 生效）
        rep_s, _ = await run(spec2, script={"mid": "GAPS: needs work"}, root=root)
        g2 = next(n for n in rep_s["nodes"] if n["id"] == "gate")
        check("Q6/T-8 script 注入使 route 命中 GAPS",
              g2.get("matched") == "GAPS" and "rework" in (g2.get("walked_to") or []),
              f"matched={g2.get('matched')!r} walked={g2.get('walked_to')}")

        # S1：route 读直接上游
        check("S1 input_seen 是直接上游 mid 的产出",
              "GAPS" in str(g2.get("input_seen", "")),
              f"input_seen={str(g2.get('input_seen'))[:80]!r}")

        # input_sources 归属
        srcs = g2.get("input_sources")
        check("Q6 input_sources 可归属到 mid", bool(srcs) and any(
            (s.get("resolved_to") == "mid") for s in (srcs or [])),
            f"input_sources={srcs}")

        # ---- 边界声明 ----
        notes = " ".join(rep.get("notes") or [])
        check("D6 notes 声明不调模型/不写盘",
              "no model calls" in notes and "writes nothing" in notes)
        check("R10 notes 区分 ANSWERABLE / NOT ANSWERABLE",
              "ANSWERABLE" in notes and "NOT ANSWERABLE" in notes)

        # schema parity
        from agent.tools.builtin.subagents import DeclareWorkflowTool
        dw = DryRunWorkflowTool(mgr).parameters
        dc = DeclareWorkflowTool(mgr).parameters
        check("T-12 spec schema 与 DeclareWorkflow 逐字相等",
              json.dumps(dw["properties"]["spec"], sort_keys=True)
              == json.dumps(dc["properties"]["spec"], sort_keys=True))

        # Q5 防滥用
        tool = DryRunWorkflowTool(mgr)
        check("Q5 计数器挂在工具实例上", hasattr(tool, "_calls"))

    print(f"\n{'='*70}")
    print(f"PASS {len(ok)} / FAIL {len(bad)}")
    print(f"{'='*70}")
    for line in ok:
        print(f"  ✓ {line}")
    for line in bad:
        print(f"  ✗ {line}")
    return 1 if bad else 0


sys.exit(asyncio.run(main()))

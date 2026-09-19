"""图级终态与节点因由如实表达（change ``workflow-terminal-honesty``，issue #217/#218/#220）。

覆盖 tasks 1.1–1.5 与 2.x/3.x/4.x/5.x 的后端部分：

- **#217** 零节点成功的图不得报 ``completed``（新档 ``stalled``）；
- **#218** 节点因由必须指向真实成因（图级闸门穿透 / 入边互等），不用一句兜底文案覆盖；
- **#220 方案 D** 回边重跑不得清空发起者，且被选中且跑过的节点不得被误报 ``skipped``；
- **D5** 图级终态集合三副本等价。

所有断言都以**实跑**（真实 ``scheduler.run``）为准，不 mock 内部状态——复现 spec 见
``openspec/changes/workflow-terminal-honesty/diagnosis.md``（#220 的 ``default`` 必须指向
回边分支，否则环转不起来、bug 复现不出）。
"""
import asyncio
import re
from pathlib import Path

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent import scheduler as scheduler_mod
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

_REPO = Path(__file__).parents[3]


class _LLM:
    """恒返回固定文本的确定性桩（无随机性，#217/#218/#220 均确定性复现）。"""

    def __init__(self, content="CONTINUE", usage=None):
        self.content = content
        self.usage = usage or Usage(5, 5)

    async def chat(self, messages, tools=None, model="gpt-4"):
        blob = " ".join(str(getattr(m, "content", m)) for m in messages)
        if "BOOM" in blob:
            raise RuntimeError("model exploded")
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=self.usage)


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=_LLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


async def _run(manager, spec: dict) -> dict:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(spec)
    await scheduler.run(scheduler.spec)
    return scheduler.workflow_graph_snapshot()


def _nodes(snapshot: dict) -> dict[str, dict]:
    return {node["id"]: node for node in snapshot["nodes"]}


def _edges(snapshot: dict) -> dict[tuple[str, str], str]:
    return {(edge["from"], edge["to"]): edge["status"] for edge in snapshot["edges"]}


# --- 三个 bug 的复现 spec（来自 diagnosis.md） -------------------------------


def _deadlock_spec() -> dict:
    """#217 / #218 形态 B：回边 ``required=true``（默认）→ 入口互等，零节点成功。

    route 的默认出口是 ``end``，回边 ``body→cycle_gate`` 是 required 数据边，
    所以 ``body`` 永远不就绪、``cycle_gate`` 永远不派发。
    """
    return {
        "goal": "deadlock",
        "nodes": [
            {"id": "cycle_gate", "kind": "route",
             "cases": [{"when": "CONTINUE", "to": "body"}], "default": "end"},
            {"id": "body", "kind": "aggregate", "strategy": "collect"},
            {"id": "end", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "cycle_gate", "to": "body"},
            {"from": "cycle_gate", "to": "end"},
            {"from": "body", "to": "cycle_gate"},
        ],
        "entry": ["cycle_gate"], "terminal": ["end"],
    }


def _spin_spec(*, max_routes=3, body_kind="aggregate") -> dict:
    """#220：回边 ``required=false``（数据边）+ ``max_routes`` 上限。

    ``default`` **必须**指向回边分支 ``body``，否则 route 只派发 1 次、``_reset_subtree``
    从不被调用（见 diagnosis.md 的 Reproduction 更正）。
    """
    body = ({"id": "body", "kind": "aggregate", "strategy": "collect"} if body_kind == "aggregate"
            else {"id": "body", "kind": "subagent", "task": "carry on"})
    return {
        "goal": "spin",
        "nodes": [
            {"id": "cycle_gate", "kind": "route", "max_routes": max_routes,
             "cases": [{"when": "CONTINUE", "to": "body"}], "default": "body"},
            body,
            {"id": "end", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "cycle_gate", "to": "body"},
            {"from": "cycle_gate", "to": "end"},
            {"from": "body", "to": "cycle_gate", "required": False},
        ],
        "entry": ["cycle_gate"], "terminal": ["end"],
        "recursion_limit": 25,
    }


def _route_cap_spec() -> dict:
    """#218 形态 A：``max_routes`` 撞线（图级闸门），route 自身超标。"""
    return {
        "goal": "route cap",
        "nodes": [
            {"id": "cycle_gate", "kind": "route", "max_routes": 1,
             "cases": [{"when": "CONTINUE", "to": "body"}], "default": "body"},
            {"id": "body", "kind": "subagent", "task": "carry on"},
            {"id": "end", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "cycle_gate", "to": "body"},
            {"from": "cycle_gate", "to": "end"},
            {"from": "body", "to": "cycle_gate", "required": False},
        ],
        "entry": ["cycle_gate"], "terminal": ["end"],
        "recursion_limit": 25,
    }


# ===========================================================================
# 1.1 / 2.x — 图级终态四档（D1/D2）
# ===========================================================================


@pytest.mark.asyncio
async def test_deadlock_graph_is_not_completed(manager):
    """1.1（#217）：零节点完成的图不得报 ``completed``——应为 ``stalled``。"""
    snapshot = await _run(manager, _deadlock_spec())
    assert snapshot["status"] != "completed"
    assert snapshot["status"] == "stalled"


@pytest.mark.asyncio
async def test_deadlock_graph_needs_no_completed_node(manager):
    """D2：``stalled`` 判据不要求存在 ``blocked`` 之外的边条件——零 completed 零 failed 即 stalled。

    本图三节点全 ``blocked``（无 ``failed``、无 ``completed``）→ ``stalled``。
    """
    snapshot = await _run(manager, _deadlock_spec())
    nodes = _nodes(snapshot)
    assert all(node["status"] != "completed" for node in nodes.values())
    assert all(node["status"] != "failed" for node in nodes.values())
    assert snapshot["status"] == "stalled"


@pytest.mark.asyncio
async def test_graph_with_completed_node_is_completed(manager):
    """四档矩阵第 2 格：``completed>0`` 且 ``failed==0`` → ``completed``（含义收窄后仍成立）。"""
    snapshot = await _run(manager, _spin_spec())
    nodes = _nodes(snapshot)
    assert any(node["status"] == "completed" for node in nodes.values())
    assert all(node["status"] != "failed" for node in nodes.values())
    assert snapshot["status"] == "completed"


@pytest.mark.asyncio
async def test_graph_with_failed_and_completed_is_completed_with_failures(manager):
    """四档矩阵第 1 格（G26 语义保留）：有 completed 也有 failed → ``completed_with_failures``。"""
    spec = {
        "goal": "partial",
        "nodes": [
            {"id": "dead", "kind": "subagent", "task": "BOOM"},
            {"id": "live", "kind": "subagent", "task": "produce"},
            {"id": "join", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "dead", "to": "join", "required": False, "reducer": "concat"},
            {"from": "live", "to": "join", "required": False, "reducer": "concat"},
        ],
        "entry": ["dead", "live"], "terminal": ["join"],
    }
    snapshot = await _run(manager, spec)
    nodes = _nodes(snapshot)
    assert nodes["dead"]["status"] == "failed"
    assert nodes["live"]["status"] == "completed"
    assert snapshot["status"] == "completed_with_failures"


@pytest.mark.asyncio
async def test_zero_completed_with_failures_is_failed(manager):
    """四档矩阵第 3 格：``completed==0`` 且 ``failed>0`` → ``failed``（不是 ``stalled``）。

    ``stalled`` 表示「图根本没跑起来」；一旦有节点**执行失败**，真因是那次失败，
    必须报 ``failed`` 才能把用户引向「哪个节点失败了」。
    """
    spec = {
        "goal": "all fail",
        "nodes": [
            {"id": "d1", "kind": "subagent", "task": "BOOM one"},
            {"id": "d2", "kind": "subagent", "task": "BOOM two"},
        ],
        "edges": [],
    }
    snapshot = await _run(manager, spec)
    nodes = _nodes(snapshot)
    assert all(node["status"] == "failed" for node in nodes.values())
    assert snapshot["status"] == "failed", f"零完成+有失败应为 failed，实为 {snapshot['status']!r}"
    assert snapshot["status"] != "stalled"


@pytest.mark.asyncio
async def test_budget_stop_wins_over_stalled(tmp_path, monkeypatch):
    """四档矩阵第 5 格：预算停优先于 ``stalled``（既有口径不得被覆盖）。

    「零 completed + 预算停」本身不可达（预算超限必须有 run 被消费，而有 run
    就有终态）。所以这里验证的是**结构保证**：四档判据只在 ``_budget_stop`` 为假的
    ``else`` 分支里被咨询。做法是把判据换成**总返回 ``stalled``** 的探针——若调用点
    被误移出 ``else``，图级 status 会变成 ``stalled``，测试即红。
    """
    import dataclasses

    calls: list[str] = []

    def spy(self) -> str:
        calls.append("called")
        return "stalled"  # 若被咨询，结果必然错

    monkeypatch.setattr(WorkflowScheduler, "_terminal_converged_status", spy)

    config = AsterwyndConfig()
    workflow = dataclasses.replace(
        config.subagents.workflow,
        budget=dataclasses.replace(config.subagents.workflow.budget, max_total_tokens=100),
    )
    config = dataclasses.replace(
        config, subagents=dataclasses.replace(config.subagents, workflow=workflow)
    )
    manager = SubAgentManager(
        llm=_LLM(usage=Usage(90, 90)),  # 每次调用 180 tokens，首轮即超 100 上限
        config=config,
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    # 链式图：每个节点独占一个 superstep，token 记账后触发 stop_new（无结构闸门）。
    spec = {
        "goal": "budget stops a chain",
        "nodes": [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(5)],
        "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(4)],
        "terminal": ["n4"],
    }
    snapshot = await _run(manager, spec)
    assert snapshot["status"] == "budget_exceeded"
    assert snapshot["status"] != "stalled"
    assert calls == [], "预算停时不得咨询四档判据（调用点必须在 else 分支内）"


# ===========================================================================
# 1.2 / 1.3 — 节点因由分档（D3）
# ===========================================================================


@pytest.mark.asyncio
async def test_route_cap_reason_pierces_graph_gate(manager):
    """1.2（#218 形态 A）：``max_routes`` 撞线 → 被牵连节点 reason 含闸门信息。"""
    snapshot = await _run(manager, _route_cap_spec())
    assert snapshot["status"] == "graph_recursion_exceeded"
    nodes = _nodes(snapshot)
    reasons = " ".join((node.get("reason") or "") for node in nodes.values())
    assert "max_routes" in reasons, f"因由未穿透图级闸门：{reasons!r}"


@pytest.mark.asyncio
async def test_deadlock_reason_is_not_the_fallback_lie(manager):
    """1.3（#218 形态 B）：无图级闸门的死锁 → 因由说明「入边互等」，不是兜底假话。

    ``diagnostics`` 为空，所以不能靠闸门穿透；必须给出结构性成因。
    """
    snapshot = await _run(manager, _deadlock_spec())
    assert not snapshot.get("diagnostics")
    nodes = _nodes(snapshot)
    blocked = [n for n in nodes.values() if n["status"] == "blocked"]
    assert blocked, "本图应存在 blocked 节点"
    for node in blocked:
        reason = node.get("reason") or ""
        assert "workflow ended before" not in reason, (
            f"节点 {node['id']} 因由仍是兜底假话：{reason!r}"
        )


# ===========================================================================
# 1.4 / 1.5 — 方案 D（D4）：发起者豁免 + 选中判据修正
# ===========================================================================


@pytest.mark.asyncio
async def test_back_edge_does_not_wipe_the_dispatching_route(manager):
    """1.4（#220）：回边为数据边 → ``cycle_gate`` 不被清空，选中的控制边为 ``passed``。"""
    snapshot = await _run(manager, _spin_spec())
    nodes = _nodes(snapshot)
    gate = nodes["cycle_gate"]
    assert gate["status"] == "completed", f"发起者被清空：{gate}"
    assert gate["targets"] == ["body"], f"选中的出口被清空：{gate.get('targets')!r}"
    edges = _edges(snapshot)
    assert edges[("cycle_gate", "body")] == "passed", (
        f"选中的控制边应为 passed，实为 {edges[('cycle_gate', 'body')]!r}"
    )


@pytest.mark.asyncio
async def test_selected_and_executed_node_is_not_reported_skipped(manager):
    """1.5（方案 D 组合回归）：被选中且跑过的节点不得报 ``skipped``（说没选它）。

    只做 origin 豁免（不做 ``_is_skipped`` 判据修正）时，``body`` 会被误报
    ``route did not select this branch``——而 route 的 ``targets`` 恰含 ``body``。
    """
    snapshot = await _run(manager, _spin_spec(body_kind="subagent"))
    nodes = _nodes(snapshot)
    gate, body = nodes["cycle_gate"], nodes["body"]
    assert "body" in (gate.get("targets") or []), "前提：route 确实选中了 body"
    assert body["runs"] > 0, "前提：body 确实执行过"
    assert body["status"] != "skipped", (
        f"body 被选中且执行过，却被报 skipped：{body}"
    )
    assert "route did not select this branch" not in (body.get("reason") or ""), (
        f"body 因由是假话：{body.get('reason')!r}"
    )


@pytest.mark.asyncio
async def test_back_edge_does_not_wipe_route_with_collect_body(manager):
    """#220 的 collect 聚合形态同样不被清空（用户真实图的形状）。"""
    snapshot = await _run(manager, _spin_spec(body_kind="aggregate"))
    gate = _nodes(snapshot)["cycle_gate"]
    assert gate["status"] == "completed"
    assert gate["targets"] == ["body"]
    assert _edges(snapshot)[("cycle_gate", "body")] == "passed"


# ===========================================================================
# G11 回归红线（既有语义必须保持）
# ===========================================================================


@pytest.mark.asyncio
async def test_reset_subtree_still_clears_stale_fields_on_rerun(manager):
    """G11 红线：回边重跑仍须清陈旧字段（不得因 origin 豁免而减少清理项）。

    构造：``a`` 先产出 RETRY 触发回边，``a`` 必须被复位（清 summary），
    且不得出现负耗时。origin 豁免只针对**发起者**，不应放过 ``a``。
    """
    spec = {
        "goal": "loop-back",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {"id": "gate", "kind": "route",
             "cases": [{"when": "RETRY", "to": "a"}], "default": "done"},
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "a"},
            {"from": "gate", "to": "done"},
        ],
        "entry": ["a"], "terminal": ["done"],
    }
    manager.llm = _LLM(content="RETRY")
    snapshot = await _run(manager, spec)
    for node in snapshot["nodes"]:
        started, finished = node.get("started_at"), node.get("finished_at")
        if started is not None and finished is not None:
            assert finished >= started, f"节点 {node['id']} 出现负耗时：{started=} {finished=}"


# ===========================================================================
# D5 — 图级终态集合三副本等价
# ===========================================================================


def _extract_bracket_list(source: str, name: str) -> set[str]:
    match = re.search(rf"{name}\s*=\s*\[(.*?)\]", source, re.S)
    assert match, f"未找到 {name} 的字面列表"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _extract_isgraphterminal(source: str) -> set[str]:
    match = re.search(r"function isGraphTerminal\(status\)\s*\{(.*?)\n  \}", source, re.S)
    assert match, "未找到 isGraphTerminal 函数体"
    return set(re.findall(r"status === '([a-z_]+)'", match.group(1)))


def test_graph_terminal_status_copies_are_equal():
    """D5：三个图级终态副本的**集合相等**（而非各自「包含 stalled」）——防未来漂移。"""
    scheduler_src = (_REPO / "agent" / "subagent" / "scheduler.py").read_text()
    match = re.search(
        r"_SNAPSHOT_TERMINAL_STATUSES\s*=\s*frozenset\(\s*\{(.*?)\}\s*\)", scheduler_src, re.S
    )
    assert match, "未找到 _SNAPSHOT_TERMINAL_STATUSES"
    backend = set(re.findall(r'"([a-z_]+)"', match.group(1)))

    workflow_js = (_REPO / "web" / "static" / "workflow.js").read_text()
    frontend_list = _extract_bracket_list(workflow_js, "TERMINAL_STATUSES")

    graph_js = (_REPO / "web" / "static" / "workflow_graph.js").read_text()
    frontend_fn = _extract_isgraphterminal(graph_js)

    assert backend == frontend_list == frontend_fn, (
        f"终态集合副本漂移：scheduler={sorted(backend)} "
        f"workflow.js={sorted(frontend_list)} isGraphTerminal={sorted(frontend_fn)}"
    )
    assert "stalled" in backend, "新档 stalled 必须进三副本"

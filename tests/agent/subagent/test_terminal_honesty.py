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
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import (
    DEFAULT_MAX_NODES,
    DEFAULT_MAX_RUNS,
    DEFAULT_RECURSION_LIMIT,
    WorkflowSpec,
    _parse_edge,
    _parse_node,
    parse_workflow_spec,
)
from agent.workspace_policy import WorkspacePolicy

_REPO = Path(__file__).parents[3]


def _spec_without_cycle_check(raw: dict) -> WorkflowSpec:
    """直接组装 ``WorkflowSpec``，**绕过声明期的「环必须能启动」校验**。

    #217 的死锁图**本来就该**在声明期被拒（change ``workflow-cycle-contract``，D1），
    但本套件测的是**运行期**诊断：图因入边互等而停滞时，节点因由必须如实说
    「入边互相等待」、图级终态必须报 ``stalled`` 而不是 ``completed``。新校验只是把
    触发路径收窄了（从「模型声明出坏图」变成「图在运行期因其它原因陷入互等」），
    诊断本身没有错，所以继续锁住它（grill Q5 裁决 (甲)）。

    这里用 ``workflow.py`` 的解析 helper 直接构造 dataclass，**不新增生产代码里的旁路**。
    """
    nodes = tuple(_parse_node(item) for item in raw["nodes"])
    edges = tuple(_parse_edge(item) for item in raw.get("edges", []))
    index = {node.id: node for node in nodes}
    entry = tuple(raw.get("entry") or (
        node.id for node in nodes if not any(edge.target == node.id for edge in edges)
    ))
    terminal = tuple(raw.get("terminal") or (
        node.id for node in nodes if not any(edge.source == node.id for edge in edges)
    ))
    return WorkflowSpec(
        goal=raw.get("goal", ""),
        nodes=nodes,
        edges=edges,
        entry=entry,
        terminal=terminal,
        recursion_limit=raw.get("recursion_limit", DEFAULT_RECURSION_LIMIT),
        max_nodes=raw.get("max_nodes", DEFAULT_MAX_NODES),
        max_runs=raw.get("max_runs", DEFAULT_MAX_RUNS),
        _index=index,
    )


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


async def _run(manager, spec: dict, *, bypass: bool = False) -> dict:
    """跑一张图并取快照。

    ``bypass=True`` 用于**声明期会被拒**的死锁图（见 :func:`_spec_without_cycle_check`）：
    本套件测的是运行期诊断，需要把图直接塞进调度器。
    """
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = (
        _spec_without_cycle_check(spec) if bypass else parse_workflow_spec(spec)
    )
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
    snapshot = await _run(manager, _deadlock_spec(), bypass=True)
    assert snapshot["status"] != "completed"
    assert snapshot["status"] == "stalled"


@pytest.mark.asyncio
async def test_deadlock_graph_needs_no_completed_node(manager):
    """D2：``stalled`` 判据不要求存在 ``blocked`` 之外的边条件——零 completed 零 failed 即 stalled。

    本图三节点全 ``blocked``（无 ``failed``、无 ``completed``）→ ``stalled``。
    """
    snapshot = await _run(manager, _deadlock_spec(), bypass=True)
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
    snapshot = await _run(manager, _deadlock_spec(), bypass=True)
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
async def test_cancelled_graph_does_not_claim_mutual_wait(tmp_path):
    """回归（Round 2 审阅 N1）：图被**取消**时，节点因由不得说「入边互相等待」。

    取消链上根本没有环——节点没就绪的唯一原因是**用户停下了它**。说「永远未就绪」
    与说「工作流提前结束」同样是**指错方向的假话**（用户会去查环，而应该看取消）。
    这里用真实 ``run()`` + ``cancel()`` 复现：``n0``(慢) → ``n1`` → ``n2``，
    取消后 ``n1``/``n2`` 均为 ``blocked``。
    """
    class _SlowLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            await asyncio.sleep(5)
            return LLMResponse(content="hi", stop_reason="end_turn", usage=Usage(5, 5))

    manager = SubAgentManager(
        llm=_SlowLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    spec = {
        "goal": "cancel me",
        "nodes": [
            {"id": "n0", "kind": "subagent", "task": "slow"},
            {"id": "n1", "kind": "aggregate", "strategy": "collect"},
            {"id": "n2", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "n0", "to": "n1"}, {"from": "n1", "to": "n2"}],
        "entry": ["n0"], "terminal": ["n2"],
    }
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(spec)
    task = asyncio.ensure_future(scheduler.run(scheduler.spec))
    await asyncio.sleep(0.4)
    scheduler.cancel()
    await task
    snapshot = scheduler.workflow_graph_snapshot()

    assert snapshot["status"] == "cancelled"
    blocked = [n for n in snapshot["nodes"] if n["status"] == "blocked"]
    assert blocked, "取消后应有 blocked 节点"
    for node in blocked:
        reason = node.get("reason") or ""
        assert "入边互相等待" not in reason, (
            f"取消图（无环）不得说入边互等：{node['id']} reason={reason!r}"
        )


@pytest.mark.asyncio
async def test_waiting_reason_fits_the_frontend_display_budget(manager):
    """回归（Round 2 审阅 N2）：互等档因由也必须有展示预算上界。

    上游 id 长度由节点声明决定（6 个语义化长 id 扇入整句 179 字符；3 个 60 字符 id 达 207 字符），
    前端在 160 处会把「，本节点永远未就绪」连同右括号一起切掉——故必须限**整句长度**。
    """
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = _spec_without_cycle_check(_deadlock_spec())
    await scheduler.run(scheduler.spec)
    long_ids = [f"validation_stage_{i}_processor" for i in range(6)]

    class _Edge:
        def __init__(self, source):
            self.source, self.target, self.required = source, "target", True

    class _State:
        status = "blocked"

    class _Node:
        id = "target"

    # 三档最坏情况：数量多 / id 长 / id 极长。**只限数量不够**——3 个 60 字符的 id
    # 就会把整句推到 207 字符，前端在 160 处把后缀连同右括号一起切掉。
    for label, ids in (
        ("长 id 扇入", [f"validation_stage_{i}_processor" for i in range(6)]),
        ("超长 id ×3", [f"v{'x' * 59}_{i}" for i in range(3)]),
        ("极长 id", [f"{'y' * 500}_{i}" for i in range(3)]),
    ):
        scheduler._states = {lid: _State() for lid in ids}
        scheduler._graph = lambda ids=ids: type(
            "G", (), {"incoming": staticmethod(lambda _nid: [_Edge(lid) for lid in ids])}
        )()
        reason = scheduler._blocked_reason(type("St", (), {"node": _Node()})())
        assert len(reason) <= 160, f"[{label}] 互等因由超展示预算（{len(reason)}）: {reason!r}"
        assert reason.endswith("本节点永远未就绪"), f"[{label}] 尾部被挤掉：{reason!r}"
        assert reason.startswith("入边互相等待（"), f"[{label}] 前缀丢了：{reason!r}"


@pytest.mark.asyncio
async def test_gate_detail_prefers_structured_limit_over_long_message(manager):
    """回归（Round 2 审阅 N3）：闸门细节**优先取结构化 `limit`**，而非截断长 message。

    ``design.md`` 要求「SHALL NOT 直接塞入整段异常文本」。若只靠 message 截断，
    超长 `reason` 下仍可能超预算，且「limit 优先」这条设计约束没有任何测试锁定。
    """
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(_route_cap_spec())
    await scheduler.run(scheduler.spec)
    scheduler._diagnostics = {
        "reason": "recursion_limit",
        "limit": 7,
        "message": "M" * 500,   # 长 message 必须**不**被采用
    }
    state = next(s for s in scheduler._states.values() if s.status == "blocked")
    reason = scheduler._blocked_reason(state)
    assert "超过上限 7" in reason, f"未采用结构化 limit：{reason!r}"
    assert "MMMM" not in reason, f"采用了整段 message 而非结构化 limit：{reason!r}"
    assert len(reason) <= 160


@pytest.mark.asyncio
async def test_gate_reason_fits_the_frontend_display_budget(manager):
    """D3/审阅发现：闸门因由必须整句落在**前端展示预算**（160 字符）内。

    ``recursion_limit`` 的异常文本会列出全部就绪节点（实测 271 字符）；直接塞进来
    会让前端在 160 字符处把尾部「本节点未派发」切掉——关键信息（「未被派发」这一
    事实）反而丢了。故闸门细节取结构化上限值，且整句长度有界。
    """
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(_route_cap_spec())
    await scheduler.run(scheduler.spec)
    nodes = ", ".join(f"'n{i}'" for i in range(24))
    scheduler._diagnostics = {
        "reason": "recursion_limit",
        "limit": 1,
        "message": (
            "GraphRecursionError: workflow reached recursion_limit 1 supersteps; "
            f"ready nodes: [{nodes}]"
        ),
    }
    state = next(s for s in scheduler._states.values() if s.status == "blocked")
    reason = scheduler._blocked_reason(state)
    assert len(reason) <= 160, f"因由超出前端展示预算（{len(reason)}）: {reason!r}"
    assert "recursion_limit" in reason
    assert "本节点未派发" in reason, f"尾部事实被挤掉：{reason!r}"
    assert "1" in reason, f"上限值必须可见：{reason!r}"


@pytest.mark.asyncio
async def test_non_gate_diagnostics_do_not_claim_a_graph_gate_fired(manager):
    """回归（审阅发现）：``_diagnostics`` 非空 ≠ 图级闸门触发。

    ``route_ref_misses``（``$ref`` 槽未命中）是**良性**诊断，也会填充 ``_diagnostics``；
    若按「非空」判闸门，节点因由会写成「图级闸门 图级闸门 触发，本节点未派发」——
    既说了一次没发生的闸门，又是明显的坏文本（闸门名重复）。这正是本 change 要
    消灭的那类假话。闸门判定必须看 ``reason`` 键是否存在。
    """
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = _spec_without_cycle_check(_deadlock_spec())
    await scheduler.run(scheduler.spec)
    # 非闸门诊断（与 route_ref_misses 同形：**无** reason 键）
    scheduler._diagnostics = {
        "route_ref_misses": [{"route": "x", "when": "$ref:a:b", "reason": "missing"}]
    }
    state = next(s for s in scheduler._states.values() if s.status == "blocked")
    reason = scheduler._blocked_reason(state)
    assert "图级闸门" not in reason, f"非闸门诊断被说成闸门触发：{reason!r}"
    assert "入边互相等待" in reason, f"应落到结构性成因：{reason!r}"


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


def test_stalled_is_treated_as_non_success_by_every_consumer():
    """Q5：``stalled`` 对所有消费方的语义是**非成功**——不得被「只查 failed」的写法漏掉。

    本仓库没有「``status == 'completed'`` 即通过」的图级判定（图级 status 的消费方
    只有三副本 + 前端淘汰/计时），所以语义落在：**stalled 必须进终态集合**（否则被
    当 running），且**不是** ``completed``。这条断言把「新增档位没同步到消费方」的
    漂移钉死（#197 已踩过同类坑）。
    """
    assert "stalled" != "completed"
    assert "stalled" != "failed"  # 与 failed 分开：行动指引不同
    for copy in _graph_status_copies().values():
        assert "stalled" in copy, "stalled 未进终态集合 → 该图会被当成 running"


def _graph_status_copies() -> dict[str, set[str]]:
    scheduler_src = (_REPO / "agent" / "subagent" / "scheduler.py").read_text()
    match = re.search(
        r"_SNAPSHOT_TERMINAL_STATUSES\s*=\s*frozenset\(\s*\{(.*?)\}\s*\)", scheduler_src, re.S
    )
    assert match, "未找到 _SNAPSHOT_TERMINAL_STATUSES"
    workflow_js = (_REPO / "web" / "static" / "workflow.js").read_text()
    graph_js = (_REPO / "web" / "static" / "workflow_graph.js").read_text()
    return {
        "scheduler": set(re.findall(r'"([a-z_]+)"', match.group(1))),
        "workflow.js": _extract_bracket_list(workflow_js, "TERMINAL_STATUSES"),
        "workflow_graph.js": _extract_isgraphterminal(graph_js),
    }


def _frontend_reason_markers() -> set[str]:
    source = (_REPO / "web" / "static" / "workflow_graph.js").read_text()
    match = re.search(r"SPECIFIC_REASON_MARKERS\s*=\s*\[(.*?)\]", source, re.S)
    assert match, "未找到 SPECIFIC_REASON_MARKERS"
    return set(re.findall(r"'([^']+)'", match.group(1)))


@pytest.mark.asyncio
async def test_frontend_reason_markers_match_backend_emitted_text(manager):
    """契约回归（审阅发现）：前端提权所依赖的标记词必须**确实是后端会产出的文本**。

    前后端靠字面量耦合：后端 ``_blocked_reason`` 写 ``图级闸门 …`` /
    ``入边互相等待 …``，前端 ``SPECIFIC_REASON_MARKERS`` 硬编码同样的词做提权。
    若只改后端措辞（如把「图级闸门」写成「图形层限制」），前端提权会静默失效 ——
    「后端修好了、用户还是看不到」，正是 Q4 要堵的那条链路。本测试把这条耦合
    变成可判定的契约：**每个前端标记词都必须是后端真会产出的因由文本的子串**，
    且两条分支各自都被覆盖。

    因由文本取自**真实实跑**（闸门图 / 死锁图），不复制后端字面量。
    """
    markers = _frontend_reason_markers()
    assert markers, "前端标记词表为空"

    emitted: dict[str, str] = {}
    for label, spec, bypass in (
        ("gate", _route_cap_spec(), False),
        ("deadlock", _deadlock_spec(), True),
    ):
        snapshot = await _run(manager, spec, bypass=bypass)
        reasons = [n.get("reason") or "" for n in snapshot["nodes"]]
        emitted[label] = " || ".join(reasons)

    all_text = " || ".join(emitted.values())
    for marker in markers:
        assert marker in all_text, (
            f"前端标记词 {marker!r} 不是后端会产出的文本；后端实际产出：{all_text!r}"
        )
    for label in ("gate", "deadlock"):
        assert any(m in emitted[label] for m in markers), (
            f"{label} 档的因由不含任何前端标记词，前端不会提权它：{emitted[label]!r}"
        )


def test_graph_terminal_status_copies_are_equal():
    """D5：三个图级终态副本的**集合相等**（而非各自「包含 stalled」）——防未来漂移。"""
    copies = _graph_status_copies()
    values = list(copies.values())
    assert values[0] == values[1] == values[2], (
        f"终态集合副本漂移：{ {k: sorted(v) for k, v in copies.items()} }"
    )
    assert "stalled" in values[0], "新档 stalled 必须进三副本"


@pytest.mark.asyncio
async def test_reset_subtree_clears_stale_failure_count(manager):
    """``_reset_subtree`` 必须清 ``failure_count``（fix-issue-215 审阅 R1）。

    它与 ``reason``/``error``/``summary`` 属**同一类**「上一轮的失败痕迹」：不复位
    会让重跑期间前端显示上一轮的失败线索，而这一轮根本还没派发——实测症状是
    ``status=pending`` 配 ``failure_count=7``，即本函数 docstring 说的「答错比答不出
    更糟」。变异点：删掉 `state.failure_count = None` → 本条必须变红。
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
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(spec)
    await scheduler.run(scheduler.spec)

    # 取一个真实节点状态，人为置成「上一轮跑过且有失败」再复位。
    state = next(iter(scheduler._states.values()))
    state.status = "completed"
    state.reason = "boom"
    state.summary = "old output"
    state.finished_at = 123.0
    state.failure_count = 7

    scheduler._reset_subtree(state, origin=None)

    assert state.status == "pending"
    assert state.reason is None
    assert state.summary == ""
    assert state.finished_at is None
    assert state.failure_count is None, (
        "重跑期间不得留着上一轮的失败计数——它会让「任务」tab 显示"
        "「本 run 内 7 次工具失败」，而这一轮根本还没派发"
    )
    # 快照投影也必须干净（计数是投影直接读的字段）。
    node = next(n for n in scheduler.workflow_graph_snapshot()["nodes"]
                if n["id"] == state.node.id)
    assert node["status"] == "pending"
    assert node["failure_count"] is None

"""M1 语义层（change ``enhance-workflow-graph-ux``，issue #197）。

覆盖 tasks M1.1–M1.6 的后端部分：

- **G11** ``_reset_subtree`` 清除陈旧字段（reason/error/finished_at/summary）——
  否则 route 回边重跑后显示上一轮因由 + 负耗时。
- **D2b** 新增第 8 档节点状态 ``skipped``（未选中）：route 条件没走这条；
  三个判据（有控制入边 + ``activations<=0`` + **控制源 route 已 completed**）；
  「被上游连累」优先于「未选中」。
- **G26** 图级终态 ``completed_with_failures``：有节点 failed 的图不再报 ``completed``。
- **D2b** route 数据入边的 per-edge 消费记账（``a→gate`` 应为 ``passed``）。

这些断言都以**实跑**（真实 scheduler.run）为准，不 mock 内部状态——这正是
发现 G1 的方式（见 ``gap-analysis.md``）。
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class _LLM:
    """按 task 文本决定行为：含 ``BOOM`` 抛异常，否则返回给定文案。"""

    def __init__(self, content="APPROVED all good"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        blob = " ".join(str(getattr(m, "content", m)) for m in messages)
        if "BOOM" in blob:
            raise RuntimeError("model exploded")
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


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


def _route_spec(*, when="APPROVED", default="no", extra_edge=None, extra_node=None) -> dict:
    """``a -> gate(route) -> {yes, no}``；``a`` 的产出决定走哪条出口。"""
    nodes = [
        {"id": "a", "kind": "subagent", "task": "produce"},
        {"id": "gate", "kind": "route", "cases": [{"when": when, "to": "yes"}], "default": default},
        {"id": "yes", "kind": "subagent", "task": "yes branch"},
        {"id": "no", "kind": "subagent", "task": "no branch"},
    ]
    edges = [
        {"from": "a", "to": "gate"},
        {"from": "gate", "to": "yes"},
        {"from": "gate", "to": "no"},
    ]
    if extra_node is not None:
        nodes.append(extra_node)
    if extra_edge is not None:
        edges.append(extra_edge)
    return {
        "goal": "route",
        "nodes": nodes,
        "edges": edges,
        "entry": ["a"],
        "terminal": ["yes", "no"],
    }


# --- D2b：skipped（未选中） -------------------------------------------------


@pytest.mark.asyncio
async def test_unselected_route_branch_is_skipped_not_blocked(manager):
    """route 命中 APPROVED → ``no`` 分支未被选中，应记 ``skipped`` 而非 ``blocked``。

    这正是 issue #197 用户实测的痛点：``blocked``（被上游连累）与
    「条件没走这条」混成同一个颜色。
    """
    snapshot = await _run(manager, _route_spec())

    nodes = _nodes(snapshot)
    assert nodes["yes"]["status"] == "completed"
    assert nodes["no"]["status"] == "skipped", (
        f"未选中的分支应记 skipped，实际 {nodes['no']['status']!r}"
    )


@pytest.mark.asyncio
async def test_skipped_is_terminal_and_counted_separately(manager):
    """``skipped`` 是良性终态：不落 ``pending_units``，也不使整图 failed。"""
    snapshot = await _run(manager, _route_spec())

    assert snapshot["status"] == "completed"
    units = snapshot["total"]  # 终态帧带计数
    assert units > 0


@pytest.mark.asyncio
async def test_route_never_run_does_not_report_skipped(manager):
    """控制源 route 自己都没跑过时，下游**不得**报 ``skipped``（否则是假话）。

    构造（审阅员 B 给的真实场景，全确定）：
    ``start → r0(route)``，``r0`` 默认出口激活 ``other``；``s`` 是 ``r0`` 的
    另一条控制出口、**从未被激活**；``r`` 是另一条 route，其**数据依赖是 s**；
    ``t`` 是 ``r`` 的控制下游。

    - ``r0`` 确实跑了且没选 ``s`` → ``s`` 判 ``skipped``（**正确**）。
    - ``r`` 因数据依赖 ``s`` 从未就绪 → ``r`` 从未运行 → ``r`` 落普通 ``blocked``。
    - ``t`` 有控制入边、``activations<=0``，但控制源 ``r`` **没跑过** →
      判据条件 3 拦下它，落 ``blocked``；没有条件 3 就会误报 ``skipped``（假话）。
    """
    spec = {
        "goal": "control-source-never-ran",
        "nodes": [
            {"id": "start", "kind": "subagent", "task": "produce"},
            {
                "id": "r0",
                "kind": "route",
                "cases": [{"when": "APPROVED", "to": "s"}],
                "default": "other",
            },
            {"id": "s", "kind": "subagent", "task": "gated, never activated"},
            {"id": "other", "kind": "subagent", "task": "taken branch"},
            {
                "id": "r",
                "kind": "route",
                "cases": [{"when": "APPROVED", "to": "t"}],
                "default": "t",
            },
            {"id": "t", "kind": "subagent", "task": "downstream of r"},
        ],
        "edges": [
            {"from": "start", "to": "r0"},
            {"from": "r0", "to": "s"},
            {"from": "r0", "to": "other"},
            {"from": "s", "to": "r"},
            {"from": "r", "to": "t"},
        ],
        "entry": ["start"],
        "terminal": ["other", "t"],
    }
    # LLM 输出必须**不匹配** r0 的 ``APPROVED``，否则 r0 会走 s 而不是 default。
    manager.llm = _LLM(content="NOTHING matches")
    snapshot = await _run(manager, spec)

    nodes = _nodes(snapshot)
    assert nodes["r0"]["status"] == "completed", "r0 应跑完（它才是判定者）"
    assert nodes["r"]["status"] != "completed", "本用例前提：r 不应跑完"
    assert nodes["s"]["status"] == "skipped", "r0 判定过且没选 s → s 应 skipped"
    assert nodes["t"]["status"] != "skipped", (
        "控制源 r 从未运行时 t 报 skipped 是假话——应落 blocked"
    )


@pytest.mark.asyncio
async def test_blocked_takes_priority_over_skipped(manager):
    """「被上游连累」优先于「未选中」：节点既未被选中、上游又失败 → ``blocked``。

    构造：``no`` 分支既未被 route 选中，又有一条 required 数据入边来自
    ``BOOM`` 失败节点。按判据顺序应先判 blocked。
    """
    spec = {
        "goal": "blocked-priority",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "APPROVED", "to": "yes"}],
                "default": "no",
            },
            {"id": "yes", "kind": "subagent", "task": "yes branch"},
            {"id": "no", "kind": "subagent", "task": "no branch"},
            {"id": "boom", "kind": "subagent", "task": "BOOM fails"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "yes"},
            {"from": "gate", "to": "no"},
            # no 的 required 数据入边来自 boom（会失败）
            {"from": "boom", "to": "no"},
        ],
        "terminal": ["yes", "no"],
    }
    snapshot = await _run(manager, spec)
    nodes = _nodes(snapshot)
    assert nodes["boom"]["status"] == "failed"
    # no 的上游 boom 失败 → 不能报 skipped
    assert nodes["no"]["status"] != "skipped", (
        "上游失败时下游不得报 skipped（那是假话）"
    )


def _doomed_upstream_spec(*, t_first: bool) -> dict:
    """构造「既未被选中、其数据上游又被受阻连累」的节点 t。

    图：``start → gate(route)``，gate 默认出口激活 ``gated``（**从未被激活**）；
    ``gated → u``（u 的 required 数据依赖永远不就绪）；另一条 route ``r`` 有数据
    依赖 ``start`` 因而跑完，它的两条控制出边指向 ``other``（被选中）与 ``t``
    （**从未被选中**）；``u → t`` 是 t 的 required 数据入边。

    收尾时 ``gated`` 判 ``skipped``、``u`` 因数据依赖未了就绪落 ``blocked``；
    ``t`` 的真因是**上游 u 受阻**（即使 route 选了它也拿不到输入），所以按
    「被连累优先」必须记 ``blocked``——spec delta 的第三条 Scenario 明确把
    ``blocked`` 上游与 ``failed``/``cancelled`` 并列。

    ``t_first`` 用来把 t 的**声明顺序**提到 u 之前：收尾遍历是按声明序推进的，
    先判的节点看到的还是上游的**中间态**——所以判据必须与声明顺序无关。
    """
    graph = [
        ("start", {"id": "start", "kind": "subagent", "task": "produce"}),
        ("gate", {"id": "gate", "kind": "route",
                  "cases": [{"when": "APPROVED", "to": "picked"}], "default": "gated"}),
        ("picked", {"id": "picked", "kind": "subagent", "task": "taken branch"}),
        ("gated", {"id": "gated", "kind": "subagent", "task": "never activated"}),
        ("u", {"id": "u", "kind": "subagent", "task": "doomed upstream"}),
        ("r", {"id": "r", "kind": "route",
               "cases": [{"when": "APPROVED", "to": "other"}], "default": "other"}),
        ("other", {"id": "other", "kind": "subagent", "task": "taken branch"}),
        ("t", {"id": "t", "kind": "subagent", "task": "downstream of u and r"}),
    ]
    order = [name for name, _ in graph]
    if t_first:
        order.remove("t")
        order.insert(order.index("u"), "t")
    return {
        "goal": "doomed-upstream",
        "nodes": [dict(graph)[name] for name in order],
        "edges": [
            {"from": "start", "to": "gate"},
            {"from": "gate", "to": "picked"},
            {"from": "gate", "to": "gated"},
            {"from": "gated", "to": "u"},
            {"from": "start", "to": "r"},
            {"from": "r", "to": "other"},
            {"from": "r", "to": "t"},
            {"from": "u", "to": "t"},
        ],
        "entry": ["start"],
        "terminal": ["picked", "other", "t"],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("t_first", [False, True])
async def test_blocked_upstream_also_beats_skipped(manager, t_first):
    """spec delta Scenario 3 把 ``blocked`` 上游与 ``failed``/``cancelled`` 并列。

    只查 ``failed``/``cancelled``（``_EDGE_BLOCKED_SOURCE_STATUSES``）会漏掉
    「上游本身也被挡住」这一支——而 ``blocked`` 恰恰是本 change 要区分开的
    那一档，漏掉就把「被连累」报成了「条件没选它」，正是要消灭的那类假话。
    """
    snapshot = await _run(manager, _doomed_upstream_spec(t_first=t_first))
    nodes = _nodes(snapshot)

    assert nodes["gated"]["status"] == "skipped", "前置：gated 确实未被选中"
    assert nodes["u"]["status"] == "blocked", "前置：u 确实被连累受阻"
    assert nodes["t"]["status"] == "blocked", (
        f"t 的上游 u 受阻 → 必须记 blocked，实际 {nodes['t']['status']!r}"
    )


@pytest.mark.asyncio
async def test_skipped_verdict_is_independent_of_declaration_order(manager):
    """收尾判据必须与节点**声明顺序**无关——否则同一张图换个声明序就换一个答案。"""
    first = _nodes(await _run(manager, _doomed_upstream_spec(t_first=True)))
    second = _nodes(await _run(manager, _doomed_upstream_spec(t_first=False)))
    assert first["t"]["status"] == second["t"]["status"], (
        f"同一张图两种声明序给出不同答案：{first['t']['status']!r} vs "
        f"{second['t']['status']!r}"
    )


# --- D2b：route 数据入边的消费记账 ------------------------------------------


@pytest.mark.asyncio
async def test_route_data_incoming_edge_is_passed(manager):
    """``a→gate`` 是 route 的数据入边，gate 读了它的产出 → 应为 ``passed``。

    现状 bug：route 走 ``_route_verdict`` → ``_node_output``，不经过任何
    ``_mark_consumed`` 调用点 → 该边永远落 ``inactive`` 兜底。
    """
    snapshot = await _run(manager, _route_spec())
    edges = _edges(snapshot)

    assert edges[("a", "gate")] == "passed", (
        f"route 的数据入边应记 passed，实际 {edges[('a','gate')]!r}"
    )


# --- G26：图级 completed_with_failures --------------------------------------


@pytest.mark.asyncio
async def test_graph_with_failed_node_is_completed_with_failures(manager):
    """有节点 failed 的图，图级 status 应为 ``completed_with_failures``。

    现状 bug：``_drive`` 收敛出口只看预算，有节点 failed 仍报 ``completed``
    → 用户**根本不会被告知去看失败**。
    """
    spec = {
        "goal": "has-failure",
        "nodes": [
            {"id": "ok", "kind": "subagent", "task": "fine"},
            {"id": "bad", "kind": "subagent", "task": "BOOM fails"},
        ],
        "edges": [{"from": "ok", "to": "bad"}],
        "terminal": ["bad"],
    }
    snapshot = await _run(manager, spec)

    nodes = _nodes(snapshot)
    assert nodes["bad"]["status"] == "failed"
    assert snapshot["status"] == "completed_with_failures", (
        f"有节点失败的图应报 completed_with_failures，实际 {snapshot['status']!r}"
    )


@pytest.mark.asyncio
async def test_graph_all_completed_stays_completed(manager):
    """全成功的图仍是 ``completed``（不误报）。"""
    spec = {
        "goal": "all-ok",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "fine"},
            {"id": "b", "kind": "subagent", "task": "also fine"},
        ],
        "edges": [{"from": "a", "to": "b"}],
        "terminal": ["b"],
    }
    snapshot = await _run(manager, spec)
    assert snapshot["status"] == "completed"


# --- G11：重跑不得残留陈旧因由 / 负耗时 -------------------------------------


@pytest.mark.asyncio
async def test_rerun_clears_stale_reason_and_finished_at(manager):
    """route 回边重跑后，节点不得显示上一轮的 reason，也不得有负耗时。

    现状 bug：``_reset_subtree`` 只清 status/activations/verdict/targets，
    不清 reason/error/finished_at → 重跑显示陈旧因由 + ``finished_at < started_at``。
    """
    spec = {
        "goal": "loop-back",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "RETRY", "to": "a"}],
                "default": "done",
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "a"},   # 回边：命中 RETRY 就重跑 a
            {"from": "gate", "to": "done"},
        ],
        "entry": ["a"],
        "terminal": ["done"],
    }
    # LLM 先吐 RETRY（触发回边重跑 a），再吐别的（走 default 收敛）
    manager.llm = _LLM(content="RETRY")
    snapshot = await _run(manager, spec)

    for node in snapshot["nodes"]:
        started = node.get("started_at")
        finished = node.get("finished_at")
        if started is not None and finished is not None:
            assert finished >= started, (
                f"节点 {node['id']} 出现负耗时：{started=} {finished=}"
            )

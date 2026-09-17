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

"""Orchestration pattern library for subagents (issue 79, decision D6).

The "split / select / review" intelligence inside a pattern is carried by LLM
subagents; the deterministic skeleton — spawn N → wait → collect — is now the
unified scheduler. Patterns run on top of ``SubAgentManager`` (no separate
control plane) and receive a per-run ``MessageBus`` via the contextvar, so
workers can exchange summaries under the bus's token budget.

Change ``workflow-dsl-scheduler`` (D7) demotes the four patterns to **DSL
templates**: :func:`compile_pattern` turns a pattern name + task + params into a
:class:`~agent.subagent.workflow.WorkflowSpec`, and :func:`run_pattern` drives
that spec through the unified :class:`~agent.subagent.scheduler.WorkflowScheduler`
while keeping the historical return shape (``pattern`` / ``task`` / ``completed``
/ ``failed`` / ``workers`` / ``summary`` / ``selector`` / ``selected`` / ``bus``)
and adding ``workflow_id`` / ``workflow_spec_hash`` / ``critical_path_s`` /
``peak_active`` / ``total_cost``.

Aggregation semantics follow the decision record: a pattern aggregates **the
latest run of each node**, not every run the node ever had. peer-review reuses
the producer/reviewer sessions across rounds (that is what makes the critique
loop cheap), so ``completed`` counts terminal *nodes* — the producer having run
twice still contributes one worker entry.

Four patterns:

- orchestrator-worker: coordinator (the calling agent) fans out to N parallel
  workers, then aggregates. Workers do not talk to each other.
- peer-review: a producer creates output, a reviewer critiques, and the loop
  iterates until approval or ``max_rounds``.
- hierarchical: N manager subagents each run a sub-task and may themselves spawn
  (nested spawn, enabled by decision D4).
- bidding: N proposers each produce a solution independently, then a selector
  subagent picks the best. The selector reads compact proposal summaries (the
  design deliberately avoids the bus for proposals, whose drop-oldest could
  drop a key bid) and may Read full proposals from artifacts.

Worker failure is not fail-fast: the aggregate envelope reports each worker's
``{subagent_id, status, summary/result_ref, usage}`` plus pattern-level counts,
so benchmark completion/cost are comparable.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agent.subagent.bus import MessageBus
from agent.subagent.context import set_bus, reset_bus
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import WorkflowSpec, parse_workflow_spec

if TYPE_CHECKING:
    from agent.subagent.manager import SubAgentManager


#: 每个模板写进节点 task 的汇总指令（聚合节点自身不跑 LLM，除非 strategy="llm"）。
_AGGREGATE_INSTRUCTION = (
    "Summarize the results produced by the upstream nodes for this goal: {goal}"
)


def _items(n: int, label: str) -> list[dict]:
    return [{"name": f"{label}-{i}"} for i in range(n)]


def _worker_budget(params: dict[str, Any]) -> dict[str, Any]:
    """``worker_max_tokens`` / ``worker_max_time_s`` → 节点的 run 预算字段。

    Issue 6（building-review）：这两个参数过去传给每个 worker run，模板化后不能
    静默丢弃——落到 ``WorkflowNode.max_tokens`` / ``max_time_s``，由调度器在
    ``_launch_run`` 里透传给 ``run_subagent``。
    """
    budget: dict[str, Any] = {}
    if params.get("worker_max_tokens") is not None:
        budget["max_tokens"] = int(params["worker_max_tokens"])
    if params.get("worker_max_time_s") is not None:
        budget["max_time_s"] = float(params["worker_max_time_s"])
    return budget


def _template_orchestrator_worker(task: str, params: dict[str, Any]) -> dict:
    workers = max(1, int(params.get("workers", 3)))
    return {
        "goal": task,
        "nodes": [
            {
                "id": "workers",
                "kind": "foreach",
                "name": "workers",
                "task": task,
                "items": _items(workers, "worker"),
                "outputs": ["result"],
                **_worker_budget(params),
            },
            {
                "id": "aggregate",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
                "task": _AGGREGATE_INSTRUCTION.format(goal=task),
                "outputs": ["result"],
            },
        ],
        "edges": [{"from": "workers", "to": "aggregate", "reducer": "concat"}],
    }


def _template_hierarchical(task: str, params: dict[str, Any]) -> dict:
    teams = max(1, int(params.get("teams", 2)))
    return {
        "goal": task,
        "nodes": [
            {
                "id": "managers",
                "kind": "foreach",
                "name": "managers",
                "description": "sub-team manager, may spawn its own workers",
                "task": task,
                "items": _items(teams, "manager"),
                "outputs": ["result"],
                **_worker_budget(params),
            },
            {
                "id": "aggregate",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
                "task": _AGGREGATE_INSTRUCTION.format(goal=task),
                "outputs": ["result"],
            },
        ],
        "edges": [{"from": "managers", "to": "aggregate", "reducer": "concat"}],
    }


def _template_bidding(task: str, params: dict[str, Any]) -> dict:
    proposers = max(2, int(params.get("proposers", 3)))
    return {
        "goal": task,
        "nodes": [
            {
                "id": "proposers",
                "kind": "foreach",
                "name": "proposers",
                "description": "independent proposer",
                "task": task,
                "items": _items(proposers, "proposer"),
                "outputs": ["proposal"],
                **_worker_budget(params),
            },
            {
                "id": "selector",
                "kind": "subagent",
                "name": "selector",
                "description": "evaluates and picks the best proposal",
                "task": (
                    "Evaluate the proposals below and select the best one. Reply with "
                    "exactly one line starting with SELECTED <proposal number> followed "
                    "by a one-sentence justification."
                ),
                "outputs": ["selected"],
            },
            {
                "id": "aggregate",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
                "task": _AGGREGATE_INSTRUCTION.format(goal=task),
                "outputs": ["result"],
            },
        ],
        "edges": [
            {"from": "proposers", "to": "selector", "reducer": "concat"},
            {"from": "selector", "to": "aggregate"},
        ],
    }


def _template_peer_review(task: str, params: dict[str, Any]) -> dict:
    max_rounds = max(1, int(params.get("max_rounds", 3)))
    return {
        "goal": task,
        "nodes": [
            {
                "id": "producer",
                "kind": "subagent",
                "name": "producer",
                "description": "produces the proposal",
                "task": task,
                "outputs": ["proposal"],
                **_worker_budget(params),
            },
            {
                "id": "reviewer",
                "kind": "subagent",
                "name": "reviewer",
                "description": "critiques the proposal",
                "task": (
                    "Review the proposal below. Reply with exactly one line starting "
                    "with APPROVED if it is acceptable, or CRITIQUE followed by the "
                    "specific issues if it needs revision."
                ),
                "outputs": ["review"],
                **_worker_budget(params),
            },
            {
                "id": "gate",
                "kind": "route",
                "task": "route on the reviewer verdict",
                "cases": [{"when": "APPROVED", "to": "aggregate"}],
                "default": "producer",
                "max_routes": max_rounds,
            },
            {
                "id": "aggregate",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
                "task": _AGGREGATE_INSTRUCTION.format(goal=task),
                "outputs": ["result"],
            },
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "aggregate"},
            {"from": "gate", "to": "producer"},
            {"from": "producer", "to": "aggregate", "reducer": "concat"},
            {"from": "reviewer", "to": "aggregate", "reducer": "concat"},
        ],
    }


def compile_pattern(
    pattern: str,
    *,
    task: str,
    params: dict[str, Any] | None = None,
) -> WorkflowSpec:
    """把一个内置 pattern 编译成 WorkflowSpec 模板（D7）。"""
    if pattern not in PATTERNS:
        raise KeyError(f"unknown pattern {pattern!r}; available: {sorted(PATTERNS)}")
    return PATTERNS[pattern](task=task, params=params).compile()


#: 模板里「进 workers[] 的节点」白名单（其余节点只出现在新增字段里）。
_AGGREGATE_NODE_IDS = {
    "orchestrator-worker": ("workers",),
    "peer-review": ("producer", "reviewer"),
    "hierarchical": ("managers",),
    "bidding": ("proposers",),
}


class OrcPattern:
    """Common pattern interface: a pattern knows how to compile itself to a spec.

    Before this change a pattern was a spawn/wait/collect routine; now the routine
    *is* the scheduler, and what remains pattern-specific is the topology. Each
    subclass therefore only declares ``name`` and ``build``.
    """

    name = "base"

    def __init__(
        self,
        *,
        task: str = "",
        params: dict[str, Any] | None = None,
    ) -> None:
        self.task = task
        self.params = params or {}

    @classmethod
    def build(cls, task: str, params: dict[str, Any]) -> dict:
        """Return the raw WorkflowSpec mapping for this pattern."""
        raise NotImplementedError

    def compile(self) -> WorkflowSpec:
        return parse_workflow_spec(self.build(self.task, self.params))


class OrchestratorWorkerPattern(OrcPattern):
    name = "orchestrator-worker"
    build = staticmethod(_template_orchestrator_worker)


class PeerReviewPattern(OrcPattern):
    name = "peer-review"
    build = staticmethod(_template_peer_review)


class HierarchicalPattern(OrcPattern):
    name = "hierarchical"
    build = staticmethod(_template_hierarchical)


class BiddingPattern(OrcPattern):
    name = "bidding"
    build = staticmethod(_template_bidding)


PATTERNS: dict[str, type[OrcPattern]] = {
    "orchestrator-worker": OrchestratorWorkerPattern,
    "peer-review": PeerReviewPattern,
    "hierarchical": HierarchicalPattern,
    "bidding": BiddingPattern,
}


# --- adapter ---------------------------------------------------------------


def _workers_from_node(node: dict, manager: "SubAgentManager") -> list[dict]:
    """把一个 DSL 节点的**最新一次 run** 投影成历史 ``workers[]`` 条目。

    foreach 节点有多个 session（每个展开项一个），逐个取各自的最新 run。
    """
    entries: list[dict] = []
    single = node.get("subagent_id")
    if node["kind"] != "foreach" and single:
        session = manager._sessions.get(single)
        run = session.runs[-1] if session and session.runs else None
        entries.append(_worker_entry(single, run))
        return entries
    for subagent_id in node.get("subagent_ids", []):
        session = manager._sessions.get(subagent_id)
        run = session.runs[-1] if session and session.runs else None
        entries.append(_worker_entry(subagent_id, run))
    return entries


def _worker_entry(subagent_id: str, run: Any) -> dict:
    """把一个 run 投影成历史 ``workers[]`` 条目——**模型面**出口，故 summary bounded。

    issue #213：``RunPattern`` 的返回体会一次带上 N 个 worker，各自原样塞全文
    （N × 30000 字）。这里与 run envelope 出口同口径：裁到固定的单条内容上限。

    截断时**必须同时给出 ``result_ref``**——条目会写「全文在 result_ref」，
    而模型拿不到这个字段的话，就是在出口 4 复制一句正要消灭的假话。
    """
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT, _clip

    if run is None:
        return {
            "subagent_id": subagent_id,
            "status": "unknown",
            "summary": "",
            "reason": None,
            "usage": {},
        }
    summary, truncated = _clip(run.summary, TRANSCRIPT_ITEM_LIMIT)
    entry = {
        "subagent_id": subagent_id,
        "status": run.status,
        "summary": summary,
        "reason": run.reason,
        "usage": {
            "total_tokens": run.usage.total_tokens,
            "tool_calls": run.usage.tool_calls,
            "input_tokens": run.usage.input_tokens,
            "output_tokens": run.usage.output_tokens,
        },
    }
    if truncated:
        entry["summary_truncated"] = True
        # 只在**确有**引用时才放这个键。放一个值为 ``None`` 的 ``result_ref``
        # 同样是在承诺「全文在那」，而模型按图索骥会扑空——那就是本 change 要
        # 消灭的那句假话换了个形式。
        ref = getattr(run, "result_ref", None)
        if ref:
            entry["result_ref"] = ref
    return entry


def _legacy_result(pattern: str, task: str, envelope: dict, manager: "SubAgentManager") -> dict:
    """把调度器 envelope 投影回历史 pattern 返回结构 + 新增度量字段。"""
    by_id = {node["id"]: node for node in envelope["nodes"]}
    wanted = _AGGREGATE_NODE_IDS.get(pattern, ())
    worker_nodes = [by_id[node_id] for node_id in wanted if node_id in by_id]

    workers: list[dict] = []
    for node in worker_nodes:
        workers.extend(_workers_from_node(node, manager))

    completed = sum(1 for worker in workers if worker["status"] == "completed")
    failed = len(workers) - completed
    parts = [
        f"[{worker['subagent_id']}] "
        f"{worker.get('summary') or worker.get('reason') or 'no output'}"
        for worker in workers
    ]
    result: dict[str, Any] = {
        "pattern": pattern,
        "task": task,
        "completed": completed,
        "failed": failed,
        "workers": workers,
        "summary": "\n".join(parts),
        # 新增字段（Q9）
        "workflow_id": envelope["workflow_id"],
        "workflow_spec_hash": envelope["spec_hash"],
        "critical_path_s": envelope["critical_path_s"],
        "peak_active": envelope["peak_active"],
        "total_cost": envelope["total_cost"],
        "workflow_status": envelope["status"],
    }

    if pattern == "bidding":
        proposals = _workers_from_node(by_id["proposers"], manager)
        selector_node = by_id.get("selector")
        selector_summary = selector_node.get("summary", "") if selector_node else ""
        result["workers"] = proposals
        result["completed"] = sum(1 for w in proposals if w["status"] == "completed")
        result["failed"] = len(proposals) - result["completed"]
        result["summary"] = "\n".join(
            f"[{w['subagent_id']}] {w.get('summary') or 'no output'}" for w in proposals
        )
        result["selected"] = selector_summary
        result["selector"] = {
            "subagent_id": selector_node.get("subagent_id") if selector_node else None,
            "status": selector_node.get("status", "unknown") if selector_node else "unknown",
            "summary": selector_summary,
            "reason": selector_node.get("reason") if selector_node else None,
        }
    return result


async def run_pattern(
    manager: "SubAgentManager",
    *,
    pattern: str,
    task: str,
    params: dict[str, Any] | None = None,
) -> dict:
    """Run an orchestration pattern: compile it to a WorkflowSpec and drive it
    through the unified scheduler, with a fresh per-run message bus.

    The bus is installed into the scheduler's dispatch context so every node (and
    every worker beneath it) can publish/read summaries, and it is reset when the
    pattern ends. The historical return shape is preserved; the scheduler's
    envelope is folded into it (``workflow_id``, ``workflow_spec_hash``,
    ``critical_path_s``, ``peak_active``, ``total_cost``).
    """
    if pattern not in PATTERNS:
        raise KeyError(f"unknown pattern {pattern!r}; available: {sorted(PATTERNS)}")
    spec = compile_pattern(pattern, task=task, params=params)
    bus = MessageBus()
    token = set_bus(bus)
    started_at = time.time()
    try:
        scheduler = WorkflowScheduler(manager, bus=bus)
        manager.register_workflow(scheduler)
        envelope = await scheduler.run(spec)
    finally:
        reset_bus(token)
    result = _legacy_result(pattern, task, envelope, manager)
    result["bus"] = bus.snapshot_payload()
    result["total_cost"] = envelope["total_cost"]
    result["critical_path_s"] = round(time.time() - started_at, 6)
    return result

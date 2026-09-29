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
from agent.subagent.workflow import (
    DEFAULT_RECURSION_LIMIT,
    WorkflowNode,
    WorkflowSpec,
    WorkflowValidationError,
    parse_workflow_spec,
)

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


#: 每个模板接受的 ``params`` 键 → 该键的**类别**。类别决定校验口径：
#:
#: - ``fanout``：计数键，展开成 foreach 项（``_items(n, ...)``）。上界 = 模板 foreach
#:   节点的 ``max_items``（模板从不覆写，恒为默认 20）。超界拒绝——理由两层：既消除
#:   执行期静默截断（``items[:max_items]`` 只跑 20 个），也**阻止编译期内存放大**
#:   （实测 ``workers=100000`` 会在编译期真的造出 10 万个 item 对象）。
#: - ``rounds``：计数键，落到 route 的 ``max_routes``。**不做静态上界**（与图级
#:   ``recursion_limit`` 的换算比依赖模板拓扑——peer-review 一轮约 1.9 superstep）；
#:   仅当明显荒谬（> ``recursion_limit``，任何拓扑下都不可能跑满）时拒绝，其余交给
#:   运行期截断诊断如实报告。
#: - ``budget``：数值键，透传给节点 run 预算（``_worker_budget``）。
#:
#: 键名按模板**封闭**（不是全局并集）：跨模板键（如 ``peer-review`` + ``workers``）
#: 今天被静默忽略，必须结构化拒绝——那正是「以为 params 生效了」的假象。
_TEMPLATE_PARAMS: dict[str, dict[str, str]] = {
    "orchestrator-worker": {
        "workers": "fanout",
        "worker_max_tokens": "budget",
        "worker_max_time_s": "budget",
    },
    "hierarchical": {
        "teams": "fanout",
        "worker_max_tokens": "budget",
        "worker_max_time_s": "budget",
    },
    "bidding": {
        "proposers": "fanout",
        "worker_max_tokens": "budget",
        "worker_max_time_s": "budget",
    },
    "peer-review": {
        "max_rounds": "rounds",
        "worker_max_tokens": "budget",
        "worker_max_time_s": "budget",
    },
}

#: fanout 计数键的上界来源：模板 foreach 节点的 ``max_items`` 默认值（模板从不覆写）。
_FANOUT_CAP = WorkflowNode.__dataclass_fields__["max_items"].default


def _coerce_count(value: Any, key: str, pattern: str) -> int:
    """计数/轮数键：必须是整数（拒绝布尔、浮点、字符串、``None``、容器）。

    布尔在显式排除之列——``isinstance(True, int)`` 为真，不排除会让 ``workers=True``
    静默变成 1。**0 与负数不在拒绝之列**：它们是既有 clamp 语义（``max(1, ...)`` /
    ``max(2, ...)`` 落到下界），不是错误。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowValidationError(
            f"template {pattern!r} param {key!r} must be an integer, got {value!r} "
            f"({type(value).__name__})"
        )
    return value


def _coerce_budget(value: Any, key: str, pattern: str) -> None:
    """预算键：``None`` = 未设置（既有语义）；否则必须是数值（拒绝布尔/字符串/容器）。"""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowValidationError(
            f"template {pattern!r} param {key!r} must be a number or null, got {value!r} "
            f"({type(value).__name__})"
        )


def validate_template_params(
    pattern: str, params: dict[str, Any] | None
) -> dict[str, Any] | None:
    """按模板校验 ``params``（键名 + 值类型 + fanout 上界 + rounds 荒谬界）。

    **必须早于**模板 ``build()`` 调用——``workers=100000`` 的编译期放大正是要在造出
    item 对象之前拦下。校验失败一律抛 :class:`WorkflowValidationError`（``ValueError``
    子类），两个调用方（统一入口 / 资产路径）各自翻译成结构化拒绝。返回 ``params``
    原样（便于链式调用），不做任何 clamp/改写。
    """
    if params is None:
        return None
    if not isinstance(params, dict):
        raise WorkflowValidationError(
            f"template {pattern!r} params must be an object, got {type(params).__name__}"
        )
    accepted = _TEMPLATE_PARAMS[pattern]
    for key, value in params.items():
        kind = accepted.get(key)
        if kind is None:
            raise WorkflowValidationError(
                f"template {pattern!r} does not accept param {key!r}; "
                f"available: {sorted(accepted)}"
            )
        if kind == "budget":
            _coerce_budget(value, key, pattern)
            continue
        count = _coerce_count(value, key, pattern)
        if kind == "fanout" and count > _FANOUT_CAP:
            raise WorkflowValidationError(
                f"template {pattern!r} param {key!r}={count} exceeds max_items "
                f"({_FANOUT_CAP}) — the bound comes from the foreach node's max_items "
                f"(silent truncation + compile-time memory growth)"
            )
        if kind == "rounds" and count > DEFAULT_RECURSION_LIMIT:
            raise WorkflowValidationError(
                f"template {pattern!r} param {key!r}={count} exceeds recursion_limit "
                f"({DEFAULT_RECURSION_LIMIT}) — declared rounds cannot even be reached "
                f"in supersteps; lower it or rely on the truncation diagnostics"
            )
    return params


def compile_pattern(
    pattern: str,
    *,
    task: str,
    params: dict[str, Any] | None = None,
) -> WorkflowSpec:
    """把一个内置 pattern 编译成 WorkflowSpec 模板（D7）。

    这是模板编译的**唯一 choke point**（统一入口与资产路径共用）。``params`` 在此
    按模板校验（键名 / 值类型 / fanout 上界 / rounds 荒谬界），**先于**模板 ``build()``
    ——避免 ``workers=100000`` 的编译期 item 放大。
    """
    if pattern not in PATTERNS:
        raise KeyError(f"unknown pattern {pattern!r}; available: {sorted(PATTERNS)}")
    validate_template_params(pattern, params)
    return PATTERNS[pattern](task=task, params=params).compile()


def compile_recipe(
    pattern: str,
    *,
    task: str,
    params: dict[str, Any] | None = None,
) -> WorkflowSpec:
    """编译一个「配方」——内置模板名 + task + params（变化 ``workflow-builtin-templates``，D4）。

    统一入口的 ``template`` 路径与 #245 的 pattern 资产路径**共用这一条**编译路径：
    内置模板 = 随代码走的配方，用户资产 = 随 workspace 走的配方，两者在此归一。

    与 :func:`compile_pattern` 的唯一差别是错误类型：未知模板名与非法 params 一律抛
    :class:`~agent.subagent.workflow.WorkflowValidationError`（``ValueError`` 子类），
    两个调用方各自翻译成结构化拒绝（``invalid_input`` / ``invalid_asset``）；避免
    ``run_pattern`` 时代的 ``KeyError`` 分叉让资产路径漏兜。

    ``template`` 是**服务端配方的引用**（封闭枚举），SHALL NOT 被当作模型可写的模板串
    ——没有占位符求值面（见 design D3）。
    """
    try:
        return compile_pattern(pattern, task=task, params=params)
    except KeyError as exc:
        raise WorkflowValidationError(str(exc)) from exc


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
        # Pattern provenance for the asset layer (change
        # ``workflow-asset-persistence``, D1): the compiled spec has already lost
        # the recipe, so record it before the run starts. Pure additive field —
        # it never reaches ``_envelope``/``_legacy_result``.
        scheduler.asset_source = {
            "kind": "pattern",
            "pattern": pattern,
            "params": dict(params or {}),
            "task": task,
        }
        manager.register_workflow(scheduler)
        envelope = await scheduler.run(spec)
    finally:
        reset_bus(token)
    result = _legacy_result(pattern, task, envelope, manager)
    result["bus"] = bus.snapshot_payload()
    result["total_cost"] = envelope["total_cost"]
    result["critical_path_s"] = round(time.time() - started_at, 6)
    return result

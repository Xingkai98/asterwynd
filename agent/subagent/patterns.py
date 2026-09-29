"""Orchestration template library for subagents (issue 79, decision D6).

The "split / select / review" intelligence inside a template is carried by LLM
subagents; the deterministic skeleton — spawn N → wait → collect — is the
unified scheduler. Templates compile to a WorkflowSpec and run on top of
``SubAgentManager`` (no separate control plane).

Change ``workflow-dsl-scheduler`` (D7) demotes the four patterns to **DSL
templates**: :func:`compile_pattern` turns a template name + task + params into a
:class:`~agent.subagent.workflow.WorkflowSpec`.

Change ``workflow-builtin-templates`` (this change) removes the ``RunPattern``
tool and its ``run_pattern`` adapter: the four templates are now reached through
the unified Workflow entry (``RunWorkflow``'s ``template`` input), which runs the
compiled spec through the unified scheduler and returns the same bounded
``parent_envelope()`` as the hand-written-spec path. The recipe — a template name
plus params — is shared with the #245 asset layer via :func:`compile_recipe`.

Aggregation semantics: a template aggregates **the latest run of each node**, not
every run the node ever had. peer-review reuses the producer/reviewer sessions
across rounds (that is what makes the critique loop cheap).

Four templates:

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

Worker failure is not fail-fast: the scheduler's envelope reports each node's
status plus run-level counts, so benchmark completion/cost stay comparable.
"""
from __future__ import annotations

from typing import Any

from agent.subagent.workflow import (
    DEFAULT_RECURSION_LIMIT,
    WorkflowNode,
    WorkflowSpec,
    WorkflowValidationError,
    parse_workflow_spec,
)


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
#:   ``recursion_limit`` 的换算比依赖模板拓扑——peer-review 一轮约 **3 superstep**
#:   （producer + reviewer + gate），实测 ``superstep = 3N + 2``；「≈1.9」是
#:   **run/轮**口径，量纲不同勿混用）；
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
    if pattern not in PATTERNS:
        raise WorkflowValidationError(
            f"unknown template {pattern!r}; available: {sorted(PATTERNS)}"
        )
    return compile_pattern(pattern, task=task, params=params)


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

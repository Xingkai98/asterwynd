"""Workflow DSL：声明式协作拓扑的数据结构与 schema 校验（change ``workflow-dsl-scheduler``）。

设计口径来自 ``openspec/changes/workflow-dsl-scheduler/design.md`` D2/D5/D6 与
grill 决策记录（``reviews/grill-design.md``）：

- 4 种节点：``subagent`` / ``aggregate`` / ``route`` / ``foreach``；
- 2 种汇合语义：``all_required`` / ``best_effort``（``best_effort`` 必须显式给
  ``deadline_s``，见 Q3）；
- 节点用 ``outputs`` 声明写哪些结果槽，多入边写同槽必须声明 reducer（受限枚举，
  不执行模型生成代码，Q4）；
- 环上必须有 ``route`` 节点——它是唯一能提供条件出口 + ``max_routes`` 上限的
  节点，没有 route 的环是不可终止的死循环；
- 三闸默认值（Q5）：``recursion_limit=25`` / ``max_nodes=200`` / ``max_runs=300``。

本模块只做「受限可校验」的声明面：不执行任何模型生成代码，不 import 运行时
（manager/scheduler），只做结构与语义校验。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

SCHEMA_VERSION = "workflow.v1"

NODE_KINDS = ("subagent", "aggregate", "route", "foreach")
JOIN_SEMANTICS = ("all_required", "best_effort")
AGGREGATE_STRATEGIES = ("llm", "collect")
# 受限 reducer 枚举：不执行模型生成代码（design.md D5 / Risks）。
REDUCERS = ("concat", "merge_dict", "first_non_empty", "last")
CHANNELS = ("result_ref", "summary", "artifact", "bus")

# 三闸默认值（grill Q5）：图级步数 / 节点数（含 foreach 展开）/ run 总数。
DEFAULT_RECURSION_LIMIT = 25
DEFAULT_MAX_NODES = 200
DEFAULT_MAX_RUNS = 300

_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "goal",
        "nodes",
        "edges",
        "entry",
        "terminal",
        "recursion_limit",
        "max_nodes",
        "max_runs",
    }
)
_NODE_FIELDS = frozenset(
    {
        "id",
        "kind",
        "task",
        "name",
        "description",
        "mode",
        "outputs",
        "join",
        "strategy",
        "deadline_s",
        "cases",
        "default",
        "max_routes",
        "items",
        "source",
        "source_field",
        "max_items",
        # 每个 subagent/foreach 节点的 run 预算（pattern 模板把 worker_max_* 落在这里）
        "max_tokens",
        "max_time_s",
    }
)
_EDGE_FIELDS = frozenset({"from", "to", "channel", "required", "reducer"})


class WorkflowValidationError(ValueError):
    """WorkflowSpec 校验失败（schema 层拒绝，不进入调度）。"""


#: 动态 route 条件源的引用前缀（change ``workflow-budget-attribution``，D4/Q1）：
#: ``when: "$ref:<node_id>:<slot>"`` —— 读取已声明节点的结果槽，取首个非空行作
#: **期望标签**，再走 ``matches_route`` 行首匹配。受限可校验，不执行模型生成代码。
ROUTE_REF_PREFIX = "$ref:"


def is_route_ref(when: str) -> bool:
    """``when`` 是否是 ``$ref:`` 引用（语法前缀判定，不校验内容）。"""
    return isinstance(when, str) and when.startswith(ROUTE_REF_PREFIX)


def parse_route_ref(when: str) -> tuple[str, str] | None:
    """解析 ``$ref:<node_id>:<slot>`` 成 ``(node_id, slot)``。

    格式非法（段数不对、段为空）返回 ``None``——调用方区分「不是 ref」（字面标签）
    与「是 ref 但格式错」（校验期拒绝）。
    """
    if not is_route_ref(when):
        return None
    parts = when[len(ROUTE_REF_PREFIX) :].split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def declared_slots(node: WorkflowNode) -> frozenset[str]:
    """一个节点对外的**已声明槽**集合（``outputs`` + 隐式 ``result`` 槽，Q3）。

    隐式 ``result`` 始终算已声明：``outputs`` 的缺省值就是 ``("result",)``，模型显式
    写 ``outputs: ["verdict"]`` 时 ``result`` 仍是 DSL 的通用兜底槽名。
    """
    return frozenset(set(node.outputs) | {"result"})


@dataclass(frozen=True)
class RouteCase:
    """``route`` 节点的一条分支：结构化标签 ``when`` 命中则走 ``to``。"""

    when: str
    to: str

    def to_dict(self) -> dict:
        return {"when": self.when, "to": self.to}


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    kind: str
    task: str = ""
    name: str | None = None
    description: str = ""
    mode: str | None = None
    # 声明的写槽：并行分支写同一槽必须声明 reducer（D5）。
    outputs: tuple[str, ...] = ("result",)
    # aggregate
    join: str = "all_required"
    strategy: str = "llm"
    deadline_s: float | None = None
    # route
    cases: tuple[RouteCase, ...] = ()
    default: str | None = None
    max_routes: int = 1
    # foreach
    items: tuple[Any, ...] | None = None
    source: str | None = None
    source_field: str | None = None
    max_items: int = 20
    # 节点级 run 预算：透传给 ``SubAgentManager.run_subagent``（pattern 模板的
    # ``worker_max_tokens`` / ``worker_max_time_s`` 落到这里）。
    max_tokens: int | None = None
    max_time_s: float | None = None

    def to_dict(self) -> dict:
        data: dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.task:
            data["task"] = self.task
        if self.name is not None:
            data["name"] = self.name
        if self.description:
            data["description"] = self.description
        if self.mode is not None:
            data["mode"] = self.mode
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        if self.max_time_s is not None:
            data["max_time_s"] = self.max_time_s
        data["outputs"] = list(self.outputs)
        if self.kind == "aggregate":
            data["join"] = self.join
            data["strategy"] = self.strategy
            if self.deadline_s is not None:
                data["deadline_s"] = self.deadline_s
        elif self.kind == "route":
            data["cases"] = [case.to_dict() for case in self.cases]
            if self.default is not None:
                data["default"] = self.default
            data["max_routes"] = self.max_routes
        elif self.kind == "foreach":
            if self.items is not None:
                data["items"] = list(self.items)
            if self.source is not None:
                data["source"] = self.source
            if self.source_field is not None:
                data["source_field"] = self.source_field
            data["max_items"] = self.max_items
        return data


@dataclass(frozen=True)
class WorkflowEdge:
    source: str
    target: str
    channel: str = "summary"
    required: bool = True
    reducer: str | None = None

    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "from": self.source,
            "to": self.target,
            "channel": self.channel,
        }
        if not self.required:
            data["required"] = False
        if self.reducer is not None:
            data["reducer"] = self.reducer
        return data


@dataclass(frozen=True)
class WorkflowSpec:
    goal: str
    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    entry: tuple[str, ...] = ()
    terminal: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    recursion_limit: int = DEFAULT_RECURSION_LIMIT
    max_nodes: int = DEFAULT_MAX_NODES
    max_runs: int = DEFAULT_MAX_RUNS
    _index: Mapping[str, WorkflowNode] = field(default_factory=dict, repr=False, compare=False)

    # -- lookups ------------------------------------------------------------

    def node(self, node_id: str) -> WorkflowNode:
        found = self._index.get(node_id)
        if found is None:
            raise KeyError(f"unknown node id: {node_id}")
        return found

    def has_node(self, node_id: str) -> bool:
        return node_id in self._index

    def incoming(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        return tuple(edge for edge in self.edges if edge.target == node_id)

    def outgoing(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        return tuple(edge for edge in self.edges if edge.source == node_id)

    def is_control_edge(self, edge: WorkflowEdge) -> bool:
        """``route`` 节点的出边是控制边（激活下游），不传数据、不参与 reducer。"""
        return self._index[edge.source].kind == "route"

    def data_incoming(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        """数据入边（排除 route 控制边）——门控与 reducer 只看这些边。"""
        return tuple(
            edge
            for edge in self.edges
            if edge.target == node_id and not self.is_control_edge(edge)
        )

    def data_outgoing(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        return tuple(
            edge
            for edge in self.edges
            if edge.source == node_id and not self.is_control_edge(edge)
        )

    def edge_between(self, source: str, target: str) -> WorkflowEdge | None:
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return edge
        return None

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "goal": self.goal,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "entry": list(self.entry),
            "terminal": list(self.terminal),
        }
        if self.recursion_limit != DEFAULT_RECURSION_LIMIT:
            data["recursion_limit"] = self.recursion_limit
        if self.max_nodes != DEFAULT_MAX_NODES:
            data["max_nodes"] = self.max_nodes
        if self.max_runs != DEFAULT_MAX_RUNS:
            data["max_runs"] = self.max_runs
        return data

    @property
    def spec_hash(self) -> str:
        """WorkflowSpec 内容哈希（与 OpenSpec artifact 的 ``spec_hash`` 不同名同义）。"""
        canonical = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def describe_brief(self) -> str:
        """Bounded 文本描述（喂工具返回，避免整图打爆父 agent 上下文）。"""
        lines = [f"goal: {self.goal}", f"nodes: {len(self.nodes)}"]
        for node in self.nodes:
            lines.append(f"- {node.id} [{node.kind}]")
        return "\n".join(lines)


# --- 解析与校验 -------------------------------------------------------------


def parse_workflow_spec(
    raw: Any,
    *,
    default_recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    default_max_nodes: int = DEFAULT_MAX_NODES,
    default_max_runs: int = DEFAULT_MAX_RUNS,
) -> WorkflowSpec:
    """把模型给的 dict 解析成 ``WorkflowSpec``，任何 schema 问题直接 reject。

    校验面（tasks 1.2）：非法环（不含 route 的环）、未知节点、重复 id、
    超 max_nodes、多入边写同槽无 reducer、reducer 非法、best_effort 缺
    ``deadline_s``、kind-specific 字段缺失/越界。
    """
    if not isinstance(raw, Mapping):
        raise WorkflowValidationError("workflow spec must be a JSON object")
    data = dict(raw)
    unknown = set(data) - _SPEC_FIELDS
    if unknown:
        raise WorkflowValidationError(
            f"unknown spec field(s): {sorted(unknown)}; allowed: {sorted(_SPEC_FIELDS)}"
        )

    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        raise WorkflowValidationError(
            f"unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION!r}"
        )

    goal = data.get("goal", "")
    if not isinstance(goal, str):
        raise WorkflowValidationError("spec.goal must be a string")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowValidationError("spec.nodes must be a non-empty list")
    nodes = tuple(_parse_node(item) for item in raw_nodes)

    node_ids = [node.id for node in nodes]
    seen: set[str] = set()
    duplicated: list[str] = []
    for node_id in node_ids:
        if node_id in seen:
            duplicated.append(node_id)
        seen.add(node_id)
    if duplicated:
        raise WorkflowValidationError(f"duplicate node id(s): {sorted(set(duplicated))}")

    raw_edges = data.get("edges", [])
    if not isinstance(raw_edges, list):
        raise WorkflowValidationError("spec.edges must be a list")
    edges = tuple(_parse_edge(item) for item in raw_edges)
    for edge in edges:
        for endpoint in (edge.source, edge.target):
            if endpoint not in seen:
                raise WorkflowValidationError(
                    f"unknown node {endpoint!r} referenced by edge "
                    f"{edge.source!r} -> {edge.target!r}"
                )

    limits = _resolve_limits(
        data,
        default_recursion_limit=default_recursion_limit,
        default_max_nodes=default_max_nodes,
        default_max_runs=default_max_runs,
    )
    if len(nodes) > limits["max_nodes"]:
        raise WorkflowValidationError(
            f"workflow declares {len(nodes)} nodes > max_nodes {limits['max_nodes']}"
        )

    index = {node.id: node for node in nodes}
    control_sources = {node.id for node in nodes if node.kind == "route"}
    data_edges = tuple(edge for edge in edges if edge.source not in control_sources)
    _validate_cycles(nodes, edges)
    _validate_reducers(index, data_edges)
    _validate_kind_specific(index)
    # Q10：foreach 的 ``source`` 递归只沿数据边向上——若 source 落在 route 参与的
    # 环里（``_validate_cycles`` 允许「环上有 route」），跨层解析就没有确定终点。
    # 复用 Tarjan SCC，查「source 是否在环分量里」。
    _validate_foreach_source_cycles(index, edges)

    entry = _parse_id_list(data.get("entry"), "spec.entry")
    terminal = _parse_id_list(data.get("terminal"), "spec.terminal")
    for node_id in (*entry, *terminal):
        if node_id not in seen:
            raise WorkflowValidationError(f"unknown node {node_id!r} in entry/terminal")
    if not entry:
        # 隐式入口 = 完全没有入边的节点。只被 route 控制边指向的节点（回边目标、
        # 条件分支出口）不是入口——它们在调度器里等 route 的激活。
        entry = tuple(
            node.id for node in nodes if not any(edge.target == node.id for edge in edges)
        )
        if not entry:
            raise WorkflowValidationError(
                "workflow has no implicit entry (every node has an incoming edge); "
                "declare spec.entry explicitly"
            )
    if not terminal:
        terminal = tuple(
            node.id for node in nodes if not any(edge.source == node.id for edge in edges)
        )

    return WorkflowSpec(
        goal=goal,
        nodes=nodes,
        edges=edges,
        entry=entry,
        terminal=terminal,
        schema_version=schema_version,
        recursion_limit=limits["recursion_limit"],
        max_nodes=limits["max_nodes"],
        max_runs=limits["max_runs"],
        _index=index,
    )


def _resolve_limits(
    data: Mapping[str, Any],
    *,
    default_recursion_limit: int,
    default_max_nodes: int,
    default_max_runs: int,
) -> dict[str, int]:
    return {
        "recursion_limit": _positive_int(
            data.get("recursion_limit", default_recursion_limit), "spec.recursion_limit"
        ),
        "max_nodes": _positive_int(
            data.get("max_nodes", default_max_nodes), "spec.max_nodes"
        ),
        "max_runs": _positive_int(data.get("max_runs", default_max_runs), "spec.max_runs"),
    }


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkflowValidationError(f"{field_name} must be a positive integer")
    return value


def _parse_id_list(raw: Any, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise WorkflowValidationError(f"{field_name} must be a list of node ids")
    return tuple(raw)


def _parse_node(raw: Any) -> WorkflowNode:
    if not isinstance(raw, Mapping):
        raise WorkflowValidationError("each node must be a JSON object")
    data = dict(raw)
    unknown = set(data) - _NODE_FIELDS
    if unknown:
        raise WorkflowValidationError(
            f"unknown node field(s): {sorted(unknown)}; allowed: {sorted(_NODE_FIELDS)}"
        )
    node_id = data.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise WorkflowValidationError("each node needs a non-empty string id")
    kind = data.get("kind")
    if kind not in NODE_KINDS:
        raise WorkflowValidationError(
            f"node {node_id!r} has unsupported kind {kind!r}; allowed: {list(NODE_KINDS)}"
        )
    task = data.get("task", "")
    if not isinstance(task, str):
        raise WorkflowValidationError(f"node {node_id!r} task must be a string")

    outputs = data.get("outputs", ["result"])
    if not isinstance(outputs, list) or not outputs:
        raise WorkflowValidationError(f"node {node_id!r} outputs must be a non-empty list")
    if not all(isinstance(slot, str) and slot for slot in outputs):
        raise WorkflowValidationError(f"node {node_id!r} outputs must be slot names")

    mode = data.get("mode")
    if mode is not None and mode not in ("build", "read_only", "plan"):
        raise WorkflowValidationError(
            f"node {node_id!r} mode must be build/read_only/plan"
        )

    node = WorkflowNode(
        id=node_id,
        kind=kind,
        task=task,
        name=_optional_str(data.get("name"), f"node {node_id!r} name"),
        description=_optional_str(
            data.get("description", ""), f"node {node_id!r} description"
        )
        or "",
        mode=mode,
        outputs=tuple(outputs),
        join=_parse_join(data.get("join", "all_required"), node_id),
        strategy=_parse_strategy(data.get("strategy", "llm"), node_id),
        deadline_s=_parse_deadline(data.get("deadline_s"), node_id),
        cases=_parse_cases(data.get("cases"), node_id),
        default=_optional_str(data.get("default"), f"node {node_id!r} default"),
        max_routes=_parse_max_routes(data.get("max_routes", 1), node_id),
        items=_parse_items(data.get("items"), node_id),
        source=_optional_str(data.get("source"), f"node {node_id!r} source"),
        source_field=_optional_str(
            data.get("source_field"), f"node {node_id!r} source_field"
        ),
        max_items=_parse_max_items(data.get("max_items", 20), node_id),
        max_tokens=_parse_node_max_tokens(data.get("max_tokens"), node_id),
        max_time_s=_parse_node_max_time_s(data.get("max_time_s"), node_id),
    )
    if node.kind == "subagent" and not node.task:
        raise WorkflowValidationError(f"subagent node {node_id!r} needs a task")
    if node.kind == "foreach" and not node.task:
        raise WorkflowValidationError(f"foreach node {node_id!r} needs an item task")
    if node.kind == "foreach":
        has_items = node.items is not None
        has_source = node.source is not None
        if has_items == has_source:
            raise WorkflowValidationError(
                f"foreach node {node_id!r} needs exactly one of items/source"
            )
        if has_source and not node.source_field:
            raise WorkflowValidationError(
                f"foreach node {node_id!r} needs source_field alongside source"
            )
    if node.kind == "route":
        if not node.cases and node.default is None:
            raise WorkflowValidationError(
                f"route node {node_id!r} needs at least one case or a default"
            )
    return node


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkflowValidationError(f"{field_name} must be a string")
    return value


def _parse_join(value: Any, node_id: str) -> str:
    if value not in JOIN_SEMANTICS:
        raise WorkflowValidationError(
            f"aggregate node {node_id!r} join must be one of {list(JOIN_SEMANTICS)}"
        )
    return value


def _parse_strategy(value: Any, node_id: str) -> str:
    if value not in AGGREGATE_STRATEGIES:
        raise WorkflowValidationError(
            f"aggregate node {node_id!r} strategy must be one of "
            f"{list(AGGREGATE_STRATEGIES)}"
        )
    return value


def _parse_deadline(value: Any, node_id: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise WorkflowValidationError(
            f"aggregate node {node_id!r} deadline_s must be a positive number"
        )
    return float(value)


def _parse_max_routes(value: Any, node_id: str) -> int:
    return _positive_int(value, f"route node {node_id!r} max_routes")


def _parse_max_items(value: Any, node_id: str) -> int:
    """``max_items`` 专用的**非负**解析（Q9）：``0`` = 不做静态截断。

    不能复用 :func:`_positive_int`——它对 ``value < 1`` 直接拒绝，而该函数还服务
    ``max_routes``/``recursion_limit``/``max_nodes``/``max_tokens``，把 0 放行到那里
    会静默删掉 C2 的结构闸语义。
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkflowValidationError(
            f"foreach node {node_id!r} max_items must be a non-negative integer "
            f"(0 = expand until the run budget is exhausted)"
        )
    return value


def _parse_node_max_tokens(value: Any, node_id: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, f"node {node_id!r} max_tokens")


def _parse_node_max_time_s(value: Any, node_id: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise WorkflowValidationError(
            f"node {node_id!r} max_time_s must be a positive number"
        )
    return float(value)


def _parse_items(value: Any, node_id: str) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise WorkflowValidationError(f"foreach node {node_id!r} items must be a list")
    return tuple(value)


def _parse_cases(value: Any, node_id: str) -> tuple[RouteCase, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise WorkflowValidationError(f"route node {node_id!r} cases must be a list")
    cases: list[RouteCase] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"when", "to"}:
            raise WorkflowValidationError(
                f"route node {node_id!r} case must be {{'when': ..., 'to': ...}}"
            )
        when, to = item["when"], item["to"]
        if not isinstance(when, str) or not when:
            raise WorkflowValidationError(f"route node {node_id!r} case 'when' must be a string")
        if not isinstance(to, str) or not to:
            raise WorkflowValidationError(f"route node {node_id!r} case 'to' must be a string")
        cases.append(RouteCase(when=when, to=to))
    return tuple(cases)


def _parse_edge(raw: Any) -> WorkflowEdge:
    if not isinstance(raw, Mapping):
        raise WorkflowValidationError("each edge must be a JSON object")
    data = dict(raw)
    unknown = set(data) - _EDGE_FIELDS
    if unknown:
        raise WorkflowValidationError(
            f"unknown edge field(s): {sorted(unknown)}; allowed: {sorted(_EDGE_FIELDS)}"
        )
    source, target = data.get("from"), data.get("to")
    if not isinstance(source, str) or not source:
        raise WorkflowValidationError("each edge needs a 'from' node id")
    if not isinstance(target, str) or not target:
        raise WorkflowValidationError("each edge needs a 'to' node id")
    channel = data.get("channel", "summary")
    if channel not in CHANNELS:
        raise WorkflowValidationError(
            f"edge {source!r} -> {target!r} channel must be one of {list(CHANNELS)}"
        )
    required = data.get("required", True)
    if not isinstance(required, bool):
        raise WorkflowValidationError(
            f"edge {source!r} -> {target!r} required must be a boolean"
        )
    reducer = data.get("reducer")
    if reducer is not None and reducer not in REDUCERS:
        raise WorkflowValidationError(
            f"edge {source!r} -> {target!r} reducer {reducer!r} is not allowed; "
            f"allowed: {list(REDUCERS)}"
        )
    return WorkflowEdge(
        source=source, target=target, channel=channel, required=required, reducer=reducer
    )


def _validate_cycles(
    nodes: tuple[WorkflowNode, ...], edges: tuple[WorkflowEdge, ...]
) -> None:
    """环上必须有 route 节点（唯一带条件出口 + max_routes 上限的节点）。"""
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        adjacency[edge.source].append(edge.target)
    kinds = {node.id: node.kind for node in nodes}

    for component in _strongly_connected_components(tuple(adjacency), adjacency):
        cyclic = len(component) > 1 or component[0] in adjacency[component[0]]
        if not cyclic:
            continue
        if not any(kinds[node_id] == "route" for node_id in component):
            raise WorkflowValidationError(
                "cycle without a route node is not allowed (no conditional exit): "
                f"{sorted(component)}"
            )


def _strongly_connected_components(
    node_ids: tuple[str, ...], adjacency: Mapping[str, list[str]]
) -> list[list[str]]:
    """Iterative Tarjan SCC（stdlib-only，避免递归深度风险）。"""
    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in node_ids:
        if root in index_of:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_index = work[-1]
            if child_index == 0:
                index_of[node] = counter
                lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            recurse = False
            neighbours = adjacency[node]
            for position in range(child_index, len(neighbours)):
                child = neighbours[position]
                if child not in index_of:
                    work[-1] = (node, position + 1)
                    work.append((child, 0))
                    recurse = True
                    break
                if child in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[child])
            if recurse:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def _validate_reducers(
    index: Mapping[str, WorkflowNode], edges: tuple[WorkflowEdge, ...]
) -> None:
    """多入边写同槽必须声明一致的 reducer（D5）。"""
    by_target: dict[str, list[WorkflowEdge]] = {}
    for edge in edges:
        by_target.setdefault(edge.target, []).append(edge)

    for target, incoming in by_target.items():
        slots: dict[str, list[WorkflowEdge]] = {}
        for edge in incoming:
            for slot in index[edge.source].outputs:
                slots.setdefault(slot, []).append(edge)
        for slot, writers in slots.items():
            distinct_sources = {edge.source for edge in writers}
            if len(distinct_sources) < 2:
                continue
            missing = sorted({edge.source for edge in writers if edge.reducer is None})
            if missing:
                raise WorkflowValidationError(
                    f"node {target!r} slot {slot!r} is written by multiple upstreams "
                    f"{sorted(distinct_sources)} but {missing} declare no reducer; "
                    f"declare one of {list(REDUCERS)}"
                )
            declared = {edge.reducer for edge in writers}
            if len(declared) > 1:
                raise WorkflowValidationError(
                    f"node {target!r} slot {slot!r} has conflicting reducers "
                    f"{sorted(declared)}"
                )


def _validate_foreach_source_cycles(
    index: Mapping[str, WorkflowNode], edges: tuple[WorkflowEdge, ...]
) -> None:
    """foreach 的 ``source`` 不得指向 route 参与环内的节点（Q10）。

    跨层解析是「沿数据边向上找第一个物化该槽的节点」。若 ``source`` 坐在一个含
    route 的回边环上，它每次激活都可能看到不同的上游产出，递归也没有确定终点。
    这里复用 :func:`_strongly_connected_components`（Tarjan）在**全量边图**上找强连通
    分量：任一 ``source`` 落在环分量里即拒绝。

    用全量边（而不是数据边）：``_validate_cycles`` 保证每个环里都有 route，而 route
    的出边是控制边——数据边子图因此恒为 DAG，只看数据边永远判不出「source 在环上」。
    """
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in index}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
    cyclic_members: set[str] = set()
    for component in _strongly_connected_components(tuple(adjacency), adjacency):
        cyclic = len(component) > 1 or component[0] in adjacency.get(component[0], [])
        if cyclic:
            cyclic_members.update(component)
    for node in index.values():
        if node.kind != "foreach" or node.source is None:
            continue
        if node.source in cyclic_members:
            raise WorkflowValidationError(
                f"foreach node {node.id!r} source {node.source!r} lies on a cycle "
                f"(route back-edge); cross-layer source resolution has no "
                f"deterministic terminus"
            )


def _validate_kind_specific(index: Mapping[str, WorkflowNode]) -> None:
    for node in index.values():
        if node.kind == "aggregate":
            if node.join == "best_effort" and node.deadline_s is None:
                raise WorkflowValidationError(
                    f"aggregate node {node.id!r} with join=best_effort needs deadline_s"
                )
        elif node.kind == "route":
            for case in node.cases:
                if case.to not in index:
                    raise WorkflowValidationError(
                        f"route node {node.id!r} case target {case.to!r} is not a known node"
                    )
                # 动态条件源（D4/Q3）：校验「节点存在 + 槽已声明（含隐式 result 槽）」。
                # **不**把数据可达性作 schema 硬条件——ref 目标可以不在 route 的数据
                # 上游（运行期槽缺失静默走 default，diagnostics 记原因）。
                if is_route_ref(case.when):
                    ref = parse_route_ref(case.when)
                    if ref is None:
                        raise WorkflowValidationError(
                            f"route node {node.id!r} case when {case.when!r} is a "
                            f"malformed $ref; expected '$ref:<node_id>:<slot>'"
                        )
                    ref_node_id, ref_slot = ref
                    ref_node = index.get(ref_node_id)
                    if ref_node is None:
                        raise WorkflowValidationError(
                            f"route node {node.id!r} case when {case.when!r} references "
                            f"unknown node {ref_node_id!r}"
                        )
                    declared = declared_slots(ref_node)
                    if ref_slot not in declared:
                        raise WorkflowValidationError(
                            f"route node {node.id!r} case when {case.when!r} references "
                            f"slot {ref_slot!r} not declared by node {ref_node_id!r} "
                            f"(declared: {sorted(declared)})"
                        )
            if node.default is not None and node.default not in index:
                raise WorkflowValidationError(
                    f"route node {node.id!r} default {node.default!r} is not a known node"
                )
        elif node.kind == "foreach":
            if node.source is not None and node.source not in index:
                raise WorkflowValidationError(
                    f"foreach node {node.id!r} source {node.source!r} is not a known node"
                )


def with_limits(spec: WorkflowSpec, **overrides: Any) -> WorkflowSpec:
    """Return a copy of ``spec`` with limit overrides (used by config plumbing)."""
    allowed = {"recursion_limit", "max_nodes", "max_runs"}
    unknown = set(overrides) - allowed
    if unknown:
        raise WorkflowValidationError(f"unknown limit override(s): {sorted(unknown)}")
    return replace(spec, **overrides)

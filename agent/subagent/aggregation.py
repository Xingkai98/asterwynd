"""分层汇聚的**执行计划**（change ``workflow-result-aggregation``，D2 + Q3/Q4）。

设计口径来自 ``design.md`` D2/D3 与 ``reviews/grill-design.md`` 决策 4/6 及用户确认
Q3/Q4/Q7/Q8：

- **不原地改 ``WorkflowSpec``**：模型声明的 spec 是不可变事实，``spec_hash`` 是 C5
  replay 的锚点。自动兜底把它投影成一份独立的 :class:`ExecutionPlan`（含插入节点与
  每节点 token 预算的 side table）。
- **三 hash 分离**：``declared_spec_hash``（原始 spec，永不因自动插节点变化）/
  ``expansion_plan_hash``（foreach 展开计划）/ ``runtime_graph_hash``（含自动插节点的
  实际执行图）。三者在本 change 前同源，现在分开记录。
- **阈值与层数**（Q4）：单 aggregate 直接上游 ``> 10``（恰好 10 不触发）时自动插入
  分层 aggregate；层数按 fan-in 分组 ``ceil(n / 10)``，逐层向上直到 root 输入 ≤ 10
  （不用 ``ceil(log10(n))`` 的层数公式，那会过度分层）。
- **部分显式树补缺**：只补缺失层，模型已声明的层原样保留。
- **预算按「距 leaf 层数」**：第 1 层 shard 800，再上 domain 1500，根（链上最上层的
  aggregate）root 3000，leaf 自身 300。四档都来自 ``AggregationConfig``（D6/Q8）。
- **auto aggregate 默认 ``strategy="llm"``**（Q4）：``collect`` 只是文本拼接、不解决
  prompt 膨胀，因此自动兜底层必须是真实 LLM run，其预算计入 ``max_nodes`` + ``max_runs``。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.context.summarizer import Summarizer, TruncationSummarizer
from agent.subagent.workflow import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowSpec,
)

#: 单个 aggregate 能直接消费的上游上限（Q4：阈值是 ``> 10``，恰好 10 不拆分）。
MAX_FAN_IN = 10

#: 自动插入节点的 id 前缀。模型声明的 id 撞上这个前缀会被拒绝（见 ``build``）。
AUTO_NODE_PREFIX = "__auto_agg__"

#: 四档分层 token 预算默认值（D2/G4 决议，Q4 确认层级判据）。
#:
#: **语义（Q7 要求明确）**：这是「每层 / 每节点」的 token 总量口径，度量的是**一个
#: 节点向它的消费者贡献多少文本**——不是字符数，也**不是** ``run_subagent`` 的
#: ``max_tokens``。两者不能混：
#:
#: - 作为 ``max_tokens`` 用时，``leaf=300`` 会让一个真实干活的 leaf run 立刻被预算
#:   杀掉（300 token 连一轮思考都不够）；
#: - 作为「向上贡献量」用时，``leaf 300`` 的含义是「一个 leaf 的产出进入下游 prompt
#:   时最多占 300 token」——这正是防 prompt 膨胀要限的量。
#:
#: 消费点：``WorkflowAggregator.bounded``（裁剪单份贡献）、
#: ``ExecutionPlan.budget_for``（按距 leaf 层数定档）、collect 聚合的
#: ``WorkflowAggregator.merge``（压缩多份贡献）。节点显式声明的 ``max_tokens``
#: 优先于档位（``WorkflowNode.max_tokens`` 仍然是 run 级预算，语义不同但显式优先）。
DEFAULT_TOKEN_BUDGETS: dict[str, int] = {
    "leaf": 300,
    "shard": 800,
    "domain": 1500,
    "root": 3000,
}

#: 每 token 折算的字符数（bounded formatter 按字符裁剪，与 bus 的估算同口径）。
CHARS_PER_TOKEN = 4

_BOUNDED_MARKER = "\n…[bounded; read the full result via result_ref]"


class WorkflowAggregator:
    """workflow 级汇聚器（D5）：把**多节点结果文本**压成 bounded 贡献。

    复用点是 :mod:`agent.context.summarizer` 的 :class:`Summarizer` Protocol，尤其
    ``compress(tier_summaries: list[str], budget)``——签名正是「多份文本 + 预算」，
    与 workflow 级汇聚的输入同型。``MemoryManager`` 的 L1/L2 是实例私有、绑定单
    AgentLoop 的 ``messages`` 流，无直接复用入口（grill 决策 8）。

    两档能力，职责分明：

    - :meth:`bounded`（同步）：按层预算裁剪单份贡献。调度器构造下游 task 文本时走
      这条——它必须在**同步**的 formatter 路径上完成，不能 await。
    - :meth:`merge`（异步）：把一份 shard 的多条贡献交给 summarizer 语义压缩。
      无 LLM 时退回 ``TruncationSummarizer`` 的拼接，且**仍然有界**（否则「没有 LLM」
      会变成绕过预算的旁路）。
    """

    def __init__(self, summarizer: Summarizer | None = None) -> None:
        self._summarizer: Summarizer = summarizer or TruncationSummarizer()

    @property
    def summarizer(self) -> Summarizer:
        return self._summarizer

    def bounded(self, text: str, *, budget: int) -> str:
        """把一份贡献裁到 ``budget`` token（短文本 no-op）。"""
        if not text:
            return ""
        limit = max(int(budget), 1) * CHARS_PER_TOKEN
        if len(text) <= limit:
            return text
        return text[:limit] + _BOUNDED_MARKER

    async def merge(self, contributions: list[str], *, budget: int) -> str:
        """把多份贡献汇聚成一份 bounded 文本（先走 summarizer，再兜底裁剪）。"""
        texts = [text for text in contributions if text]
        if not texts:
            return ""
        compressed: str | None = None
        try:
            compressed = await self._summarizer.compress(texts, budget)
        except Exception:  # noqa: BLE001 - 汇聚失败退回拼接，不丢结果
            compressed = None
        if compressed:
            return self.bounded(compressed, budget=budget)
        return self.bounded("\n\n---\n\n".join(texts), budget=budget)


@dataclass(frozen=True)
class AutoAggregateLayer:
    """自动兜底的一层：把 ``fan_in`` 个上游分组成 ``group_count`` 个新 aggregate。"""

    fan_in: int
    group_count: int


def plan_layer_insertions(count: int, max_fan_in: int = MAX_FAN_IN) -> list[AutoAggregateLayer]:
    """给定一个 aggregate 的**逻辑上游数**，算出需要插入几层、每层几个节点。

    逐层向上：第 1 层把 ``count`` 个贡献分成 ``ceil(count / max_fan_in)`` 组；若该组数
    仍 > ``max_fan_in``，再插一层，直到最上层输出 ≤ ``max_fan_in``（Q4）。
    """
    if count <= max_fan_in:
        return []
    layers: list[AutoAggregateLayer] = []
    remaining = count
    while True:
        groups = math.ceil(remaining / max_fan_in)
        layers.append(AutoAggregateLayer(fan_in=remaining, group_count=groups))
        if groups <= max_fan_in:
            return layers
        remaining = groups


def budget_for_distance(distance: int, budgets: Mapping[str, int]) -> int:
    """按「距 leaf 层数」取预算档：0=leaf / 1=shard / 2=domain / ≥3=root。"""
    if distance <= 0:
        return budgets["leaf"]
    if distance == 1:
        return budgets["shard"]
    if distance == 2:
        return budgets["domain"]
    return budgets["root"]


def _hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ExecutionPlan:
    """一份 spec 的执行投影：可能含自动插入的 aggregate 层 + 每节点预算。

    对调度器暴露与 :class:`WorkflowSpec` 同形的查询接口（``data_incoming`` /
    ``data_outgoing`` / ``incoming`` / ``outgoing`` / ``is_control_edge`` /
    ``node`` / ``has_node``），因此调度器只需把 ``self._spec.xxx`` 换成
    ``self._plan.xxx`` 即可消费自动插入的图。
    """

    nodes: tuple[WorkflowNode, ...]
    edges: tuple[WorkflowEdge, ...]
    entry: tuple[str, ...]
    terminal: tuple[str, ...]
    declared_spec_hash: str
    expansion_plan_hash: str
    runtime_graph_hash: str
    inserted_nodes: tuple[str, ...]
    budgets: Mapping[str, int]
    max_fan_in: int = MAX_FAN_IN
    #: 构建本计划用的四档预算（``with_expansion`` 需要它，而不是已被 distance
    #: 覆盖成 per-node 值的 ``budgets``）。
    tiers: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_TOKEN_BUDGETS))
    #: **模型声明的**节点/边（不含自动插入层）。``with_expansion`` 必须从这一份重建，
    #: 否则第二次展开会把上次插入的 auto 节点当成声明节点，撞上保留前缀校验。
    declared_nodes: tuple[WorkflowNode, ...] = ()
    declared_edges: tuple[WorkflowEdge, ...] = ()
    _expansions: Mapping[str, int] = field(default_factory=dict)
    _index: Mapping[str, WorkflowNode] = field(default_factory=dict, repr=False, compare=False)
    _control_sources: frozenset[str] = field(default_factory=frozenset, repr=False, compare=False)

    # -- 与 WorkflowSpec 同形的查询 -----------------------------------------

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
        return edge.source in self._control_sources

    def data_incoming(self, node_id: str) -> tuple[WorkflowEdge, ...]:
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

    # -- 预算 ---------------------------------------------------------------

    def budget_for(self, node_id: str) -> int:
        """该节点向上贡献文本的 token 预算（按距 leaf 层数定档）。"""
        if node_id in self.budgets:
            return self.budgets[node_id]
        node = self._index.get(node_id)
        if node is not None and node.max_tokens:
            return node.max_tokens
        return DEFAULT_TOKEN_BUDGETS["leaf"]

    def char_budget_for(self, node_id: str) -> int:
        """bounded formatter 的字符预算（token 预算 × ``CHARS_PER_TOKEN``）。"""
        return self.budget_for(node_id) * CHARS_PER_TOKEN

    # -- 展开期复检（Q3） ---------------------------------------------------

    def with_expansion(self, node_id: str, count: int) -> "ExecutionPlan":
        """把某个 foreach 节点的展开项数记进计划并重算插层（声明期 + 展开期都算）。"""
        if not self.has_node(node_id):
            raise KeyError(f"unknown node id: {node_id}")
        expansions = dict(self._expansions)
        expansions[node_id] = max(int(count), 1)
        declared = self.declared_nodes or self.nodes
        declared_edges = self.declared_edges or self.edges
        return ExecutionPlan.build(
            WorkflowSpec(
                goal="",
                nodes=declared,
                edges=declared_edges,
                entry=self.entry,
                terminal=self.terminal,
                _index={node.id: node for node in declared},
            ),
            max_fan_in=self.max_fan_in,
            budgets=dict(self.tiers),
            expansions=expansions,
            declared_spec_hash=self.declared_spec_hash,
        )

    # -- 构建 ---------------------------------------------------------------

    @classmethod
    def build(
        cls,
        spec: WorkflowSpec,
        *,
        max_fan_in: int = MAX_FAN_IN,
        budgets: Mapping[str, int] | None = None,
        expansions: Mapping[str, int] | None = None,
        declared_spec_hash: str | None = None,
    ) -> "ExecutionPlan":
        budgets = dict(budgets or DEFAULT_TOKEN_BUDGETS)
        expansions = dict(expansions or {})
        declared = tuple(spec.nodes)
        for node in declared:
            if node.id.startswith(AUTO_NODE_PREFIX):
                raise ValueError(
                    f"node id {node.id!r} uses the reserved prefix {AUTO_NODE_PREFIX!r}"
                )

        nodes = list(declared)
        edges = list(spec.edges)
        control_sources = {node.id for node in declared if node.kind == "route"}
        inserted: list[str] = []

        def is_data_edge(edge: WorkflowEdge) -> bool:
            return edge.source not in control_sources

        # 每个 aggregate 的「逻辑上游贡献数」：foreach 展开项数在声明期按 1 算，
        # 展开期按实际项数算（Q3：两处都算）。
        for node in declared:
            if node.kind != "aggregate":
                continue
            incoming = [
                edge
                for edge in edges
                if edge.target == node.id and is_data_edge(edge)
            ]
            contributions = sum(expansions.get(edge.source, 1) for edge in incoming)
            layers = plan_layer_insertions(contributions, max_fan_in)
            if not layers:
                continue
            inserted.extend(
                _insert_layers(
                    node_id=node.id,
                    incoming=incoming,
                    layers=layers,
                    max_fan_in=max_fan_in,
                    expansions=expansions,
                    nodes=nodes,
                    edges=edges,
                )
            )

        node_tuple = tuple(nodes)
        edge_tuple = tuple(edges)
        index = {node.id: node for node in node_tuple}
        structure = {
            "nodes": [node.to_dict() for node in node_tuple],
            "edges": [edge.to_dict() for edge in edge_tuple],
        }
        # 声明哈希是**原始 spec** 的锚点（C5 replay 前提）：``with_expansion`` 重建时
        # 折回的 spec 是执行图投影，不能再从它算声明哈希（Q3 三 hash 分离）。
        declared_hash = declared_spec_hash or spec.spec_hash
        expansion_hash = (
            declared_hash
            if not expansions
            else _hash({"declared": declared_hash, "expansions": dict(sorted(expansions.items()))})
        )
        runtime_hash = (
            expansion_hash if not inserted else _hash({"expansion": expansion_hash, **structure})
        )
        plan = cls(
            nodes=node_tuple,
            edges=edge_tuple,
            entry=spec.entry,
            terminal=spec.terminal,
            declared_spec_hash=declared_hash,
            expansion_plan_hash=expansion_hash,
            runtime_graph_hash=runtime_hash,
            inserted_nodes=tuple(inserted),
            budgets=_assign_budgets(node_tuple, edge_tuple, index, control_sources, budgets),
            max_fan_in=max_fan_in,
            tiers=dict(budgets),
            declared_nodes=declared,
            declared_edges=tuple(spec.edges),
            _expansions=expansions,
            _index=index,
            _control_sources=frozenset(control_sources),
        )
        return plan


def _insert_layers(
    *,
    node_id: str,
    incoming: list[WorkflowEdge],
    layers: list[AutoAggregateLayer],
    max_fan_in: int,
    expansions: Mapping[str, int],
    nodes: list[WorkflowNode],
    edges: list[WorkflowEdge],
) -> list[str]:
    """在 ``node_id`` 与其上游之间插入 ``layers`` 层 aggregate，返回新节点 id。"""
    reducer_by_source = {edge.source: edge.reducer for edge in incoming}
    required_by_source = {edge.source: edge.required for edge in incoming}
    # 上游按「逻辑贡献」展开：foreach 展开 N 项时它在分组里占 N 个位置，
    # 但边仍然只有一条（渲染在同一个 foreach 节点上）。
    upstreams: list[str] = []
    for edge in incoming:
        upstreams.extend([edge.source] * expansions.get(edge.source, 1))
    inserted: list[str] = []
    current = upstreams
    for layer_index, layer in enumerate(layers):
        groups = [current[i : i + max_fan_in] for i in range(0, len(current), max_fan_in)]
        next_level: list[str] = []
        for group_index, group in enumerate(groups):
            new_id = f"{AUTO_NODE_PREFIX}{node_id}_{layer_index}_{group_index}"
            nodes.append(
                WorkflowNode(
                    id=new_id,
                    kind="aggregate",
                    join="all_required",
                    strategy="llm",  # Q4：collect 只是拼接，不解决 prompt 膨胀
                    outputs=("result",),
                    name=f"auto-aggregate for {node_id}",
                    description=(
                        "scheduler-inserted aggregation layer "
                        f"(level {layer_index + 1}, {len(set(group))} upstreams)"
                    ),
                )
            )
            inserted.append(new_id)
            for source in sorted(set(group)):
                edges.append(
                    WorkflowEdge(
                        source=source,
                        target=new_id,
                        channel="summary",
                        required=required_by_source.get(source, True),
                        reducer=reducer_by_source.get(source) or "concat",
                    )
                )
            next_level.append(new_id)
        current = next_level

    # 原边直连 root 的（上游 → node_id）替换成最上层新节点 → node_id。
    edges[:] = [edge for edge in edges if not (edge.target == node_id and edge in incoming)]
    for new_id in current:
        edges.append(
            WorkflowEdge(
                source=new_id,
                target=node_id,
                channel="summary",
                required=True,
                reducer="concat",
            )
        )
    return inserted


def _assign_budgets(
    nodes: tuple[WorkflowNode, ...],
    edges: tuple[WorkflowEdge, ...],
    index: Mapping[str, WorkflowNode],
    control_sources: set[str],
    budgets: Mapping[str, int],
) -> dict[str, int]:
    """给每个节点定档。

    判据是「距 leaf 层数」（Q4）：leaf 距离 0 取 leaf 档，第 1 层 shard 档，再上
    domain 档。链上**最上层**的 aggregate（不再喂给别的 aggregate）等价于设计里的
    「root」，取 root 档——否则一张 3 层树的最顶层只能拿到 domain 预算。
    节点自带的 ``max_tokens`` 覆盖档位（显式声明优先）。
    """
    distance = _distances_from_leaf(nodes, edges, control_sources)
    result: dict[str, int] = {}
    for node in nodes:
        if node.max_tokens:
            result[node.id] = node.max_tokens
        elif node.kind == "aggregate" and not _feeds_aggregate(
            node.id, edges, index, control_sources
        ):
            result[node.id] = budgets["root"]
        else:
            result[node.id] = budget_for_distance(distance.get(node.id, 0), budgets)
    return result


def _distances_from_leaf(
    nodes: tuple[WorkflowNode, ...],
    edges: tuple[WorkflowEdge, ...],
    control_sources: set[str],
) -> dict[str, int]:
    """数据边的「距 leaf 层数」（leaf = 无数据入边的节点，距离 0）。

    固定点迭代而非深搜：回边（route 参与的环）不应让距离发散——迭代次数以节点数
    为上界，环上的距离会稳定在一个有限值。
    """
    data_edges = [
        (edge.source, edge.target) for edge in edges if edge.source not in control_sources
    ]
    incoming_counts = {node.id: 0 for node in nodes}
    for _source, target in data_edges:
        incoming_counts[target] = incoming_counts.get(target, 0) + 1
    distance = {
        node.id: (0 if incoming_counts.get(node.id, 0) == 0 else 1) for node in nodes
    }
    for _ in range(len(nodes) + 1):
        changed = False
        for source, target in data_edges:
            candidate = distance.get(source, 0) + 1
            if candidate > distance.get(target, 0):
                distance[target] = candidate
                changed = True
        if not changed:
            break
    return distance


def _feeds_aggregate(
    node_id: str,
    edges: tuple[WorkflowEdge, ...],
    index: Mapping[str, WorkflowNode],
    control_sources: set[str],
) -> bool:
    """该节点是否有数据出边指向另一个 aggregate（有 → 它不是链上最上层）。"""
    for edge in edges:
        if edge.source != node_id or edge.source in control_sources:
            continue
        target = index.get(edge.target)
        if target is not None and target.kind == "aggregate":
            return True
    return False

"""Workflow DSL 的 DAG 调度器（change ``workflow-dsl-scheduler``，D3/D4/D6）。

分工（grill 决策 3）：``SubAgentManager`` 仍是「实际 LLM/tool 执行」的并发上限与
排队实现；调度器**不复用** manager 的单条 FIFO 队列做自己的数据结构，而是自持
节点状态机（``pending``/``started``/``completed``/``failed``/``cancelled``/
``blocked``）+ ready 集合 + 依赖门控 + 准入决策，manager 只当物理并发背闸。

关键口径：

- **准入背压**（Q2）：调度器只在「在途 run 数 < ``max_active`` + ``max_queued_runs``」
  时才派发新 run，因此 workflow **永不**触发 ``queue_full``（后者会静默丢弃 run
  record，可观测性断裂）。
- **superstep**（Q5/D6）：一次「就绪一批 → 派发 → 等一批完成」算 1 步，
  超过图级 ``recursion_limit`` 抛 :class:`GraphRecursionError`。
- **汇合语义**（D4/Q3）：``all_required`` 等所有 required 上游终态（失败不
  fail-fast）；``best_effort`` 在 ``deadline_s`` 到点时取消仍在跑的臂
  （``CancelSubagentRun`` + checkpoint）并按已完成结果聚合。
- **身份 set 点**（grill 决策 1/2）：``workflow_id``/``node_id``/``bus`` 在
  **调用 ``manager.run_subagent`` 的那个上下文**里 set —— C1 的 ``_enqueue_run``
  用 ``copy_context()`` 捕获入队上下文，执行期再 set 一律丢失。
- **回边**（D7/Q9）：``route`` 节点的出边是控制边（激活下游）；非 route 出边是数据边。
  数据边重跑会级联复位下游（同一 session 复用），因此 peer-review 模板里
  producer/reviewer 跨轮复用同一会话，聚合只取每个节点的最新一次 run。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Mapping

from agent.subagent.aggregation import (
    AUTO_NODE_PREFIX,
    CHARS_PER_TOKEN,
    DEFAULT_TOKEN_BUDGETS,
    ExecutionPlan,
    MAX_FAN_IN,
    WorkflowAggregator,
    _distances_from_leaf,
)
from agent.context.summarizer import LLMSummarizer, Summarizer
from agent.subagent.bus import MessageBus
from agent.subagent.context import (
    reset_bus,
    reset_graph_distance,
    reset_node_id,
    reset_workflow_id,
    set_bus,
    set_graph_distance,
    set_node_id,
    set_workflow_id,
)
from agent.subagent.workflow import (
    REDUCERS,
    WorkflowEdge,
    WorkflowNode,
    WorkflowSpec,
    WorkflowValidationError,
    is_route_ref,
    parse_route_ref,
)
from agent.subagent.workflow_budget import WorkflowBudget, WorkflowBudgetExceeded
from agent.subagent.workflow_store import WorkflowStore
from agent.trace_recorder import count_failures

if TYPE_CHECKING:
    from agent.config import AsterwyndConfig
    from agent.subagent.manager import SubAgentManager

logger = logging.getLogger("asterwynd.subagent")

# 终态节点状态：汇合门控只看这些。
# ``budget_exceeded`` 是 C4 新增的**节点级**终态（Q5）：被预算停下但未派发的根节点
# 标它而不是 ``blocked``。不加进来，被标的上游会让下游的 ``_data_deps_satisfied``
# 永远为 False（Confirmed Decision 7）。
# ``skipped``（change ``enhance-workflow-graph-ux`` D2b）是「route 判定没走这条」
# 的**良性终态**——它既不失败也不受阻，但必须算终态，否则门控会把它的下游
# 永远卡住、收敛判定也会把它当未完成。
TERMINAL_NODE_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "blocked", "budget_exceeded", "skipped"}
)

# Run 终态（与 manager.TERMINAL_RUN_STATUSES 同口径 + queue_full 这个「从未发生」态）。
TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "budget_exceeded", "queue_full"}
)

# ``_await_run`` 的轮询间隔：调度器与 run 任务同事件循环，靠让出调度来观察取消。
_POLL_INTERVAL_S = 0.01

_SUMMARY_LIMIT = 400

#: 节点因由在前端的**展示预算**（前端 ``workflow_graph.js`` 的 ``truncateText`` 在
#: 160 字符处再切）。后端注入具体因由（闸门细节等）时按这个预算压缩，保证关键信息
#: （闸门名、上限值、「本节点未派发」）落在用户可见的那 160 字符内——「后端写了真因
#: 但被前端切掉」等于没修（#218/Q4）。
_REASON_DISPLAY_LIMIT = 160

#: 「入边互相等待」因由里最多列出几个上游 id。上游 id 由节点声明决定、长度不可控
#: （实测 6 个语义化长 id 扇入时整句 179 字符，前端会在 160 处把「，本节点永远未就绪」
#: 连同右括号一起切掉），所以列出的数量必须有界。超出的用「等」收尾。
_WAITING_LIST_LIMIT = 3

#: bounded envelope 里 ``latest_events`` 的条目数上限（Q5：5 条终态迁移事件）。
_LATEST_EVENTS_LIMIT = 5
#: 单条 ``latest_events`` 的 ``summary_preview`` 字符上限（Q5：每条分配字符上限，
#: 5 × 80 = 400 字符，bounded envelope 的「bounded」由这个上界保证）。
_EVENT_PREVIEW_LIMIT = 80

#: 父 agent 面向投影的节点条数硬上限（D3「永远 bounded」；Issue 4）。
#: 与 ``max_nodes`` 默认值同量级：超过就按上限截断并用 ``nodes_omitted`` 显式报告。
_PARENT_NODES_LIMIT = 200
#: 父投影里单节点文本字段（summary/reason/error）的字符上限。
_PARENT_FIELD_LIMIT = 200

#: 图快照里带终态计数的 ``status`` 集合（change ``workflow-graph-visualization``）：
#: 只有整张图停下时计数才有意义，running 中带计数会误导视图头。
_SNAPSHOT_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        # G26（D9）：有节点失败但图正常收敛——必须算终态，否则那张图会被当成
        # running（永远排 tab 最前、永不进淘汰池、每次重连都补发）。
        "completed_with_failures",
        # workflow-terminal-honesty（#217）：零节点成功的图（图根本没跑起来）。
        # 三个副本（本集合 / workflow.js 的 TERMINAL_STATUSES / workflow_graph.js
        # 的 isGraphTerminal）必须集合相等，漏一个就会让该图被当成 running。
        "stalled",
        "failed",
        "cancelled",
        "budget_exceeded",
        "graph_recursion_exceeded",
    }
)
#: 边 ``blocked`` 的两侧状态集合（决策 7）：目标被闸门挡住，或源没有可用产出。
_EDGE_BLOCKED_TARGET_STATUSES = frozenset({"blocked", "budget_exceeded"})
_EDGE_BLOCKED_SOURCE_STATUSES = frozenset({"failed", "cancelled"})

#: 收尾判定里「数据上游把下游一起拖住」的集合（D2b 的「被连累优先于未选中」）。
#: 比 ``_EDGE_BLOCKED_SOURCE_STATUSES`` 多一个 ``blocked``：spec 的第三条 Scenario
#: 明确把「上游受阻」与「上游失败/取消」并列——漏掉它就会把「被连累」报成
#: 「条件没选它」，正是本 change 要消灭的那类假话。
_DOOMED_UPSTREAM_STATUSES = frozenset({"failed", "cancelled", "blocked"})

#: foreach 展开项的**终态**集合（G7/D5.2）：只有这些值会被 done 回调落进
#: ``item_states``；其余（``pending``/``queued``/``running``）都在投影时现算。
_ITEM_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "budget_exceeded"})

#: 项级推帧的调度器侧最小间隔（M2.3/G2）：``_emit_graph_snapshot`` 是**全量重建**
#: （遍历全部 nodes+edges），而 ``GraphEventForwarder`` 的 0.1s 窗只合并**发送**、
#: 不合并构建。12–200 项的 foreach 若每项迁移都构建一帧，O(项数 × 图规模) 全压在
#: 事件循环上——所以限频必须落在调度器侧。窗内只发首帧，窗末补一帧保证不丢尾态。
_ITEM_FRAME_WINDOW_S = 0.1

#: 成本归因摘要的四维（D7/Q16）。
_ATTRIBUTION_DIMS = ("by_workflow", "by_node", "by_depth", "by_edge")
#: 每维回给父 agent 的 top-k（D7：不整表返回，与 C3 的 bounded envelope 同口径）。
_ATTRIBUTION_TOP_K = 5


class GraphRecursionError(RuntimeError):
    """图级步数/节点数/run 数超限（D6 Q5）。模型看到的是 envelope，不是异常文本。"""

    def __init__(
        self,
        *,
        steps: int,
        limit: int,
        current_nodes: list[str],
        message: str,
        reason: str = "recursion_limit",
    ) -> None:
        super().__init__(message)
        self.steps = steps
        self.limit = limit
        self.current_nodes = current_nodes
        self.reason = reason

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "message": str(self),
            "steps": self.steps,
            # 两个键同值：``limit`` 是异常自身的口径，``recursion_limit`` 是
            # envelope 诊断的口径（Q8 要求模型看到 recursion_limit）。
            "limit": self.limit,
            "recursion_limit": self.limit,
            "current_nodes": list(self.current_nodes),
        }


@dataclass
class _ItemRunSlot:
    """foreach 展开项的 run 身份槽（index → 身份），见 ``NodeState.item_runs``。

    ``_launch_run`` 的 ``reuse_state`` 只需要 ``subagent_id``/``run_id`` 两个可写
    字段。展开项借它把「index → 本项 run」在**派发那一刻**记下来——这是
    ``items_running`` 能区分「排队等 slot」与「真正在跑」的唯一依据（G7）：
    ``state.subagent_ids`` 是 gather 之后才 append 的稀疏数组，且顺序 ≠ item 序号。

    ``on_dispatch`` 让 ``_launch_run`` 在 run 身份落定后回调调度器补一帧项级进度
    （M2.3）；不设时纯记账。
    """

    subagent_id: str | None = None
    run_id: str | None = None
    on_dispatch: Callable[[], None] | None = None
    #: 本项 run 的失败步骤数（三态：``None`` = 无可用 trace / ``0`` = 已检查、零失败 /
    #: ``N`` = N 条失败）。与 ``NodeState.failure_count`` 同口径，由 ``_launch_run``
    #: 的同一处埋点写入。
    #:
    #: **当前无生产读取方**：容器快照读的是 ``NodeState.failure_count``（容器自身没有
    #: 单一 run，故恒为 ``None``），容器级线索由既有的 ``items_failed`` 承担。本字段
    #: 目前只被测试消费，为 #202（运行内事件流）的项级线索预留——不是「已接线」。
    failure_count: int | None = None


@dataclass
class NodeState:
    """调度器的节点状态（``WorkflowNode`` 的运行时投影）。"""

    node: WorkflowNode
    status: str = "pending"
    subagent_id: str | None = None
    subagent_ids: list[str] = field(default_factory=list)
    run_id: str | None = None
    run_ids: list[str] = field(default_factory=list)
    runs: int = 0
    summary: str = ""
    reason: str | None = None
    #: 结果槽（aggregate/foreach 的合并输入，以及节点的写槽）
    slots: dict[str, str] = field(default_factory=dict)
    started_at: float | None = None
    finished_at: float | None = None
    #: 未消费的 route 控制激活数（>0 才允许派发「只有控制入边」的节点）
    activations: int = 0
    #: best_effort 的等待时钟起点（第一条上游臂派发时刻）
    deadline_ref: float | None = None
    deadline_fired: bool = False
    verdict: str | None = None
    raw: str | None = None
    targets: list[str] = field(default_factory=list)
    items: int | None = None
    error: str | None = None
    #: foreach 的 per-item 状态（index → 状态），长度 = ``items``。G7：这是
    #: 「N 项里几个在跑/几个排队」的权威来源，也是 D5.2 堆叠条的数据源。
    item_states: list[str] = field(default_factory=list)
    #: foreach 的 per-item run 身份（index → :class:`_ItemRunSlot`）。
    item_runs: list[_ItemRunSlot] = field(default_factory=list)
    #: foreach 的项级计数（M2.1：计数点在每项**完成**那一刻的 done 回调上）。
    items_completed: int = 0
    items_failed: int = 0
    #: 本节点 run 的失败步骤数，**三态**（change fix-issue-215 的 Q6 方案 D）：
    #: ``None`` = 没有可用 trace（未派发 / 排队被拒 / trace 为空），**不显示**；
    #: ``0`` = 已检查、零失败（正向声明）；``N`` = N 条失败。
    #: ``None`` 与 ``0`` 不得折叠——前者是「没数据」，后者是「检查过、没事」。
    failure_count: int | None = None

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {
            "id": self.node.id,
            "kind": self.node.kind,
            "status": self.status,
            "runs": self.runs,
            "subagent_id": self.subagent_id,
            "summary": self.summary[:_SUMMARY_LIMIT],
            "reason": self.reason,
        }
        if self.subagent_ids:
            payload["subagent_ids"] = list(self.subagent_ids)
        if self.items is not None:
            payload["items"] = self.items
        if self.slots:
            # bounded envelope（D3）：collect aggregate 的槽是 N 份上游 concat 后的
            # 巨型字符串，整段进 envelope 就等于把父上下文打爆——槽值同样要裁剪。
            payload["slots"] = {
                slot: value[:_SUMMARY_LIMIT] for slot, value in self.slots.items()
            }
        if self.node.kind == "route":
            payload["verdict"] = self.verdict
            payload["raw"] = self.raw
            payload["targets"] = list(self.targets)
        if self.error:
            payload["error"] = self.error
        return payload


# --- 纯函数 helper（受测试直接覆盖） ---------------------------------------


def aggregate_slots(values: list[str], reducer: str) -> str:
    """按受限 reducer 枚举合并同一槽的多份贡献（D5：不执行模型生成代码）。"""
    if reducer not in REDUCERS:
        raise WorkflowValidationError(
            f"reducer {reducer!r} is not allowed; allowed: {list(REDUCERS)}"
        )
    texts = [value for value in values if value is not None]
    if reducer == "concat":
        return "\n".join(text for text in texts if text)
    if reducer == "first_non_empty":
        for text in texts:
            if text:
                return text
        return ""
    if reducer == "last":
        for text in reversed(texts):
            if text is not None:
                return text
        return ""
    # merge_dict：解析 JSON 对象后浅合并，非对象贡献被跳过。
    merged: dict[str, Any] = {}
    for text in texts:
        parsed = _maybe_json(text)
        if isinstance(parsed, Mapping):
            merged.update(parsed)
    return json.dumps(merged, ensure_ascii=False)


def matches_route(verdict: str, label: str) -> bool:
    """结构化标签匹配：标签必须出现在**某一行行首**（大小写无关），不做表达式求值。

    用行首匹配而非子串包含：reviewer 写「NOT APPROVED」时，子串判定会命中
    `APPROVED` 分支并让 review 循环提前终止（building-review Issue 7）。
    """
    if not verdict or not label:
        return False
    expected = label.strip().upper()
    if not expected:
        return False
    for line in verdict.upper().splitlines():
        stripped = line.lstrip()
        if stripped.startswith(expected):
            return True
    return False


def extract_collection(value: Any, field_name: str | None) -> list[Any]:
    """从上游产出里取 foreach 的展开集合（Q4：只会解析，不执行代码）。"""
    if field_name is not None:
        parsed = _maybe_json(value) if isinstance(value, str) else value
        value = parsed.get(field_name) if isinstance(parsed, Mapping) else None
    elif isinstance(value, str):
        parsed = _maybe_json(value)
        if parsed is not None:
            value = parsed

    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in ("items", "results", "tasks", "list"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return list(candidate)
        return [value]
    if isinstance(value, str):
        lines = [line for line in value.splitlines() if line.strip()]
        return lines or [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def render_item_task(template: str, item: Any, *, index: int | None = None) -> str:
    """把 ``{item}`` / ``{index}`` / 字典字段占位符替换成具体的展开项。"""
    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    if isinstance(item, Mapping) and "name" in item and isinstance(item["name"], str):
        text = item["name"]
    rendered = template.replace("{item}", text)
    if index is not None:
        rendered = rendered.replace("{index}", str(index))
    if isinstance(item, Mapping):
        for key, value in item.items():
            rendered = rendered.replace("{" + str(key) + "}", str(value))
    return rendered


#: 父投影里保留的节点字段：都是 O(1) 的标量/短列表。
_PARENT_NODE_FIELDS = ("id", "kind", "status", "runs", "subagent_id", "items")
#: 父投影里保留但必须裁剪的文本字段。
_PARENT_NODE_TEXT_FIELDS = ("summary", "reason", "error")


def _bounded_node(node: dict) -> dict:
    """把一个节点摘要投影成父 agent 面向的有界版本（Issue 4）。

    丢弃随图规模线性增长的数组（``subagent_ids``/``run_ids``/``slots``/``targets``/
    ``raw``）；文本字段裁到 ``_PARENT_FIELD_LIMIT``。
    """
    projected: dict[str, Any] = {
        key: node[key] for key in _PARENT_NODE_FIELDS if key in node
    }
    for key in _PARENT_NODE_TEXT_FIELDS:
        value = node.get(key)
        if not value:
            continue
        projected[key] = value[:_PARENT_FIELD_LIMIT]
    if node.get("reason") is None and "reason" in node:
        projected["reason"] = None
    return projected


def _budget_config(config: "AsterwyndConfig | None") -> object | None:
    """从配置里取 ``subagents.workflow.budget``（缺失时返回 None 用默认值）。

    与 ``WorkflowScheduler._aggregation_config`` 同款**防御式**读取：测试里
    ``SubAgentManager`` 常以 ``config=None`` 构造，链路上任何一环缺失都不能抛。
    """
    workflow = getattr(getattr(config, "subagents", None), "workflow", None)
    return getattr(workflow, "budget", None)


def _first_non_empty_line(text: str) -> str:
    """事件预览取**首个非空行**（Q5：不承诺「一句话」，只保证确定性的短预览）。"""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return value


# --- 调度器 -----------------------------------------------------------------


class WorkflowScheduler:
    """一张 WorkflowSpec 的一次运行（一个 workflow run = 一个执行实例）。"""

    def __init__(
        self,
        manager: "SubAgentManager",
        *,
        bus: MessageBus | None = None,
        workflow_id: str | None = None,
    ) -> None:
        self.manager = manager
        self.workflow_id = workflow_id or f"wf_{uuid.uuid4().hex[:8]}"
        self.bus = bus
        self._spec: WorkflowSpec | None = None
        self._plan: ExecutionPlan | None = None
        self._states: dict[str, NodeState] = {}
        #: 最近 5 次**终态迁移事件**（Q5）：ring buffer，同节点重跑可再次出现。
        self._latest_events: deque[dict] = deque(maxlen=_LATEST_EVENTS_LIMIT)
        self._store: WorkflowStore | None = None
        self._root_result_ref: str | None = None
        #: workflow 级汇聚器（D5）：复用 summarizer 抽象做 bounded formatter。
        #: LLM 可用时用它做语义压缩，否则退回 TruncationSummarizer（仍有界）。
        self._aggregator = WorkflowAggregator(
            summarizer=self._build_summarizer()
        )
        self._cancelled = False
        self._cancel_event = asyncio.Event()
        self._progress = asyncio.Event()
        self._steps = 0
        self._runs = 0
        self._expanded_nodes = 0
        #: foreach node_id -> 已计费的展开项数（review Issue 3：再展开只扣增量）。
        self._charged_expansions: dict[str, int] = {}
        self._in_flight_runs = 0
        self._in_flight_nodes = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._route_counts: dict[str, int] = {}
        self._run_refs: list[Any] = []
        #: 编排质量指标的 run 级记账（change ``benchmark-workflow-replay``，D4/Q2）：
        #: 被下游真正读走产出的 run id 集合（``_collect_slots``/``_node_task_text``/
        #: ``_write_root_result`` 打标）。冗余度的分子就是它的基数——没有它就只能退
        #: 回「有出边即有用」的结构口径，答不出「冗余」（Q2 口径 A 的问题）。
        self._consumed_run_ids: set[str] = set()
        #: 被下游读走产出的**边**集合（change ``workflow-graph-visualization``，
        #: grill Q5）：边状态 ``passed`` 的一档查表源。记 ``(source, target)`` 而不是
        #: run id——同一节点的两条出边无法用 run 级记账区分。
        #:
        #: **旁新增**（决策 11/12）：只在三个消费循环的 ``_mark_consumed`` 调用点旁
        #: 顺手 ``add``，``_mark_consumed`` 本体一行不改——``_consumed_run_ids`` 的
        #: 基数因此逐位不变，C5 的 ``useful_runs``/``redundancy`` 零漂移。第四个调用点
        #: （``_write_root_result``）遍历的是终态节点、没有 ``edge`` 变量，不覆盖。
        self._consumed_edges: set[tuple[str, str]] = set()
        #: 拒绝/降级计数（Q3/Q4）：queue_full 与图级超限在调度器侧落账；深度撤工具与
        #: spawn 预算拒绝由 manager 的计数器提供（``rejection_counts_for``）。
        self._queue_full_runs = 0
        self._graph_recursion_runs = 0
        #: run() finally 释放 spawn 桶之前取下的快照（Q2/Confirmed Decision 7）：
        #: 释放后 ``manager.spawn_count()`` 会退化成 manager 生命周期计数，口径不同。
        self._spawn_count_snapshot: int | None = None
        self._rejection_counts_snapshot: dict[str, int] = {}
        #: node_id -> 仍在跑的 (subagent_id, run_id)，取消路径据此找到 in-flight run
        self._live_runs: dict[str, list[tuple[str, str]]] = {}
        #: 项级推帧的限频状态（M2.3）：``_item_frame_pending`` = 窗内还有被合并掉的
        #: 迁移待补发；``_item_frame_last_at`` = 上一帧的单调时刻（``None`` = 无历史）。
        self._item_frame_pending = False
        self._item_frame_last_at: float | None = None
        self._peak_active = 0
        self._started_at = 0.0
        self._finished_at: float | None = None
        self._status = "declared"
        #: False 之后调度器不再接受新的派发/复位（取消或图级超限后）
        self._accepting = True
        #: 节点任务里抛出的图级闸门异常，由主循环冒泡成 envelope 诊断
        self._fatal_error: GraphRecursionError | None = None
        self._diagnostics: dict[str, Any] = {}
        self._cost_before = 0.0
        #: workflow 级四维度预算账本（D1/Q6 方案 B）：loop 层每次 LLM 调用累加
        #: token/cost，调度器在派发前预扣 runs 维度。``_budget_stop`` 是超限后的
        #: **粘性** stop_new 标志（D2）——``_accepting`` 今天不 gate 派发（决策 2），
        #: 所以必须另有一个被派发路径显式检查的闸。
        self._budget: WorkflowBudget | None = None
        self._budget_stop = False
        self._budget_dimension: str | None = None
        #: runs 预扣被拒时触发拒绝的累计值（实际未扣款，仅用于 envelope 口径自洽）。
        self._budget_projected_runs: int | None = None
        #: 四维归因摘要的落盘件 ref（D7/Q15：结算时一次性写，父按需 Read）。
        self._attribution_ref: str | None = None

    # -- 生命周期 -----------------------------------------------------------

    @property
    def started(self) -> bool:
        """``run()`` 是否已经开跑（``declared`` 态 = 只注册不执行）。

        C5 的 record 采集据此过滤：``DeclareWorkflow`` 只注册不执行，未启动的图
        不能进 ``workflows`` 列表，否则 replay 会重放出 record 时不存在的行为。
        """
        return self._status != "declared"

    @property
    def spec(self) -> WorkflowSpec | None:
        return self._spec

    @property
    def plan(self) -> ExecutionPlan | None:
        """当前执行计划（含自动插入层 + 预算档），未 attach 时为 ``None``。"""
        return self._plan

    @spec.setter
    def spec(self, value: WorkflowSpec) -> None:
        """Attach the parsed spec before ``StartWorkflow`` drives the graph (D1)."""
        self._spec = value
        self._plan = self._build_plan(value)
        self._states = {node.id: NodeState(node=node) for node in self._plan.nodes}
        self._expanded_nodes = len(self._plan.nodes)
        self._charged_expansions = {}

    def _build_plan(self, spec: WorkflowSpec) -> ExecutionPlan:
        """按 ``subagents.workflow.aggregation`` 配置构建执行计划（D2/D6/Q4）。"""
        return ExecutionPlan.build(
            spec,
            max_fan_in=self._aggregation_max_fan_in(),
            budgets=self._token_budgets(),
        )

    def _aggregation_config(self) -> Any:
        limits = getattr(getattr(self.manager.config, "subagents", None), "workflow", None)
        return getattr(limits, "aggregation", None)

    def _aggregation_max_fan_in(self) -> int:
        aggregation = self._aggregation_config()
        thresholds = getattr(aggregation, "thresholds", None)
        if thresholds is None:
            return MAX_FAN_IN
        return getattr(thresholds, "max_fan_in", MAX_FAN_IN)

    def _token_budgets(self) -> dict[str, int]:
        """四档 token 预算（leaf/shard/domain/root），配置缺失时用默认值。"""
        aggregation = self._aggregation_config()
        tiers = getattr(aggregation, "token_budgets", None)
        if tiers is None:
            return dict(DEFAULT_TOKEN_BUDGETS)
        return {
            "leaf": getattr(tiers, "leaf", DEFAULT_TOKEN_BUDGETS["leaf"]),
            "shard": getattr(tiers, "shard", DEFAULT_TOKEN_BUDGETS["shard"]),
            "domain": getattr(tiers, "domain", DEFAULT_TOKEN_BUDGETS["domain"]),
            "root": getattr(tiers, "root", DEFAULT_TOKEN_BUDGETS["root"]),
        }

    def _build_summarizer(self) -> Summarizer | None:
        """有 LLM 时用 ``LLMSummarizer``，否则 ``None`` 让 aggregator 用截断兜底。"""
        llm = getattr(self.manager, "llm", None)
        if llm is None:
            return None
        try:
            return LLMSummarizer(llm)
        except Exception:  # noqa: BLE001 - 汇聚器构造失败不该拖垮调度
            return None

    def _graph(self) -> ExecutionPlan:
        """运行期图结构（含自动插入层）——所有边/节点查询的唯一入口。"""
        assert self._plan is not None
        return self._plan

    def _workflow_store(self) -> WorkflowStore:
        if self._store is None:
            self._store = self.manager.workflow_store(self.workflow_id)
        return self._store

    # -- 事件（D4：权威状态进事件日志，bus 只做低延迟广播） -----------------

    def _record_event(
        self,
        event_type: str,
        *,
        node_id: str | None = None,
        status: str = "",
        summary: str = "",
        terminal: bool = False,
    ) -> None:
        """写一条权威事件：落盘事件日志（D4）+ 终态迁移进 ring buffer（Q5）。

        事件日志是**权威源**（结果完整性、重试、重放的依据）；MessageBus 丢消息
        不影响这里的记录，因此 bus 降级后 workflow 完成与结果正确性不受影响。

        ``latest_events`` 只收**终态迁移**（Q5：节点/工作流进入终态），非终态的
        生命周期事件（``workflow_started``）只进日志——否则小图里 5 格 ring buffer
        会被非终态事件挤满，父 agent 反而看不到「谁跑完了」。
        """
        event: dict[str, Any] = {"type": event_type, "status": status}
        if node_id is not None:
            event["node_id"] = node_id
            preview = _first_non_empty_line(summary)
            event["summary_preview"] = preview[:_EVENT_PREVIEW_LIMIT]
        if terminal:
            self._latest_events.append(event)
        try:
            self._workflow_store().append_event({**event, "workflow_id": self.workflow_id})
        except Exception:  # noqa: BLE001 - 事件日志是尽力而为的可观测性
            pass

    # -- 图事件出口（change ``workflow-graph-visualization``，Q1/Q3/Q11） ----

    def _emit_graph_event(self, event_type: str, data: dict) -> None:
        """把一条图事件交给 manager 级 sink（默认静默）。

        **调用 sink 永不抛**（Q11）：sink 内部吞异常是它的责任，但调度器不信赖
        这一点——这里再包一层，因为调用点全在**节点任务的调用栈里**
        （``_dispatch``/``_run_node``/``cancel``），漏出来的异常会被 ``_run_node``
        的 ``except Exception`` 吞成「节点 failed」——用户的图会因为关了个页面而失败。

        这条不可观测性通道**不得**反向影响执行（本 change 最隐蔽的耦合）。
        """
        sink = getattr(self.manager, "graph_sink", None)
        if sink is None:
            return
        try:
            sink(event_type, data)
        except Exception:  # noqa: BLE001 - 可观测性通道绝不打断执行（Q11）
            logger.debug("workflow graph sink raised; snapshot dropped", exc_info=True)

    def _emit_graph_snapshot(self) -> None:
        """推一帧完整快照（D4：发完整快照，不发局部 patch，保证可重放）。"""
        try:
            payload = self.workflow_graph_snapshot()
        except Exception:  # noqa: BLE001 - 快照构造失败同样不得打断执行
            logger.debug("workflow graph snapshot failed", exc_info=True)
            return
        self._emit_graph_event("workflow_snapshot", payload)

    def _emit_workflow_started(self) -> None:
        self._emit_graph_event(
            "workflow_started",
            {
                "workflow_id": self.workflow_id,
                "spec_hash": self._spec.spec_hash if self._spec else None,
                "goal": self._spec.goal if self._spec else "",
                "status": "running",
                "timestamp": time.time(),
            },
        )

    def cancel(self) -> dict:
        """Q8：立即返回「取消已提交」envelope（不 gather 等 in-flight 停下）。"""
        self._cancelled = True
        self._accepting = False
        self._cancel_event.set()
        for state in self._states.values():
            if state.status in ("queued", "started"):
                # 取消必须是**立即**的（Q8：不 gather 等 in-flight 停下）：
                # 这里同步标终态并取消底层 run，不等节点协程收尾。
                asyncio.ensure_future(self._cancel_node(state))
                state.status = "cancelled"
                state.reason = state.reason or "cancelled: workflow cancelled"
        # ``_status`` 只在图**真的跑过**时才落终态：``started`` property 就是
        # ``_status != "declared"``，而 C5 的 record 采集 / 指标投影（以及重连补发）
        # 都拿它当「这张图是否运行过」的判据。``DeclareWorkflow`` 的调度器停在
        # ``declared``，此时一条快照都没有——若在这里无条件改写 ``_status``，
        # 一张「只声明、从未 run()」的图会被 C5 记进 ``workflows`` 列表（record 的
        # ``spec``/``observed`` 全是空跑产物）。没有图可发时也不必发快照。
        if self._status != "declared":
            self._status = "cancelled"
            self._emit_graph_snapshot()
        self._progress.set()
        return {
            "workflow_id": self.workflow_id,
            "status": "cancelling",
            "message": "取消已提交；in-flight 的 run 会写下 checkpoint 供后续 resume",
        }

    def status(self) -> dict:
        """bounded 状态快照（Q8/低危项：节点级摘要裁剪，避免打爆父上下文）。"""
        return self._envelope(status=self._status)

    async def run(
        self,
        spec: WorkflowSpec,
        *,
        raise_on_recursion: bool = False,
    ) -> dict:
        self._spec = spec
        # 自动兜底在 parse 之后插入节点，所以执行计划（而非原 spec）是运行期权威
        # （grill 决策 6）；原始 spec 保持不变，其 spec_hash 仍是 replay 锚点。
        self._plan = self._build_plan(spec)
        self._states = {node.id: NodeState(node=node) for node in self._plan.nodes}
        self._expanded_nodes = len(self._plan.nodes)
        self._charged_expansions = {}
        self._status = "running"
        self._started_at = time.time()
        self._cost_before = self._ledger_total()
        # 四维度预算账本（D1）：一个 workflow run 一份，挂钟从创建起算（Q6）。
        self._budget = WorkflowBudget(_budget_config(self.manager.config))
        self._budget_stop = False
        self._budget_dimension = None
        self._budget_projected_runs = None
        self._consumed_run_ids = set()
        self._consumed_edges = set()
        self._queue_full_runs = 0
        self._graph_recursion_runs = 0
        self._spawn_count_snapshot = None
        self._rejection_counts_snapshot = {}
        bus = self.bus or MessageBus()
        self.bus = bus
        self._record_event("workflow_started", status="running")
        # 图事件触发点（决策 1/2）：就在已有的 ``_record_event("workflow_started")``
        # hook 处——工具层拿不到 session 事件 sink，而 ``run()`` 是唯一同时知道
        # 「图真的开跑了」和持有调度器状态的入口。``DeclareWorkflow`` 只注册不调
        # ``run()``，因此天然不发。
        self._emit_workflow_started()
        self._emit_graph_snapshot()
        # 幂等自注册：loop 层的预算记账（Q6 方案 B）按 ``current_workflow_id()`` 反查
        # 调度器，直接构造（不经 Declare/Start 工具）的调度器也必须在注册表里。
        self.manager.register_workflow(self)
        self.manager.register_workflow_bucket(self.workflow_id, spec.max_runs * 2)
        try:
            self._check_declared_limits(spec)
            await self._drive(raise_on_recursion=raise_on_recursion)
        except GraphRecursionError as exc:
            # 运行期复检（自动插入节点吃 max_nodes）：与主循环内触发的图级闸门
            # 走同一个 envelope 诊断出口（Q8：模型看到 envelope，不是异常文本）。
            await self._cancel_all_in_flight()
            self._mark_graph_recursion_exceeded(exc)
            if raise_on_recursion:
                raise
        except WorkflowBudgetExceeded as exc:
            # D1/Q4（审阅员修订）：预算超限**不得逃出 run()**——映射为
            # stop_new + drain + envelope，父 agent 拿到的是 envelope 而非异常。
            self._mark_budget_stop(exc.dimension)
        finally:
            await self._teardown()
            # 快照必须早于 ``release_workflow_bucket``（Q2/Confirmed Decision 7）：
            # 释放会 pop 掉 workflow 桶，之后 ``spawn_count()`` 在无 workflow 上下文的
            # 采集点会退化成 manager 生命周期计数——那是「整个任务的全部 spawn」。
            self._snapshot_spawn_accounting()
            self.manager.release_workflow_bucket(self.workflow_id)
            self._finished_at = time.time()
            self._write_root_result()
            # 归因快照在本 workflow 结算时**一次性**落盘（Q15）；父 agent 拿到的是
            # bounded 摘要 + ref，完整账单按需 Read（与 C3 的 result_ref 同口径）。
            self._write_attribution()
            self._record_event("workflow_terminal", status=self._status, terminal=True)
            self._emit_graph_snapshot()
        return self.status()

    def _snapshot_spawn_accounting(self) -> None:
        """把 workflow 桶的 spawn/拒绝计数快照进调度器（Q2/Q3）。

        ``manager.spawn_count_for`` 走显式 workflow_id，不依赖 contextvar——
        ``run()`` 的 finally 里调用上下文已随节点任务的收尾而清理。
        """
        manager = self.manager
        self._spawn_count_snapshot = int(manager.spawn_count_for(self.workflow_id))
        self._rejection_counts_snapshot = manager.rejection_counts_for(self.workflow_id)

    def _mark_consumed(self, state: "NodeState") -> None:
        """打标「该节点的 run 产出被下游读走」（Q2 消费口径）。

        一个节点可能有多次 run（route 回边重跑）或多次展开项（foreach），所以标记
        按 run id 记而不是按节点记。只加记账状态，不改执行流。
        """
        if state.run_id:
            self._consumed_run_ids.add(state.run_id)
        for run_id in state.run_ids:
            self._consumed_run_ids.add(run_id)

    def _mark_graph_recursion_exceeded(self, exc: GraphRecursionError) -> None:
        """图级闸门的**唯一**收敛出口（Q3 的「图级超限」计数落点）。

        ``_check_declared_limits``（``run()`` 路径）与 ``_drive`` 的内部捕获都会走到
        这里；计数幂等，避免同一次超限被记两次。
        """
        self._accepting = False
        self._diagnostics = exc.to_dict()
        self._status = "graph_recursion_exceeded"
        self._graph_recursion_runs = 1
        self._emit_graph_snapshot()

    def _check_declared_limits(self, spec: WorkflowSpec) -> None:
        """运行期记账复检（grill 决策 6）：自动插入的节点也要吃 ``max_nodes``。

        ``parse_workflow_spec`` 的 ``max_nodes`` 检查是**声明期**的（一次算完），
        自动兜底发生在 parse 之后。没有这道复检，用户配置的节点上限对自动插入的
        shard/domain 层完全失效——与 C2 grill Q5 的「max_nodes = 节点数（含 foreach
        展开）」口径直接矛盾。
        """
        if len(self._plan.nodes) > spec.max_nodes:
            raise GraphRecursionError(
                steps=0,
                limit=spec.max_nodes,
                current_nodes=[node.id for node in self._plan.nodes],
                reason="max_nodes",
                message=(
                    f"GraphRecursionError: workflow expands to {len(self._plan.nodes)} "
                    f"nodes (including {len(self._plan.inserted_nodes)} auto-inserted "
                    f"aggregate nodes), exceeding max_nodes {spec.max_nodes}"
                ),
            )

    async def _teardown(self) -> None:
        """取消/收尾所有仍在途的节点任务，并标记未派发节点为 blocked。

        Q5：预算超限时，**根节点**（``plan.terminal``，无下游数据边）若未完成则改
        ``budget_exceeded``，其余未派发节点仍是 ``blocked``；已完成的根节点不覆盖。
        """
        self._accepting = False
        for state in self._states.values():
            if state.status in ("queued", "started"):
                await self._cancel_node(state)
                if state.status in ("queued", "started"):
                    state.status = "cancelled"
        self._resolve_pending_nodes()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - teardown 吞掉
                pass
        self._tasks.clear()

    # -- 主循环 -------------------------------------------------------------

    async def _drive(self, *, raise_on_recursion: bool) -> None:
        spec = self._spec
        assert spec is not None
        try:
            while True:
                if self._cancelled:
                    self._status = "cancelled"
                    return
                # stop_new 显式闸（D2/决策 2）：``_accepting`` 今天只 gate 级联复位、
                # 不 gate 派发，所以预算超限必须在这里检查一次——否则预算超限后
                # 调度器会继续派发所有就绪节点，四维预算是空转的。
                if self._budget_stop and self._in_flight_nodes == 0:
                    self._status = "budget_exceeded"
                    return
                # 项级限频窗（M2.3）：被窗口合并掉的那一帧在这里补发。下一轮通常紧跟
                # 在项级迁移之后（``_progress.set()`` 唤醒主循环），所以尾帧不会因为
                # 「窗口内没有后续迁移」而丢。
                self._drain_item_frame()
                self._fire_best_effort_deadlines()
                ready = self._ready_nodes()
                dispatched = 0
                if ready:
                    if self._steps >= spec.recursion_limit:
                        raise GraphRecursionError(
                            steps=self._steps,
                            limit=spec.recursion_limit,
                            current_nodes=[state.node.id for state in ready],
                            reason="recursion_limit",
                            message=(
                                f"GraphRecursionError: workflow reached recursion_limit "
                                f"{spec.recursion_limit} supersteps; "
                                f"ready nodes: {[state.node.id for state in ready]}"
                            ),
                        )
                    for state in ready:
                        if self._dispatch(state):
                            dispatched += 1
                    if dispatched:
                        self._steps += 1
                if self._fatal_error is not None:
                    # 节点任务里触发的图级闸门（典型：foreach 展开预检）
                    raise self._fatal_error
                if dispatched == 0 and self._in_flight_nodes == 0:
                    # 没有可派发的节点、也没有在途节点：图已收敛（或存在不可达节点）。
                    # 预算超限是**粘性**状态（Q5）：收敛出口不得把它覆盖成 completed。
                    if self._budget_stop:
                        self._status = "budget_exceeded"
                    else:
                        # G26（D9）：有节点 ``failed`` 的图不得报 ``completed``——
                        # 否则用户根本不会被告知去看失败。用独立档区分，不让它
                        # 使整图算失败（其余节点可能都正常跑完了）。
                        self._status = self._terminal_converged_status()
                    return
                await self._wait_for_progress()
        except GraphRecursionError as exc:
            await self._cancel_all_in_flight()
            self._mark_graph_recursion_exceeded(exc)
            if raise_on_recursion:
                raise

    async def _wait_for_progress(self) -> None:
        """等一条推进信号（节点终态 / run 完成），但绝不无限期阻塞。

        ``best_effort`` 的截止时间是一条**没有事件源**的推进条件：到点前如果图里
        只剩阻塞的臂，主循环必须自己醒来才能触发取消。因此这里的等待上界取
        「最近的截止时间」与调度心跳的较小值。
        """
        tick = _POLL_INTERVAL_S
        deadline_in = self._next_deadline_in()
        if deadline_in is not None:
            tick = min(tick, max(deadline_in, 0.001))
        try:
            await asyncio.wait_for(self._progress.wait(), timeout=tick)
        except asyncio.TimeoutError:
            pass
        self._progress.clear()

    def _next_deadline_in(self) -> float | None:
        now = time.time()
        pending: list[float] = []
        for state in self._states.values():
            node = state.node
            if node.kind != "aggregate" or node.join != "best_effort":
                continue
            if state.status != "pending" or state.deadline_fired:
                continue
            if state.deadline_ref is None or node.deadline_s is None:
                continue
            pending.append(node.deadline_s - (now - state.deadline_ref))
        return min(pending) if pending else None

    async def _cancel_all_in_flight(self) -> None:
        for state in self._states.values():
            if state.status in ("queued", "started"):
                await self._cancel_node(state)
                if state.status in ("queued", "started"):
                    state.status = "cancelled"

    # -- 四维度预算（D1/D2） -------------------------------------------------

    def _check_budget_before_dispatch(self, state: NodeState, cost: int) -> None:
        """派发前判定四维度预算（Q4/Q6 方案 B）。

        顺序即语义：token/cost/wall_time 是「已完成调用的累计值」判定，runs 是预扣。
        任一超限都置 stop_new（drain 在跑、退掉 queued），并抛
        :class:`WorkflowBudgetExceeded` 走 ``_dispatch`` 的调用方收敛。异常由
        ``_run_node``/``_drive`` 的捕获路径映射成 envelope，绝不逃出 ``run()``。
        """
        budget = self._budget
        if budget is None:
            return
        # token/cost/wall_time 三维是「已完成调用的累计值」判定（Q6 方案 B）。
        self._raise_if_budget_exceeded(now=time.time())
        # runs 维度是**预扣**：用预扣后的累计值判定（复用 ``self._runs``，Q4）。
        self._enforce_c4_runs(self._runs + cost)

    def _enforce_c4_runs(self, projected: int) -> None:
        """C4 ``max_total_runs`` 的**唯一**预扣落点（Q4）。

        派发点（``_dispatch``）与 foreach 展开点（``_execute_foreach``）都必须走这里
        ——foreach 展开项经 ``_run_foreach_item`` 直接派发、**不经 ``_dispatch``**，
        只在 ``_dispatch`` 里查 C4 会让 foreach 完全绕过 runs 预算（building-review
        Round 2 回归：``max_total_runs=2`` 的图仍跑满 10 项且报 ``exceeded=False``）。

        ``projected`` 是**预扣后**的累计 run 数。超限判定委托给账本的
        :meth:`WorkflowBudget.reserve_runs`（上限语义与「0 = 不限」只在该处定义一次），
        调度器只负责把拒绝映射成 stop_new。C4 检查刻意先于 C2 结构闸——同值时由 C4
        触发 drain 语义，只有 C2 显式更小时才走 ``graph_recursion_exceeded``。
        """
        budget = self._budget
        if budget is None:
            return
        try:
            budget.reserve_runs(projected)
        except WorkflowBudgetExceeded:
            # 记下触发值：预扣被拒时实际未扣款，envelope 的 runs.used 要能自洽地
            # 展现「是哪个数触发的」（见 _budget_summary）。
            self._budget_projected_runs = projected
            self._mark_budget_stop("runs")
            raise

    def _raise_if_budget_exceeded(self, *, now: float | None = None) -> None:
        """四维预算超限判定 → 置 stop_new + 抛 ``WorkflowBudgetExceeded``。

        维度覆盖 ``exceeded_dimension`` 的全部返回集（含 ``"runs"``）——漏掉任一维
        都会在这里抛 ``KeyError`` 而不是预算异常，异常穿透 ``run()``，违反 spec
        Scenario「超限出口不逃出 run」（building-review Round 2 回归）。
        """
        budget = self._budget
        if budget is None:
            return
        dimension = budget.exceeded_dimension(runs=self._runs, now=now)
        if dimension is None:
            return
        self._mark_budget_stop(dimension)
        used, limit = {
            "tokens": (budget.tokens, budget.max_tokens),
            "cost_usd": (budget.cost_usd, budget.max_cost_usd),
            "runs": (self._runs, budget.max_runs),
            "wall_time_s": (budget.wall_time_s(now=now), budget.max_wall_time_s),
        }[dimension]
        raise WorkflowBudgetExceeded(dimension, used, limit)

    def _mark_budget_stop(self, dimension: str) -> None:
        """置粘性 stop_new 状态：不取消在跑 run、退掉 queued、让主循环 drain。

        D2：token/cost/wall_time 超限都**不取消**已启动的 run（只停止派发），所以
        这里只把仍在 ``queued`` 的节点标 cancelled，``started`` 的交回 ``_teardown``
        的 drain 路径。``_accepting`` 一并置 False，阻止节点收尾把下游从终态复活。
        """
        if self._budget_stop:
            return
        self._budget_stop = True
        self._budget_dimension = dimension
        self._accepting = False
        for state in self._states.values():
            if state.status == "queued":
                state.status = "cancelled"
                state.reason = f"budget exceeded ({dimension})"
        self._emit_graph_snapshot()

    def _expired_root_ids(self) -> set[str]:
        """根节点集合（``plan.terminal``，无下游数据边）；fan-out 图是多个。"""
        plan = self._plan
        if plan is None:
            return set()
        return set(plan.terminal)

    def _apply_budget_exhausted_status(
        self, state: NodeState, *, reason: str | None = None
    ) -> None:
        """预算停下时节点级状态的**唯一**落点（Q5）。

        - 根节点（``plan.terminal``）未完成 → ``budget_exceeded``；
        - 非根节点 → ``blocked``（仍由上游/收敛语义解释）。

        被预算抓到的节点有两类：仍在 ``pending``（``_teardown`` 路径）与已 ``started``
        但中途撞上预算（``_run_node`` 路径）。两条路径必须用**同一规则**，否则根节点
        在 ``_run_node`` 路径会被写成 ``blocked``、绕过 Q5 的 ``budget_exceeded``。

        ``reason`` 是非根 ``blocked`` 的备选说明（如 ``_run_node`` 传入异常文本）。
        """
        if state.node.id in self._expired_root_ids():
            state.status = "budget_exceeded"
            state.reason = f"budget exceeded ({self._budget_dimension or 'unknown'})"
        else:
            state.status = "blocked"
            state.reason = (
                state.reason
                or reason
                or "workflow ended before the node became ready"
            )

    def record_llm_usage(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """loop 层的每次 LLM 调用回调到这里（Q6 方案 B）。

        manager 通过当前 contextvar 的 workflow_id 找到本调度器再调进来；根 loop
        （无 workflow 身份）永远不会走到这里。
        """
        if self._budget is None:
            return
        self._budget.record_llm_call(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

    def _edge_for(self, node_id: str) -> str:
        """该节点这次 run 的 ``edge`` 归因键（D3/Q8，取值在派发点算出）。

        Q8 规则（用户确认）：

        - 多数据入边：按 source id **排序**拼接 ``a|b|c->join``（排序保证同一张图的
          两种等价声明序得到同一键，``by_edge`` 不会因声明序漂移）；
        - foreach 展开项：共享容器节点的数据入边（``planner->fan``）；
        - 入口节点（无数据入边）：``"<root>->node"``；
        - route 控制边触发的下游：``route->target``（控制激活优先——它是实际触发这次
          run 的来源，数据上游可能有多个或为空）。
        """
        plan = self._plan
        if plan is None:
            return f"<root>->{node_id}"
        control_sources = [
            edge.source
            for edge in plan.incoming(node_id)
            if plan.is_control_edge(edge)
        ]
        if control_sources:
            return f"{sorted(set(control_sources))[0]}->{node_id}"
        sources = sorted({edge.source for edge in plan.data_incoming(node_id)})
        if not sources:
            return f"<root>->{node_id}"
        return f"{'|'.join(sources)}->{node_id}"

    def _graph_distance_for(self, node_id: str) -> int:
        """该节点的 workflow 图距（0=leaf/1=shard/2=domain/3+=root，Q7/Q13）。

        复用 C3 ``_distances_from_leaf`` 的固定点迭代，与 ``budget_for_distance``
        同一口径——但**绝不写进 ``spawn_depth``**（那会连带影响 ``max_depth`` 闸）。
        """
        plan = self._plan
        if plan is None:
            return 0
        distance = _distances_from_leaf(
            plan.nodes, plan.edges, set(plan._control_sources)
        )
        return int(distance.get(node_id, 0))

    def _attribution_bill(self) -> dict | None:
        """本 workflow 的四维账单（未截断）；无 ledger 或读取失败时 ``None``。

        按 ``workflow_id`` 过滤（D7/Q15）：ledger 是跨 workflow 共享的，by_node/by_edge
        的键会跨图重名——不限定就把别的 workflow 的成本写进本图的 attribution。
        """
        ledger = getattr(self.manager, "cost_ledger", None)
        if ledger is None:
            return None
        try:
            return ledger.bill(workflow_id=self.workflow_id)
        except TypeError:
            # 兼容不支持作用域参数的 ledger 替身（测试注入的 stub）。
            return ledger.bill()
        except Exception:  # noqa: BLE001 - 归因是尽力而为的可观测性
            return None

    @staticmethod
    def _bucket_projection(bucket: dict) -> dict:
        return {
            "tokens": int(bucket.get("tokens", 0)),
            "cost": round(float(bucket.get("cost", 0.0)), 9),
            "estimated": bool(bucket.get("estimated", False)),
        }

    def _attribution_summary(self) -> dict:
        """四维账单的 **bounded** 摘要（D7/Q15/Q16）——回给父 agent 的那一份。

        每维只回 top-``_ATTRIBUTION_TOP_K``（按 cost 降序）——整表返回（100 节点的
        ``by_node``）会撑爆父上下文，与 C3 的 bounded envelope 同口径。**完整账单**
        走 ``attribution_ref`` 落盘件（见 :meth:`_attribution_full`）。
        """
        bill = self._attribution_bill()
        if bill is None:
            return {dim: {} for dim in _ATTRIBUTION_DIMS}
        summary: dict[str, Any] = {}
        counts: dict[str, int] = {}
        for dim in _ATTRIBUTION_DIMS:
            buckets = bill.get(dim) or {}
            top = sorted(
                buckets.items(), key=lambda item: item[1].get("cost", 0.0), reverse=True
            )[:_ATTRIBUTION_TOP_K]
            summary[dim] = {
                key: self._bucket_projection(bucket) for key, bucket in top
            }
            # 桶总数与被截断的条数显式报告（不静默截断，与 C3 的 nodes_omitted 同口径）。
            counts[f"{dim}_total"] = len(buckets)
            counts[f"{dim}_omitted"] = max(len(buckets) - _ATTRIBUTION_TOP_K, 0)
        summary["counts"] = counts
        return summary

    def _attribution_full(self) -> dict:
        """四维账单的**完整**快照（不截断）——落盘给 ``attribution_ref`` 的那一份。

        D7/Q15 的口径是「envelope 只给 bounded 摘要，完整归因走 result_ref 让父按需
        inspect」。这里必须与 :meth:`_attribution_summary` 取**不同**的投影：若两者都
        截断到 top-k，``attribution_ref`` 就只是同一份摘要的副本，父 agent 永远拿不到
        被省略的节点/边（building-review Round 2 回归）。
        """
        bill = self._attribution_bill()
        if bill is None:
            return {dim: {} for dim in _ATTRIBUTION_DIMS}
        return {
            dim: {
                key: self._bucket_projection(bucket)
                for key, bucket in (bill.get(dim) or {}).items()
            }
            for dim in _ATTRIBUTION_DIMS
        }

    def _write_attribution(self) -> None:
        """结算时一次性落盘**完整**账单，并记录 ``_attribution_ref``（D7/Q15）。

        落盘的是 :meth:`_attribution_full`（不截断），envelope 里的是 top-k 摘要——
        ``attribution_ref`` 必须能取回被摘要省略的节点/边。落盘失败不影响 workflow
        完成（与 ``_write_root_result`` 同口径：尽力而为的可观测性）。
        """
        attribution = self._attribution_full()
        if not any(attribution.get(dim) for dim in _ATTRIBUTION_DIMS):
            return
        try:
            self._attribution_ref = self._workflow_store().save_attribution(
                self.workflow_id, attribution
            )
        except Exception:  # noqa: BLE001 - 落盘失败不改变 workflow 结果
            logger.warning("Failed to persist workflow attribution", exc_info=True)

    def _budget_summary(self) -> dict:
        """``status()``/``_envelope`` 的 ``budget`` 块（D7）。

        runs 维度报的是**预扣后**的累计值（Q4：它与 C2 的结构闸共用 ``self._runs``）。
        预扣被拒时实际没有扣款，``self._runs`` 会小于触发值——直接报它会出现
        ``exceeded=true`` 而 ``used < limit`` 的自相矛盾（foreach 一次预扣 10 项、
        上限 3 时最明显）。所以取「实际累计」与「触发拒绝的预扣值」的较大者，
        让 envelope 与 ``WorkflowBudgetExceeded.used`` 口径一致。
        """
        budget = self._budget
        if budget is None:
            return {}
        runs_used = self._runs
        if self._budget_dimension == "runs" and self._budget_projected_runs is not None:
            runs_used = max(runs_used, self._budget_projected_runs)
        return {
            "dimensions": budget.dimensions(runs=runs_used),
            "exceeded": self._budget_stop,
            "exceeded_dimension": self._budget_dimension,
        }

    # -- 就绪与派发 ---------------------------------------------------------

    def _data_deps_satisfied(self, state: NodeState) -> bool:
        for edge in self._graph().data_incoming(state.node.id):
            if not edge.required:
                continue
            upstream = self._states.get(edge.source)
            if upstream is None or upstream.status not in TERMINAL_NODE_STATUSES:
                return False
        return True

    def _has_control_incoming(self, node_id: str) -> bool:
        plan = self._graph()
        return any(plan.is_control_edge(edge) for edge in plan.incoming(node_id))

    def _terminal_converged_status(self) -> str:
        """图收敛时的终态四档（G26/D9 + change ``workflow-terminal-honesty``）。

        判据按**实际执行结果**（优先级即语义，先命中先返回）：

        1. ``completed > 0`` 且 ``failed > 0`` → ``completed_with_failures``
        2. ``completed > 0`` 且 ``failed == 0`` → ``completed``
        3. ``completed == 0`` 且 ``failed > 0`` → ``failed``
        4. ``completed == 0`` 且 ``failed == 0`` → ``stalled``（图根本没跑起来）

        与 ``completed`` 分开是**用户可见**的：混用会让一张有失败节点的图在
        tab 上显示「已完成」，用户根本不会去看哪里失败了。

        第 4 档（``stalled``）修的是同一件事的更强形式（#217）：**零节点成功**的图
        也不得报 ``completed``——「无成功却说成功」比「有失败却说成功」更糟，用户
        连排查方向都没有。不并入 ``failed`` 是因为本项目 ``failed`` 已被「节点执行
        失败」占用（``completed_with_failures`` 依赖它），混用会让「有节点失败」与
        「图没跑起来」不可分辨，而两者对用户的行动指引完全不同。

        ``completed`` 的计数口径是 ``status == "completed"`` 的**节点**数，**不含**
        ``skipped``（未选中 ≠ 跑成功）。它**不是**快照的 ``completed`` 计数——后者
        来自 ``_unit_counts()['completed_units']``（``_logical_units`` 口径，foreach
        容器按展开项数计），二者不同源，不得混用。

        调用方保证本方法只在 ``self._budget_stop`` 为假的 else 分支里被调用，所以
        ``budget_exceeded`` / ``cancelled`` / ``graph_recursion_exceeded`` 天然优先。
        """
        states = list(self._states.values())
        completed = sum(1 for state in states if state.status == "completed")
        failed = sum(1 for state in states if state.status == "failed")
        if completed > 0 and failed > 0:
            return "completed_with_failures"
        if completed > 0:
            return "completed"
        if failed > 0:
            return "failed"
        return "stalled"

    def _resolve_pending_nodes(self) -> None:
        """把所有未派发节点落成终态，**上游先定**（D2b）。

        逐轮扫，每轮只判「入边源头都已离开 ``pending``」的节点；一轮下来没有任何
        进展说明剩下的在互相等待——那是 route 回边（环）里的节点，此时按既有规则
        一次性落定（环内谁先谁后本就无解，取稳定的声明序）。
        """
        pending = [s for s in self._states.values() if s.status == "pending"]
        while pending:
            progressed = False
            for state in list(pending):
                if not self._upstreams_resolved(state):
                    continue
                self._resolve_pending_status(state)
                pending.remove(state)
                progressed = True
            if not progressed:
                for state in pending:
                    self._resolve_pending_status(state)
                return

    def _upstreams_resolved(self, state: NodeState) -> bool:
        """该节点的**全部入边源头**是否都已离开 ``pending``。

        收尾判定必须自**上游先定**，否则同一个节点会因为「上游先被标了 blocked」
        还是「上游还是 pending」而给出不同答案。而 ``blocked`` 上游这一支恰恰是
        spec 明确要求「连累优先」的（第三条 Scenario 把 ``blocked`` 与
        ``failed``/``cancelled`` 并列）——就地判会把「被连累」报成「条件没选它」，
        用户读到的是**假话**。
        """
        plan = self._graph()
        for edge in plan.incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is not None and upstream.status == "pending":
                return False
        return True

    def _resolve_pending_status(self, state: NodeState) -> None:
        """一个未派发节点的终态落点（``_teardown`` 的唯一出口）。

        顺序是语义的一部分：``skipped`` **必须先于**预算分支，否则被 route 门控的
        根节点在预算停时会被写成 ``budget_exceeded``。
        """
        if self._is_skipped(state):
            state.status = "skipped"
            state.reason = "route did not select this branch"
        elif self._budget_stop:
            self._apply_budget_exhausted_status(state)
        else:
            state.status = "blocked"
            state.reason = state.reason or self._blocked_reason(state)

    def _blocked_reason(self, state: NodeState) -> str:
        """``blocked`` 节点的因由——按**真实成因**分档（#218，D3）。

        兜底句 ``workflow ended before the node became ready`` 读起来像「被动受牵连、
        外部原因」，而真实成因至少有两类，用户按兜底句排查会找错方向：

        1. **图级闸门触发**（``max_routes`` / ``recursion_limit`` / ``max_nodes`` /
           ``max_runs``）：真因在 ``self._diagnostics`` 里（形如
           ``GraphRecursionError: route node 'gate' exceeded max_routes 2``），
           必须**穿透**到节点因由，否则用户只在图级诊断里才看得到。
        2. **入边互相等待**（无任何图级闸门、``diagnostics`` 为空）：节点因入边
           永远不就绪而未派发——这是**结构性**原因，不是「工作流提前结束」。

        文案按**前端展示预算**压缩（见 :data:`_REASON_DISPLAY_LIMIT`）：闸门细节取
        ``_gate_detail()``（结构化上限值优先），互等档按 :data:`_WAITING_LIST_LIMIT`
        限制列出的上游数——两档都保证整句落在用户可见的那 160 字符内。

        **闸门判定看 ``reason`` 键是否存在，不看 ``_diagnostics`` 是否非空**：
        ``_diagnostics`` 也会被**非闸门**诊断填充（典型：``route_ref_misses``，
        即 ``$ref`` 槽未命中这类良性记录）。用「非空」判会把一次 ``$ref`` 未命中
        说成「图级闸门触发」——又是一句指错方向的假话（正是本 change 要消灭的
        那类）。闸门诊断的唯一写入点是 ``_mark_graph_recursion_exceeded``，它**必带**
        ``reason`` 键。

        **「入边互等」只在图**自然收敛**时才是真因**（用户取消 / 预算停是更强的
        停止原因，见 D1 的既有口径）。图被取消时节点没就绪是因为**用户停下了它**，
        链上根本没有环；此时说「永远未就绪」同样是指错方向的假话。故取消态直接
        走兜底句——前端 ``GRAPH_STOP_REASONS`` 会把它渲染成「流程被取消」。
        """
        if self._cancelled:
            return "workflow cancelled before the node became ready"
        reason = str(self._diagnostics.get("reason") or "").strip()
        if reason:
            return f"图级闸门 {reason} 触发（{self._gate_detail()}），本节点未派发"
        waiting = self._waiting_upstreams(state)
        if waiting:
            return self._waiting_reason(waiting)
        return "workflow ended before the node became ready"

    def _waiting_reason(self, waiting: list[str]) -> str:
        """「入边互相等待」因由——**整句**有界（上游 id 的长度与数量都不可控）。

        先按 :data:`_WAITING_LIST_LIMIT` 限数量，再按 :data:`_REASON_DISPLAY_LIMIT`
        限**整句长度**（截 id 列表中段、**保留后缀**「本节点永远未就绪」）。只限数量
        不够：3 个 60 字符的 id 就会把整句推到 207 字符，前端在 160 处会把后缀连同
        右括号一起切掉，用户看到的是半句断话。
        """
        prefix = "入边互相等待（"
        suffix = "），本节点永远未就绪"
        more = len(waiting) > _WAITING_LIST_LIMIT
        joined = ", ".join(waiting[:_WAITING_LIST_LIMIT])
        room = _REASON_DISPLAY_LIMIT - len(prefix) - len(suffix) - 1  # -1 给省略号
        if len(joined) > room:
            joined = joined[: max(room - 1, 1)].rstrip(" ,") + "…"
        elif more:
            joined += "…"
        return prefix + joined + suffix

    def _gate_detail(self) -> str:
        """图级闸门的**结构化**细节（bounded），供注入节点因由。

        优先取 ``limit``（闸门上限值，人话最短且信息量最高：``超过上限 2``）；
        无 ``limit`` 时退回**截断到展示预算**的 ``message``——截断在此处做，
        而不是让整段异常文本流到前端再被切掉尾巴。
        """
        limit = self._diagnostics.get("limit")
        if limit is not None and str(limit).strip():
            return f"超过上限 {limit}"
        message = str(self._diagnostics.get("message") or "").strip()
        if not message:
            return "无附加信息"
        # 给「图级闸门 … 触发（」+「），本节点未派发」留出余量。
        budget = max(_REASON_DISPLAY_LIMIT - 48, 1)
        return message[:budget]

    def _waiting_upstreams(self, state: NodeState) -> list[str]:
        """该节点的入边源头中**永远未就绪**的那些（``blocked`` / ``skipped`` / 未定）。

        只列「没成功」的源头：``completed`` 的源头说明这条边送过数据、不是互等的
        成因；``failed`` / ``cancelled`` 已有自己的语义（被连累），不在互等之列。
        返回稳定顺序（声明序）便于测试与阅读。
        """
        plan = self._graph()
        waiting: list[str] = []
        for edge in plan.incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            if upstream.status in ("blocked", "pending", "skipped"):
                if edge.source not in waiting:
                    waiting.append(edge.source)
        return waiting

    def _is_skipped(self, state: NodeState) -> bool:
        """未被 route 选中的节点（D2b，enhance-workflow-graph-ux）。

        四个条件**同时**成立才算 ``skipped``：

        1. 有控制入边（只被 route 门控的节点才是「未选中」的候选）；
        2. ``activations <= 0``（控制激活信号为负）；
        3. **每条控制入边的源头 route 都已 ``completed``**——「确实做过判定，
           且没选它」。缺了它，``route 从未运行``（例如它的数据依赖永远没就绪）
           会被误报成「条件没走这条」——**用户读到的是假话**；
        4. **已完成控制源本次选中的出口不含本节点**（``node_id not in source.targets``）
           ——（#220，方案 D）。``activations`` 会被子树复位（``_reset_subtree``）
           清零，而回边场景下 route 可能**已经选中并派发过**本节点；只凭条件 2
           会把「选过、也跑过」的节点报成 ``route did not select this branch``，
           又是一句假话。``targets`` 是权威信号：它受发起者豁免保护、不被回边复位
           清空，且已是 route 选中出口的对外契约。

        条件 3 与「被连累优先」是同一件事的两面：控制源没 completed（不管是
        ``blocked``/``skipped`` 还是仍在 pending），说明「选没选它」这件事**没有
        发生过**，真因在上游。调用方保证本方法在**上游已定**之后才被调用
        （``_upstreams_resolved`` 的迭代），所以这里看到的是终态而不是中间态。
        """
        node_id = state.node.id
        if not self._has_control_incoming(node_id):
            return False
        if state.activations > 0:
            return False
        plan = self._graph()
        for edge in plan.incoming(node_id):
            if not plan.is_control_edge(edge):
                continue
            source = self._states.get(edge.source)
            if source is None or source.status != "completed":
                return False
            # 条件 4：控制源确实选中了本节点 → 不是「未选中」，别报 skipped。
            if node_id in source.targets:
                return False
        # 数据上游被连累（failed/cancelled/blocked 都由上游先定后再看）：
        # 「被连累」优先于「未选中」——即使 route 选了它，它也拿不到输入。
        for edge in plan.data_incoming(node_id):
            if not edge.required:
                continue
            upstream = self._states.get(edge.source)
            if upstream is not None and upstream.status in _DOOMED_UPSTREAM_STATUSES:
                return False
        return True

    def _ready_nodes(self) -> list[NodeState]:
        ready: list[NodeState] = []
        for state in self._states.values():
            if state.status != "pending":
                continue
            if not self._data_deps_satisfied(state):
                continue
            if state.deadline_fired:
                ready.append(state)
                continue
            if (
                not self._is_entry(state.node.id)
                and self._has_control_incoming(state.node.id)
                and state.activations <= 0
            ):
                # 回边目标节点要等 route 的激活才允许重跑；但它仍受数据门控约束
                # （例如 join 只在所有臂终态、且任一臂激活它时才跑）。
                continue
            ready.append(state)
        return ready

    def _is_entry(self, node_id: str) -> bool:
        plan = self._plan
        return bool(plan is not None and node_id in plan.entry)

    def _dispatch_capacity(self) -> int:
        return self.manager.max_active + self.manager.max_queued_runs

    def _run_cost(self, node: WorkflowNode) -> int:
        if node.kind == "subagent":
            return 1
        if node.kind == "aggregate":
            return 1 if node.strategy == "llm" else 0
        if node.kind == "foreach":
            return 0  # 展开项在节点任务内自行按背压逐个派发
        return 0  # route 是纯逻辑节点

    def _dispatch(self, state: NodeState) -> bool:
        """派发一个就绪节点；容量不足时返回 False（留在 ready 集合等槽位，Q2）。"""
        spec = self._spec
        assert spec is not None
        # 预算超限后的粘性闸（D2/决策 2）：``_accepting`` 不 gate 派发，所以这里必须
        # 显式拒绝。杀掉 queued 由 ``_mark_budget_stop`` 完成，这里只需不再派新的。
        if self._budget_stop:
            return False
        cost = self._run_cost(state.node)
        # C4 的运行期四维预算检查置于 C2 的结构闸**之前**（Q4）：同值 300 时由 C4
        # 触发 ``budget_exceeded``（drain 语义），只有 C2 显式更小时才走
        # ``graph_recursion_exceeded``。token/cost/wall_time 三维也在这里一并判定
        # ——foreach 展开项的预扣落在 ``_check_foreach_budget``，两处同源。
        #
        # 超限**不**让异常穿透 ``_drive``：转成「拒绝派发」（返回 False）后由主循环
        # 的 stop_new 闸收敛——这才满足 D2 的 drain 语义（在跑 run 跑完）。
        if cost:
            try:
                self._check_budget_before_dispatch(state, cost)
            except WorkflowBudgetExceeded:
                return False
        if self._runs + cost > spec.max_runs:
            raise GraphRecursionError(
                steps=self._steps,
                limit=spec.max_runs,
                current_nodes=[state.node.id],
                reason="max_runs",
                message=(
                    f"GraphRecursionError: workflow run budget exhausted "
                    f"({self._runs}/{spec.max_runs}); ready node {state.node.id!r}"
                ),
            )
        if cost and self._in_flight_runs + cost > self._dispatch_capacity():
            return False

        if state.node.kind == "route":
            if self._route_counts.get(state.node.id, 0) >= state.node.max_routes:
                raise GraphRecursionError(
                    steps=self._steps,
                    limit=state.node.max_routes,
                    current_nodes=[state.node.id],
                    reason="max_routes",
                    message=(
                        f"GraphRecursionError: route node {state.node.id!r} exceeded "
                        f"max_routes {state.node.max_routes}"
                    ),
                )

        state.status = "started"
        state.started_at = time.time()
        state.activations = 0
        self._runs += cost
        self._in_flight_runs += cost
        self._in_flight_nodes += 1
        # aggregate 的 best_effort 等待时钟从「第一条上游臂开始跑」起算（Q3）。
        for edge in self._graph().data_outgoing(state.node.id):
            successor = self._states.get(edge.target)
            if (
                successor is not None
                and successor.deadline_ref is None
                and successor.node.kind == "aggregate"
            ):
                successor.deadline_ref = time.time()
        task = asyncio.create_task(self._run_node(state))
        self._tasks.add(task)
        task.add_done_callback(lambda _task: self._progress.set())
        # 节点置 started 是一次真实迁移（D4 的迁移点之一），推一帧让前端看到「谁在跑」。
        self._emit_graph_snapshot()
        return True

    async def _run_node(self, state: NodeState) -> None:
        try:
            if state.node.kind == "subagent":
                await self._execute_subagent(state)
            elif state.node.kind == "foreach":
                await self._execute_foreach(state)
            elif state.node.kind == "aggregate":
                await self._execute_aggregate(state)
            else:
                await self._execute_route(state)
        except asyncio.CancelledError:
            state.status = "cancelled"
            raise
        except GraphRecursionError as exc:
            # 图级闸门（含 foreach 展开预检）：不能折叠成「节点失败」——它是整张图
            # 的终止条件，必须冒泡成 envelope 的 graph_recursion_exceeded。
            state.status = "failed"
            state.error = f"{type(exc).__name__}: {exc}"
            state.reason = state.reason or state.error
            self._fatal_error = self._fatal_error or exc
            self._accepting = False
        except WorkflowBudgetExceeded as exc:
            # 预算超限（D2）：不是节点失败——置粘性 stop_new，并按 Q5 的规则给节点
            # 终态（根节点 ``budget_exceeded``、其余 ``blocked``）。
            self._mark_budget_stop(exc.dimension)
            self._apply_budget_exhausted_status(state, reason=str(exc))
        except Exception as exc:  # noqa: BLE001 - 节点失败不 fail-fast（D4）
            state.status = "failed"
            state.error = f"{type(exc).__name__}: {exc}"
            state.reason = state.reason or state.error
        finally:
            if state.finished_at is None:
                state.finished_at = time.time()
            self._in_flight_nodes -= 1
            # 终态迁移事件（Q5）：同节点重跑会再次出现，因为它是一次新的迁移。
            if state.status in TERMINAL_NODE_STATUSES:
                self._record_event(
                    "node_terminal",
                    node_id=state.node.id,
                    status=state.status,
                    summary=state.summary or state.reason or "",
                    terminal=True,
                )
            self._on_node_finished(state)
            self._progress.set()
            # 节点终态是本 change 里信息量最大的一次迁移（谁跑完了、下游被复位）。
            self._emit_graph_snapshot()

    def _release(self, cost: int) -> None:
        self._in_flight_runs -= cost
        self._refresh_peak()
        self._progress.set()

    def _on_node_finished(self, state: NodeState) -> None:
        """节点终态后的收敛动作：级联复位下游数据节点 + 消费控制激活。"""
        if state.node.kind == "route":
            return
        if not self._accepting:
            # workflow 已取消/已超限：节点收尾不得把下游从终态复活（否则 blocked
            # 会被重新改回 pending，取消后的状态快照就自相矛盾）。
            return
        for edge in self._graph().data_outgoing(state.node.id):
            successor = self._states.get(edge.target)
            if successor is None:
                continue
            if successor.status in TERMINAL_NODE_STATUSES:
                self._reset_subtree(successor, origin=state.node.id)

    def _reset_subtree(self, state: NodeState, *, origin: str | None = None) -> None:
        """数据上游重跑 → 下游必须用新输入重跑（同一 session 复用）。

        G11（enhance-workflow-graph-ux）：复位必须**一并清上一轮的产出于因由**
        （``reason``/``error``/``summary``/``finished_at``），否则重跑期间前端
        会显示上一轮的失败因由（``state.reason = state.reason or ...`` 的 ``or``
        语义会把它留住），且 ``finished_at`` 不复位会让新 ``started_at`` 大于旧
        ``finished_at`` → **负耗时**。**答错比答不出更糟**，而 route 回边重跑
        （review 循环）是本项目的常见形态。

        ``origin`` 是**本次派发链的发起者**（#220，D4）：数据边回边（如
        ``body → cycle_gate``，``body`` 非 route）会让递归沿 ``data_outgoing``
        走回发起者自己，把它刚写完的 ``status``/``targets``/``summary`` 清空 ——
        成功被改写成未派发。豁免**只跳过 origin 一个节点**，不停止传播：环上其它
        节点仍须重跑（G11 的重跑语义）。**只加豁免，不减任何清理项。**
        """
        if origin is not None and state.node.id == origin:
            return
        if state.status == "pending":
            return
        state.status = "pending"
        state.activations = 0
        state.deadline_fired = False
        state.verdict = None
        state.targets = []
        state.reason = None
        state.error = None
        state.summary = ""
        state.finished_at = None
        # 失败计数也必须复位（fix-issue-215 审阅 R1）：它与 ``reason`` 属同一类
        # 「上一轮的失败痕迹」。不复位会让重跑期间前端显示**上一轮**的失败线索
        # （实测：``status=pending`` 配 ``failure_count=7``），而这一轮根本还没派发
        # ——正是本函数 docstring 说的「答错比答不出更糟」。
        state.failure_count = None
        for edge in self._graph().data_outgoing(state.node.id):
            successor = self._states.get(edge.target)
            if successor is not None:
                self._reset_subtree(successor, origin=origin)

    # -- 节点执行 -----------------------------------------------------------

    async def _execute_subagent(self, state: NodeState) -> None:
        node = state.node
        envelope = await self._launch_run(
            node=node,
            task=self._node_task_text(node),
            mode=node.mode,
            reuse_state=state,
        )
        state.subagent_id = envelope["subagent_id"]
        state.run_id = envelope["run_id"]
        state.summary = envelope.get("summary", "") or ""
        state.reason = envelope.get("reason")
        self._release(1)
        self._apply_run_status(state, envelope["status"])

    async def _execute_aggregate(self, state: NodeState) -> None:
        node = state.node
        contributions = self._collect_slots(state)
        state.slots.update(contributions)
        # 聚合节点的 ``outputs`` 声明「合并结果写到哪个槽」：单槽时所有上游贡献按
        # reducer 合并进该槽（多槽时逐个重复同一合并结果，保持可校验的简单语义）。
        merged = self._merge_contributions(state, contributions)
        for slot in node.outputs:
            state.slots[slot] = merged
        if node.strategy == "llm":
            envelope = await self._launch_run(
                node=node,
                task=self._aggregate_task_text(state),
                mode=node.mode,
                reuse_state=state,
            )
            state.subagent_id = envelope["subagent_id"]
            state.run_id = envelope["run_id"]
            state.summary = envelope.get("summary", "") or ""
            state.reason = envelope.get("reason")
            for slot in node.outputs:
                state.slots[slot] = state.summary or merged
            self._release(1)
            self._apply_run_status(state, envelope["status"])
            return
        # collect：纯逻辑聚合，不产生 run（completed 只数真实 run）。没有下游 LLM run
        # 来消化拼接结果，所以 D5 的 workflow 级汇聚器正是这里的压缩点：把多份贡献交给
        # summarizer 语义压缩，无 LLM 时退回有界拼接（不把巨型字符串原样传下去）。
        merged = await self._merge_contributions_bounded(state, contributions, merged)
        for slot in node.outputs:
            state.slots[slot] = merged
        state.summary = merged or "\n".join(str(value) for value in state.slots.values())
        state.subagent_id = None
        state.run_id = None
        state.status = "completed"

    async def _execute_route(self, state: NodeState) -> None:
        """Q8：route 只匹配结构化标签/受限枚举，不执行任何模型生成代码。

        动态条件源（D4/Q1/Q2）：``when`` 是 ``$ref:<node>:<slot>`` 时，先解析槽值、
        取**首个非空行**作期望标签，再走 ``matches_route(上游文本, 标签)`` 的行首匹配；
        槽缺失静默视为未命中走 default，diagnostics 记原因（Q3）。
        """
        node = state.node
        raw = self._route_verdict(state)
        matched: str | None = None
        for case in node.cases:
            label = self._route_case_label(node, case)
            if label is None:
                continue
            if matches_route(raw, label):
                matched = label
                state.targets = [case.to]
                break
        else:
            state.targets = [node.default] if node.default else []
        # ``verdict`` 是命中的**期望标签**（字面 case 即 case.when；``$ref`` case 是
        # 解析出的槽值首行），default 分支为 None；``raw`` 是上游原文，便于诊断
        # 「为什么走了这条边」而不把整段产出塞回父上下文。
        state.verdict = matched
        state.raw = raw[:_SUMMARY_LIMIT]
        self._route_counts[node.id] = self._route_counts.get(node.id, 0) + 1
        state.summary = f"{matched or 'default'} -> {state.targets}"
        state.status = "completed"
        spec = self._spec
        assert spec is not None
        for target in state.targets:
            successor = self._states.get(target)
            if successor is None:
                continue
            successor.activations += 1
            if successor.status in TERMINAL_NODE_STATUSES:
                self._reset_subtree(successor, origin=state.node.id)

    async def _execute_foreach(self, state: NodeState) -> None:
        """展开项**并发**派发（D2「对有限集合展开并行」），受三重闸门控。

        并发不是无界的：先按 max_runs / max_nodes 预检（超限直接报
        GraphRecursionError，而不是让 spawn 桶先炸），再由 ``_acquire_slot``
        统一受准入背压约束——所以峰值并发仍是 ``max_active``，只是不再串行。
        """
        node = state.node
        items = self._resolve_items(state)
        state.items = len(items)
        state.subagent_id = None
        state.run_ids = []
        state.subagent_ids = []
        # G7/D3b：项级进度与计数必须在这里一并归零。route 回边重跑同一个容器会
        # 重新走 ``_execute_foreach``，不归零就会在上一轮的结果上继续 ``+=``
        # （M2 的计数）或留下上一轮的 per-item 状态（「3/12 完成」配 pending）。
        state.item_states = ["pending"] * len(items)
        state.item_runs = [_ItemRunSlot() for _ in items]
        state.items_completed = 0
        state.items_failed = 0
        self._item_frame_pending = False
        self._item_frame_last_at = None
        # C4 runs 维度的预扣（Q4）：展开项绕过 ``_dispatch``，必须在这里与派发点同源
        # 地查一次；且刻意先于 ``_expand_plan`` 与 C2 结构闸——同值时由 C4 触发
        # ``budget_exceeded``（drain），C2 显式更小时才走 ``GraphRecursionError``。
        delta = len(items) - self._charged_expansions.get(node.id, 0)
        if delta > 0:
            self._enforce_c4_runs(self._runs + delta)
        # 展开期复检（Q3）：声明期不可知的展开项数在这里进入执行计划，重新插层。
        self._expand_plan(node.id, len(items))
        self._check_foreach_budget(node, state)
        tasks = []
        for index, item in enumerate(items):
            slot = _ItemRunSlot()
            state.item_runs[index] = slot
            task = asyncio.create_task(self._run_foreach_item(node, index, item, state, slot))
            # M2.1：计数点必须是**每项完成那一刻**的回调。放在 ``gather`` 之后的
            # 结果循环里只有 0 和 N 两种取值——整个运行期显示「完成 0/12」，
            # D5 的立项动机（看到并行）在时间维度上完全落空。
            task.add_done_callback(partial(self._on_foreach_item_done, state, index))
            tasks.append(task)
        for task in tasks:
            self._tasks.add(task)
        envelopes = await asyncio.gather(*tasks, return_exceptions=True)
        summaries: list[str] = []
        failures = 0
        for index, envelope in enumerate(envelopes):
            if isinstance(envelope, BaseException):
                if isinstance(envelope, asyncio.CancelledError):
                    state.status = "cancelled"
                    return
                summaries.append("")
                failures += 1
                continue
            state.subagent_ids.append(envelope["subagent_id"])
            state.run_ids.append(envelope["run_id"])
            summaries.append(envelope.get("summary", "") or "")
            if envelope["status"] != "completed":
                failures += 1
        state.runs = len(items)
        state.summary = "\n".join(summaries)
        if items and failures == len(items):
            state.status = "failed"
            state.reason = "all foreach items failed"
        elif failures:
            state.status = "completed"
            state.reason = f"{failures}/{len(items)} foreach items did not complete"
        else:
            state.status = "completed"

    async def _run_foreach_item(
        self,
        node: WorkflowNode,
        index: int,
        item: Any,
        state: NodeState,
        slot: _ItemRunSlot | None = None,
    ) -> dict:
        """一个展开项的完整生命周期；并发实例由 ``_acquire_slot`` 统一背压。

        身份记账走 ``slot``（index → run），因为 ``state.subagent_ids`` 是 gather
        之后才 append 的稀疏数组——用它当 index 映射会让被取消/异常的项消失。
        """
        acquired = await self._acquire_slot()
        if not acquired:
            state.item_states[index] = "cancelled"
            raise asyncio.CancelledError
        try:
            return await self._launch_run(
                node=node,
                task=render_item_task(node.task, item, index=index),
                mode=node.mode,
                reuse_state=slot,
                session_name=f"{node.id}-{index}",
            )
        finally:
            self._release(1)

    def _item_live_status(self, slot: _ItemRunSlot) -> str:
        """一项「已派发但未终态」时此刻的真实状态（G7 的口径修正）。

        ``_dispatch_capacity`` 是 ``max_active + max_queued_runs``（默认 25），所以
        12 项会被**一次性派发**，但真正在执行只有 ``max_active``（默认 5）个。
        「已派发未终态」当在跑会把 20 个排队项全画成蓝的——必须问 run record。
        """
        if slot.subagent_id is None or slot.run_id is None:
            return "queued"
        run = self.manager.find_run(slot.subagent_id, slot.run_id)
        if run is not None and run.status == "running":
            return "running"
        return "queued"

    def _on_foreach_item_done(
        self,
        state: NodeState,
        index: int,
        task: asyncio.Task,
    ) -> None:
        """一项的 done 回调（M2.1）：落 per-item 终态、推进计数、推一帧进度。

        **非失败的中断不得计入 ``items_failed``**：``_acquire_slot`` 返回 False 时
        抛的 ``CancelledError``、``GraphRecursionError``、``WorkflowBudgetExceeded``
        都不是「这一项失败了」——把它们计成失败等于向前端谎报。
        """
        if index >= len(state.item_states):
            # 容器被重跑（回边）后旧 task 才收尾：它的 index 属于上一轮，丢弃。
            return
        status = "completed"
        if task.cancelled():
            status = "cancelled"
        else:
            exc = task.exception()
            if isinstance(exc, asyncio.CancelledError):
                status = "cancelled"
            elif isinstance(exc, (GraphRecursionError, WorkflowBudgetExceeded)):
                status = "cancelled"
            elif exc is not None:
                status = "failed"
            else:
                envelope = task.result()
                if envelope.get("status") != "completed":
                    status = "failed"
        if status == "completed":
            state.items_completed += 1
        elif status == "failed":
            state.items_failed += 1
        state.item_states[index] = status
        self._emit_item_frame()

    def _emit_item_frame(self) -> None:
        """项级迁移的推帧，**调度器侧限频**（M2.3/G2）。

        每个窗口最多构建一帧（``emit``），窗口末的第二条迁移把该帧标记为
        ``pending``，由 ``_drain_item_frame`` 在窗口过后的下一次迁移或 ``_drive``
        的下一轮里补发——所以「限频」只合并构建，不吞掉尾帧。
        """
        now = time.monotonic()
        last = self._item_frame_last_at
        if last is not None and now - last < _ITEM_FRAME_WINDOW_S:
            self._item_frame_pending = True
            return
        self._item_frame_last_at = now
        self._item_frame_pending = False
        self._emit_graph_snapshot()

    def _drain_item_frame(self) -> None:
        """补发被限频窗口合并掉的那一帧（保证任何状态变化最终都可见）。"""
        if not self._item_frame_pending:
            return
        self._item_frame_pending = False
        self._item_frame_last_at = time.monotonic()
        self._emit_graph_snapshot()

    def _expand_plan(self, node_id: str, count: int) -> None:
        """展开期复检（Q3）：把 foreach 展开项数记进执行计划并按需插入新层。

        声明期只知道 1 个 foreach 节点；运行时才知道它展开出多少项。不在这里重算，
        「2 个声明节点 + 展开 100 项汇入同一 aggregate」的图仍会把 100 份结果 concat
        后喂给单个 aggregate——正是 spec delta 要防的场景。

        新插入的节点必须进 ``_expanded_nodes`` 记账并复检（grill 决策 6）：它们绕过
        parse 期的 ``max_nodes`` 检查。
        """
        plan = self._plan
        if plan is None:
            return
        expanded = plan.with_expansion(node_id, count)
        new_ids = [
            node_id for node_id in expanded.inserted_nodes if node_id not in plan.inserted_nodes
        ]
        # 收缩时（展开项数变少）旧 auto 节点的 NodeState 会失效：它们已不在新 plan 的
        # 图里，却仍被 `_unit_counts()` 统计进 envelope 的 total/pending（Issue 5）。
        # 先算 stale 集合，两条返回路径都要 prune。
        stale_ids = [
            node_id
            for node_id in plan.inserted_nodes
            if node_id not in expanded.inserted_nodes
        ]
        if not new_ids:
            self._plan = expanded
            self._prune_states(stale_ids)
            return
        spec = self._spec
        assert spec is not None
        added_nodes = len(new_ids)
        # foreach 展开项本身也要吃 max_nodes：展开前预检保留给 `_check_foreach_budget`，
        # 这里只把**新增的 auto aggregate 节点**记进已声明节点数并复检。
        if self._expanded_nodes + added_nodes > spec.max_nodes:
            raise GraphRecursionError(
                steps=self._steps,
                limit=spec.max_nodes,
                current_nodes=new_ids,
                reason="max_nodes",
                message=(
                    f"GraphRecursionError: node {node_id!r} expansion requires "
                    f"{added_nodes} auto-inserted aggregate nodes, exceeding max_nodes "
                    f"{spec.max_nodes} ({self._expanded_nodes} already declared)"
                ),
            )
        self._expanded_nodes += added_nodes
        self._plan = expanded
        for new_id in new_ids:
            self._states[new_id] = NodeState(node=expanded.node(new_id))
        self._prune_states(stale_ids)

    def _prune_states(self, stale_ids: list[str]) -> None:
        """丢弃已不在执行图里的节点状态（Issue 5：收缩后不留幽灵计数）。

        只删真正失效的 id；仍在图里的节点状态（可能已带运行期 summary/槽）保持不动。
        已计费的 ``_expanded_nodes`` 不退还——预算是保守的**高水位**口径，与
        ``_check_foreach_budget`` 只收增量的语义一致。
        """
        for stale_id in stale_ids:
            state = self._states.pop(stale_id, None)
            if state is None:
                continue
            # 在途节点不该出现在 stale 集合里（foreach 必须等所有展开项收尾才结束，
            # 其下游 aggregate 才可能就绪）。真出现时按取消处理，避免留下孤儿任务。
            if state.status in ("queued", "started"):
                self._schedule_cancel(state)
            self._live_runs.pop(stale_id, None)

    def _check_foreach_budget(self, node: WorkflowNode, state: NodeState) -> None:
        """展开前预检（Q5/D6）：max_runs 与 max_nodes 都要把展开项算进去。

        预检先于任何 session 创建，所以超限时不会留下半张已展开的图；报错走
        ``GraphRecursionError`` envelope（Q8），而不是让 spawn 桶抛底层 RuntimeError。

        计费按**增量**：route 回边会把同一个 foreach 重新激活，重复按满额计费会让
        用户配置的 max_nodes/max_runs 被无声缩水（review Issue 3）。``_charged_
        expansions`` 记「该节点已计费到多少项」，只收差额；项数变小时保守保持已扣
        额度（不退还），与 ``_expand_plan`` 的幂等语义对齐。
        """
        spec = self._spec
        assert spec is not None
        count = state.items or 0
        charged = self._charged_expansions.get(node.id, 0)
        delta = count - charged
        if delta <= 0:
            return  # 已计费过这份（或更大量）展开，不重复扣
        if self._runs + delta > spec.max_runs:
            raise GraphRecursionError(
                steps=self._steps,
                limit=spec.max_runs,
                current_nodes=[node.id],
                reason="max_runs",
                message=(
                    f"GraphRecursionError: foreach node {node.id!r} would expand "
                    f"{count} runs ({delta} new), exceeding max_runs {spec.max_runs} "
                    f"({self._runs} already used)"
                ),
            )
        if self._expanded_nodes + delta > spec.max_nodes:
            raise GraphRecursionError(
                steps=self._steps,
                limit=spec.max_nodes,
                current_nodes=[node.id],
                reason="max_nodes",
                message=(
                    f"GraphRecursionError: foreach node {node.id!r} would expand "
                    f"{count} nodes ({delta} new), exceeding max_nodes {spec.max_nodes} "
                    f"({self._expanded_nodes} already declared)"
                ),
            )
        self._charged_expansions[node.id] = count
        self._expanded_nodes += delta
        self._runs += delta

    # -- run 派发（身份 contextvar 的唯一 set 点） ---------------------------

    async def _launch_run(
        self,
        *,
        node: WorkflowNode,
        task: str,
        mode: str | None,
        reuse_state: NodeState | _ItemRunSlot | None,
        session_name: str | None = None,
    ) -> dict:
        """在**入队上下文**里 set workflow/node/bus 身份后调用 ``run_subagent``。

        C1 的 ``_enqueue_run`` 用 ``copy_context()`` 捕获入队时的上下文
        （``manager.py:571``），所以这两个身份必须在调用 ``run_subagent`` 的
        这一刻就已经 set 好——等 run 真正执行时再 set 会丢（grill 决策 1/2）。

        run 的 id 在**派发成功的那一刻**就写回 ``reuse_state``（而不是等它终态）：
        ``best_effort`` 的截止时间到了要能找到并取消仍在跑的 run。
        """
        manager = self.manager
        # 身份 contextvar 的包裹点（grill 决策 1/2）：``create_subagent`` 与
        # ``run_subagent`` 都读 ``current_workflow_id()``/``current_node_id()``，
        # 而 ``_enqueue_run`` 只在被调用的那一刻 ``copy_context()``——所以身份必须
        # 在调用前 set、调用后立刻 reset。中间虽然有 await，但 asyncio 的每个 Task
        # 各持一份 context 副本，其它节点的 run 看不到这里的 set。
        token_workflow = set_workflow_id(self.workflow_id)
        token_node = set_node_id(node.id)
        token_distance = set_graph_distance(self._graph_distance_for(node.id))
        token_bus = set_bus(self.bus)
        try:
            subagent_id = reuse_state.subagent_id if reuse_state and reuse_state.subagent_id else None
            if subagent_id is None:
                created = manager.create_subagent(
                    name=session_name or node.name or node.id,
                    description=node.description,
                    mode=mode,
                )
                subagent_id = created["subagent_id"]
                if reuse_state is not None:
                    reuse_state.subagent_id = subagent_id
            launched = await manager.run_subagent(
                subagent_id=subagent_id,
                task=task,
                wait=False,
                max_tokens=node.max_tokens,
                max_time_s=node.max_time_s,
                # edge 在**调度器派发点**算出（决策 6：``_new_run`` 没有「上游节点」
                # contextvar，推不出来）；foreach 展开项复用容器节点的数据入边。
                edge=self._edge_for(node.id),
            )
        finally:
            reset_bus(token_bus)
            reset_graph_distance(token_distance)
            reset_node_id(token_node)
            reset_workflow_id(token_workflow)
        run_id = launched["run_id"]
        if launched["status"] == "queue_full":
            # Q2：准入背压让 workflow 永不撞 queue_full；真撞上时 manager 已经把
            # run record 弹掉了（`_take_back_if_queue_full`），所以这里**不能**索引
            # ``session.runs[-1]``——按可诊断的失败记账，绝不静默丢。
            # 计数落账（C5 Q3）：这一类在 workflow 内**预期恒为 0**，实现必须能诚实
            # 报 0 而不是给个看着像有数据的数——所以计数点是这个真实的拒绝分支。
            self._queue_full_runs += 1
            return {
                "subagent_id": subagent_id,
                "run_id": run_id,
                "status": "queue_full",
                "summary": "",
                "reason": launched.get("reason") or "subagent queue is full",
            }
        self._run_refs.append(manager._sessions[subagent_id].runs[-1])
        # 派发即登记：取消路径要能在 run 终态之前找到它。foreach 节点没有单一
        # session，所以只登记 live 列表，不写回 state.subagent_id（它是 None）。
        if reuse_state is not None:
            reuse_state.subagent_id = reuse_state.subagent_id or subagent_id
            reuse_state.run_id = run_id
        self._live_runs.setdefault(node.id, []).append((subagent_id, run_id))
        self._refresh_peak()
        # foreach 展开项（M2.3）：run 身份此刻才落定，项级「排队 → 在跑」的迁移帧
        # 要在这里发——``_run_foreach_item`` 的 finally 发不了（那时 run 已终态）。
        # ``getattr`` 是必要的：普通节点的 ``reuse_state`` 是 ``NodeState``（没有
        # 这个字段），只有展开项传的 ``_ItemRunSlot`` 才有。
        on_dispatch = getattr(reuse_state, "on_dispatch", None)
        if on_dispatch is not None:
            on_dispatch()
        terminal = await self._await_run(subagent_id, run_id)
        self._live_runs.get(node.id, []).remove((subagent_id, run_id))
        # 失败计数（change fix-issue-215 Q6 方案 D）：run 此刻已终态、trace 必然写完，
        # **每 run 算一次**——不放在 ``_graph_node_projection`` 里每帧现算（那会是每帧
        # O(节点数 × 步数)，而快照按节点事件推进）。普通节点与 foreach 展开项都走这条
        # 路径（共用 ``reuse_state`` 这一个身份槽），所以埋一处就够。
        # 只读 ``run.trace``，不改写入侧那四个终态落点。
        self._record_failure_count(
            reuse_state, count_failures(getattr(manager.find_run(subagent_id, run_id),
                                                "trace", None)))
        return terminal

    async def _await_run(self, subagent_id: str, run_id: str) -> dict:
        """等 run 终态，但周期性让出调度（否则取消/背压无法介入）。

        调度器与 run 任务在同一条事件循环上：``await`` 一个 sleep 让事件循环把
        ``_apply_cancel`` 的取消/``_fire_best_effort_deadlines`` 跑起来，否则
        WorkflowTask 的取消要等到节点自己的 run 结束才生效。
        """
        manager = self.manager
        while True:
            run = manager.find_run(subagent_id, run_id)
            if run is not None and run.status in TERMINAL_RUN_STATUSES:
                self._refresh_peak()
                # 内部消费：envelope 的 summary 会喂 state.summary → 下游聚合。
                # 必须取全量——聚合器用 len(merged) 判断要不要调 summarizer 压缩，
                # 提前裁短会让它误判「没超预算」而静默跳过压缩（issue #213 D2）。
                return manager._format_run_envelope(  # type: ignore[arg-type]
                    subagent_id, run, full_summary=True
                )
            self._refresh_peak()
            await asyncio.sleep(_POLL_INTERVAL_S)

    @staticmethod
    def _record_failure_count(reuse_state: Any, count: int | None) -> None:
        """把失败计数写回调用方给的身份槽（普通节点是 ``NodeState``，展开项是
        ``_ItemRunSlot``）。两处共用 ``_launch_run`` 这一个埋点，不埋第二处。
        """
        if reuse_state is not None and hasattr(reuse_state, "failure_count"):
            reuse_state.failure_count = count

    def _apply_run_status(self, state: NodeState, status: str) -> None:
        state.runs += 1
        if status == "completed":
            state.status = "completed"
        elif status == "cancelled":
            state.status = "cancelled"
            state.reason = state.reason or "cancelled"
        else:
            state.status = "failed"
            state.reason = state.reason or status

    # -- best_effort 截止时间 -------------------------------------------------

    def _fire_best_effort_deadlines(self) -> None:
        """Q3：截止时间到 → 取消仍在跑的臂 + 按已完成结果聚合。"""
        spec = self._spec
        assert spec is not None
        now = time.time()
        for state in self._states.values():
            node = state.node
            if node.kind != "aggregate" or node.join != "best_effort":
                continue
            if state.status != "pending" or state.deadline_fired:
                continue
            if state.deadline_ref is None or node.deadline_s is None:
                continue
            if now - state.deadline_ref < node.deadline_s:
                continue
            state.deadline_fired = True
            for edge in self._graph().data_incoming(node.id):
                upstream = self._states.get(edge.source)
                if upstream is not None and upstream.status in ("queued", "started"):
                    self._schedule_cancel(upstream)

    def _schedule_cancel(self, state: NodeState) -> None:
        state.status = "cancelled"
        state.reason = "cancelled: best_effort deadline reached"
        task = asyncio.create_task(self._cancel_node(state))
        self._tasks.add(task)

    async def _cancel_node(self, state: NodeState) -> None:
        """取消该节点所有仍在跑的 run（含 foreach 展开项）。"""
        live = set(self._live_runs.get(state.node.id, []))
        if state.subagent_id is not None and state.run_id is not None:
            live.add((state.subagent_id, state.run_id))
        for subagent_id, run_id in live:
            try:
                await self.manager.cancel_subagent_run(
                    subagent_id=subagent_id, run_id=run_id
                )
            except Exception:  # noqa: BLE001 - 取消是尽力而为
                continue

    async def _acquire_slot(self) -> bool:
        """背压门：在途 run 数达到 max_active + max_queued_runs 时让出调度。

        run 预算（``max_runs``）已由调用方在派发前预扣，这里只管理物理在途槽位。
        返回 False 表示 workflow 在等待期间被取消（调用方自行收尾，别派发）。
        """
        capacity = self._dispatch_capacity()
        while self._in_flight_runs + 1 > capacity:
            if self._cancelled:
                return False
            self._progress.clear()
            await self._progress.wait()
        if self._cancelled:
            return False
        self._in_flight_runs += 1
        return True

    # -- 槽 / 任务文本 -------------------------------------------------------

    async def _merge_contributions_bounded(
        self,
        state: NodeState,
        contributions: dict[str, str],
        merged: str,
    ) -> str:
        """collect 聚合的压缩点（D5/Q7）。

        只有**多份贡献**且拼接结果超出该节点预算时才走 summarizer：单份贡献或本来就
        在预算内的结果保持原样（既省一次无谓调用，也保住既有精确断言）。
        """
        plan = self._plan
        if plan is None:
            return merged
        budget = plan.budget_for(state.node.id)
        if len(merged) <= budget * CHARS_PER_TOKEN:
            return merged
        # 传给 summarizer 的是**每个上游一份**的 bounded 产出（而不是已经 concat 好的
        # 巨型字符串）：compress 的语义是「多份文本 → 一份摘要」。
        #
        # 不按上游数提前返回：单个 foreach 容器展开 100 项时上游只有 1 个，但它的
        # summary 已经是 100 份结果的拼接——正是 Q3 要防的场景，必须压缩。
        upstreams = [
            edge
            for edge in plan.data_incoming(state.node.id)
            if self._states.get(edge.source) is not None
            and self._states[edge.source].status in TERMINAL_NODE_STATUSES
        ]
        texts = [
            text
            for edge in upstreams
            for text in (self._bounded_output(self._states[edge.source], "result"),)
            if text
        ]
        if not texts:
            return self._aggregator.bounded(merged, budget=budget)
        return await self._aggregator.merge(texts, budget=budget)

    def _merge_contributions(self, state: NodeState, contributions: dict[str, str]) -> str:
        """把所有上游贡献合并成一个字符串（``outputs`` 单槽时的取值语义）。

        每个槽的贡献已经在 :meth:`_collect_slots` 里按 reducer 合并过了，所以这里
        不能按上游逐条再折叠一次（会把同一份贡献重复计数）。单槽直接取该槽；声明了
        多个槽时按声明的 reducer 二次合并。
        """
        if not contributions:
            return ""
        if len(contributions) == 1:
            return next(iter(contributions.values()))
        reducer = "concat"
        for edge in self._graph().data_incoming(state.node.id):
            if edge.reducer:
                reducer = edge.reducer
                break
        return aggregate_slots(list(contributions.values()), reducer)

    def _collect_slots(self, state: NodeState) -> dict[str, str]:
        """按槽聚合每个数据上游的产出（每节点取最新一次 run，Q9/D7）。"""
        groups: dict[str, list[str]] = {}
        reducers: dict[str, str] = {}
        for edge in self._graph().data_incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None or upstream.status not in TERMINAL_NODE_STATUSES:
                continue
            for slot in upstream.node.outputs:
                value = self._node_output(upstream, slot)
                if value is None:
                    continue
                # 消费打标（C5 D4/Q2）：这个上游的产出真被下游 reducer 读走了。
                self._mark_consumed(upstream)
                self._consumed_edges.add((edge.source, edge.target))
                groups.setdefault(slot, []).append(value)
                if edge.reducer:
                    reducers[slot] = edge.reducer
        return {
            slot: aggregate_slots(values, reducers.get(slot, "concat"))
            for slot, values in groups.items()
        }

    def _node_output(self, state: NodeState, slot: str) -> str | None:
        if slot in state.slots and state.node.kind != "subagent":
            return state.slots[slot]
        plan = self._plan
        for edge in (plan.data_incoming(state.node.id) if plan else ()):
            upstream = self._states.get(edge.source)
            if upstream is not None and slot in upstream.slots:
                return upstream.slots[slot]
        return state.summary or None

    def _node_task_text(self, node: WorkflowNode) -> str:
        """subagent 节点的任务文本 = 节点 task + 上游**bounded**产出（D7/Q7）。

        真正的爆点在这里（grill 决策 5）：把所有数据上游的 ``_node_output`` 原文拼进
        下游 task，100 个 leaf 就会把 100 份完整结果灌进一个 prompt。所以下游消费的是
        bounded 投影（按上游节点的预算档裁剪 + 带 ``result_ref``），不是全文。
        """
        spec = self._spec
        assert spec is not None
        parts = [node.task]
        goal = spec.goal
        if goal and goal not in node.task:
            parts.append(f"Overall goal: {goal}")
        for edge in self._plan.data_incoming(node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            text = self._bounded_output(upstream, "result")
            if not text:
                continue
            self._mark_consumed(upstream)
            self._consumed_edges.add((edge.source, edge.target))
            ref = self._result_ref_for(upstream)
            suffix = f" (full result: {ref})" if ref else ""
            parts.append(f"Input from {edge.source}{suffix}:\n{text}")
        return "\n\n".join(parts)

    def _aggregate_task_text(self, state: NodeState) -> str:
        """aggregate 的任务文本 = 节点 task + 各上游的 **bounded** 贡献（Q7）。

        不能读 ``state.slots`` 的拼接结果：那已经是 N 份全文 concat 后的巨型字符串
        （``reducer=concat``），把它整段喂给 aggregate 正是要防的 prompt 膨胀。这里
        改为按上游逐个取 bounded 投影。
        """
        spec = self._spec
        assert spec is not None
        parts = [state.node.task or f"Aggregate the results of {spec.goal or 'the workflow'}."]
        for edge in self._plan.data_incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            for slot in upstream.node.outputs:
                text = self._bounded_output(upstream, slot)
                if not text:
                    continue
                self._mark_consumed(upstream)
                self._consumed_edges.add((edge.source, edge.target))
                ref = self._result_ref_for(upstream)
                suffix = f" (result_ref: {ref})" if ref else ""
                parts.append(f"Input from {edge.source} slot {slot}{suffix}:\n{text}")
        return "\n\n".join(parts)

    def _result_ref_for(self, state: NodeState) -> str | None:
        """上游节点的最新一次 run 的 ``result_ref``（没落盘/token 上限到达时为空）。"""
        if not state.subagent_id or not state.run_id:
            return None
        run = self.manager.find_run(state.subagent_id, state.run_id)
        return getattr(run, "result_ref", None) if run is not None else None

    def _bounded_output(self, state: NodeState, slot: str) -> str:
        """一个上游节点在**下游视角**下的 bounded 产出（按距 leaf 层数定档裁剪）。

        裁剪经 :class:`WorkflowAggregator` 完成（D5：复用 summarizer 抽象），短文本
        no-op——grill 风险「中」的既有精确相等断言因此不受影响。
        """
        value = self._node_output(state, slot)
        if not value:
            return ""
        plan = self._plan
        assert plan is not None
        tier_tokens = plan.budget_for(state.node.id)
        return self._aggregator.bounded(value, budget=tier_tokens)

    def _route_case_label(self, node: WorkflowNode, case: Any) -> str | None:
        """一条 case 的**期望标签**（D4/Q1/Q2）。

        - 字面 case：``case.when`` 原样作标签（C2 语义保留）；
        - ``$ref:<node>:<slot>`` case：读该节点 ``NodeState.slots[slot]`` → 取**首个
          非空行**（``_first_non_empty_line`` + strip）作标签；槽缺失/空值 → 返回
          ``None``（未命中），并在 diagnostics 记原因（Q3）。

        **判定前不调 ``bounded``**：``WorkflowAggregator.bounded`` 会截断并追加
        ``…[bounded...]``，长值场景下标签必然判不中（Q2）。``bounded`` 只用于诊断展示。
        运行时只读 ``NodeState.slots``——不落盘、不读文件、不做 ``_node_output`` 的跨
        节点回退（D4 的安全边界）。
        """
        when = case.when
        if not is_route_ref(when):
            return when
        ref = parse_route_ref(when)
        if ref is None:
            # 校验期已拒绝非法格式；这里防御性处理（运行期等价于未命中）。
            self._note_route_ref_miss(node.id, when, "malformed $ref")
            return None
        ref_node_id, ref_slot = ref
        ref_state = self._states.get(ref_node_id)
        if ref_state is None:
            self._note_route_ref_miss(node.id, when, "referenced node has no state")
            return None
        if ref_slot not in ref_state.slots:
            self._note_route_ref_miss(
                node.id, when, f"slot {ref_slot!r} not materialised on {ref_node_id!r}"
            )
            return None
        label = _first_non_empty_line(ref_state.slots.get(ref_slot) or "")
        if not label:
            self._note_route_ref_miss(
                node.id, when, f"slot {ref_slot!r} on {ref_node_id!r} is empty"
            )
            return None
        return label

    def _note_route_ref_miss(self, route_id: str, when: str, reason: str) -> None:
        """把一次 ``$ref`` 未命中记进 diagnostics（Q3：静默不报错，但要有迹可循）。"""
        misses = self._diagnostics.setdefault("route_ref_misses", [])
        misses.append({"route": route_id, "when": when, "reason": reason})

    def _route_verdict(self, state: NodeState) -> str:
        """route 的判定文本 = 所有数据上游产出的拼接（只做标签匹配）。

        D2b（enhance-workflow-graph-ux）：这里读上游产出的同时也是**一次消费**，
        必须顺手记 per-edge 账（``_mark_consumed`` 的既有四个调用点都在
        aggregate/root 路径上，route 一个都不走）——否则 ``a→gate`` 这类
        route 数据入边永远落 ``inactive`` 兜底，看起来像「数据没流过去」。
        与既有三处同构：只在 ``if text:`` 内记账，不改 ``_mark_consumed`` 本体
        （C5 的 ``_consumed_run_ids``/``useful_runs``/``redundancy`` 逐位不变）。
        """
        parts: list[str] = []
        for edge in self._graph().data_incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            text = self._node_output(upstream, "result")
            if text:
                parts.append(text)
                self._consumed_edges.add((edge.source, edge.target))
        return "\n".join(parts)

    def _resolve_items(self, state: NodeState) -> list[Any]:
        """解析 foreach 的展开集合（D5/Q9/Q10）。

        ``max_items=0`` 的效果在各处不同：

        - ``>0``：静态截断 ``items[:max_items]``（C2 语义保留）；
        - ``==0``：**不做静态截断**，改按剩余图级预算截断（:meth:`_remaining_expansion_capacity`），
          且截断必须发生在 ``_expand_plan`` 之前（否则会先撞 ``max_nodes``，见 Q9 的
          审阅员注记）。
        """
        node = state.node
        if node.items is not None:
            items = list(node.items)
        else:
            value = self._source_collection(node)
            # ``source_field`` **只应用一次**（Q10）：取到基础值后直接交给
            # ``extract_collection``，不再额外传 field（二次取字段会退化）。
            items = extract_collection(value, node.source_field)
        if node.max_items == 0:
            return items[: self._remaining_expansion_capacity()]
        return items[: node.max_items]

    def _source_collection(self, node: WorkflowNode) -> Any:
        """跨层解析 foreach 的 ``source``（Q10）。

        顺序：优先读 source 节点**自身**的 ``result`` 槽（运行时物化的槽值），没有才在
        **唯一数据上游**时沿数据边继续向上；多入边且无物化 result = schema 歧义拒绝；
        递归在无上游/已访问处终止（环已在校验期拒绝）。返回值**不含** ``source_field``
        的二次应用（由调用方统一交给 ``extract_collection``）。
        """
        source_id = node.source or ""
        # Q2（issue #207）：从**哪个节点**读到了产出就记哪条边——动态 foreach
        # 确实消费了上游产出，不记账会让该边被判成「产出未被下游读取」
        # （change ``workflow-gate-only-edge-status`` 新增的 ``satisfied`` 档）。
        # 与 #197 在 ``_route_verdict`` 的修法同构：**旁加** ``_consumed_edges``，
        # ``_mark_consumed`` 本体不动 → C5 的 ``_consumed_run_ids`` 零漂移。
        def _read(source_state: NodeState, slot: str = "result") -> Any:
            value = self._node_output(source_state, slot)
            if value:
                self._consumed_edges.add((source_state.node.id, node.id))
            return value

        visited: set[str] = set()
        current = source_id
        while current and current not in visited:
            visited.add(current)
            source_state = self._states.get(current)
            if source_state is None:
                return None
            if "result" in source_state.slots:
                value = source_state.slots["result"]
                if value:
                    self._consumed_edges.add((source_state.node.id, node.id))
                return value
            # 非 subagent 节点会物化 summary 作兜底（collect aggregate 的产出）。
            if source_state.node.kind != "subagent" and source_state.summary:
                self._consumed_edges.add((source_state.node.id, node.id))
                return source_state.summary
            upstreams = self._graph().data_incoming(current)
            distinct = sorted({edge.source for edge in upstreams})
            if len(distinct) != 1:
                # 无上游（终止）或多入边歧义（拒绝递归）
                return _read(source_state)
            current = distinct[0]
        if source_id in self._states:
            return _read(self._states[source_id])
        return None

    def _remaining_expansion_capacity(self) -> int:
        """``max_items=0`` 的展开上限（Q9）：三个剩余上限的**最小值**。

        三者：C4 的 ``max_total_runs``、C2 的 ``max_runs``、C2 的 ``max_nodes``
        （后者按「每展开项一个节点」计）。任一维度为 0（不限 / 无约束）则跳过它。
        """
        spec = self._spec
        if spec is None:
            return 0
        limits: list[int] = []
        budget = self._budget
        if budget is not None and budget.max_runs:
            limits.append(max(budget.max_runs - self._runs, 0))
        limits.append(max(spec.max_runs - self._runs, 0))
        limits.append(max(spec.max_nodes - self._expanded_nodes, 0))
        return min(limits) if limits else 0

    # -- 度量 ---------------------------------------------------------------

    def _ledger_total(self) -> float:
        ledger = getattr(self.manager, "cost_ledger", None)
        if ledger is None:
            return 0.0
        try:
            return float(ledger.total())
        except Exception:  # noqa: BLE001
            return 0.0

    def _queue_wait_s(self) -> float | None:
        """最长单次排队时长（Q4：聚合用 ``max``，不用 sum/p50）。

        数据面今天就在 run record 上（``created_at``/``started_at``，manager 赋值），
        零新字段、零新分支（Confirmed Decision 5）。``started_at is None`` 的 run 是
        「排了队但没跑成就被取消」，在这里沉默跳过，单独记 ``queue_cancelled_runs``。

        ``None`` 语义 = 本 workflow 没有任何 run 真的开跑。
        """
        return max(
            (r.started_at - r.created_at for r in self._run_refs if r.started_at),
            default=None,
        )

    def _queue_cancelled_runs(self) -> int:
        """排队期间被取消（从未开跑）的 run 数（Q4）。

        **单列、不并入拒绝降级计数**：它是分母侧的量，语义与 ``queue_full``
        （根本没排上队）相反，两者不得合并成一个指标。
        """
        return sum(1 for r in self._run_refs if r.started_at is None)

    def _redundancy(self) -> float | None:
        """冗余度 = 有用产出 / spawn 总数（D4，Q2 消费口径）。

        分子 = 被下游真正读走产出的 run 数；分母 = workflow 级 spawn 快照（含
        ``create_subagent`` + 真实 run，不含 queue_full）。分母为 0 时记 ``None``
        而不是 0——「没有 spawn」与「spawn 全是冗余」是两回事。值越低越健康。
        """
        spawns = self._spawn_count_snapshot
        if not spawns:
            return None
        return round(len(self._consumed_run_ids) / spawns, 6)

    def _rejected_runs(self) -> int:
        """拒绝降级总量（D4 四类 = queue_full + 深度撤工具 + spawn 预算拒绝 + 图级超限）。

        ``queue_cancelled_runs`` **不**在这里（它是分母侧量，Q4 明确单列）。
        """
        return (
            self._queue_full_runs
            + self._graph_recursion_runs
            + self._rejection_counts_snapshot.get("depth_capped", 0)
            + self._rejection_counts_snapshot.get("spawn_budget", 0)
        )

    def _refresh_peak(self) -> None:
        # Q9：peak_active = 本 workflow 内并发执行的 run 数（不被同 manager 其他
        # pattern 污染），因此从自己的 run record 里统计，而非许可池占用。
        running = sum(1 for run in self._run_refs if run.status == "running")
        self._peak_active = max(self._peak_active, running)

    def _logical_units(self, state: NodeState) -> int:
        """一个节点的**逻辑执行单元**数（Q2 的分母口径）。

        普通节点 = 1；``foreach`` = 展开项数 + 1（展开项各自是一个执行单元，容器节点
        自身也是一个）。未展开时按 1 算。
        """
        if state.node.kind == "foreach":
            return (state.items or 0) + 1
        return 1

    def _unit_counts(self) -> dict[str, int]:
        """按逻辑执行单元统计各桶（Q2）。

        ``blocked`` 是终态、单独计数；``cancelled``/``budget_exceeded`` 单列不混
        ``failed``；剩下的（pending/queued/started）都是 ``pending``。
        """
        counts = {
            "total": 0,
            "completed_units": 0,
            "failed_units": 0,
            "cancelled_units": 0,
            "budget_exceeded_units": 0,
            "blocked_units": 0,
            "skipped_units": 0,
            "pending_units": 0,
        }
        for state in self._states.values():
            units = self._logical_units(state)
            counts["total"] += units
            status = state.status
            if status == "completed":
                counts["completed_units"] += units
            elif status == "failed":
                counts["failed_units"] += units
            elif status == "cancelled":
                counts["cancelled_units"] += units
            elif status == "budget_exceeded":
                counts["budget_exceeded_units"] += units
            elif status == "blocked":
                counts["blocked_units"] += units
            elif status == "skipped":
                # 良性终态，**独立桶**——落 pending_units 会让「图跑完了还有
                # pending」自相矛盾。
                counts["skipped_units"] += units
            else:
                counts["pending_units"] += units
        return counts

    # -- 运行态图快照（change ``workflow-graph-visualization``） -------------

    def workflow_graph_snapshot(self) -> dict:
        """面向 Web UI 的**运行态图快照**（D3 + grill 决策 4 / Q10）。

        与 ``_envelope`` 的关系：这是**另一条出口**，不是它的投影。``_envelope`` 是
        父 Agent 契约（含 ``bus``/``attribution``/``latest_events`` 等重字段，且节点
        走 ``NodeState.to_dict()``），本方法按 Web UI 的需要**显式挑字段**——两者互不
        影响，本方法一行都不改 ``_envelope``。

        字段口径（Q10）：只含 ``workflow_id``/``spec_hash``/``goal``/``status``/
        ``nodes``/``edges``/``timestamp``，终态时附 ``total``/``completed``/
        ``failed`` 计数，超限时附 ``diagnostics``。归属用的 ``session_id`` 由 web 层
        的 forwarder 补（调度器不知道自己的 ws session，见 Q1/Q8）。节点不含 ``subagent_ids``（foreach
        每展开项一个 id）/``slots``（concat 后巨型字符串）/``raw``/``error`` 原文；
        边只含结构字段。

        规模（决策 10）：``nodes`` 长度天然就是 ``len(self._graph().nodes)``，即当前图
        规模的权威值——不用 ``_expanded_nodes``（那是计费高水位，收缩后不退还）。
        """
        plan = self._plan
        nodes = [
            self._graph_node_projection(self._states[node.id])
            for node in (plan.nodes if plan else ())
            if node.id in self._states
        ]
        edges = [
            {
                "from": edge.source,
                "to": edge.target,
                "channel": edge.channel,
                "required": edge.required,
                "reducer": edge.reducer,
                "kind": "control" if plan is not None and plan.is_control_edge(edge) else "data",
                "status": self._edge_status(edge),
            }
            for edge in (plan.edges if plan else ())
        ]
        payload: dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "spec_hash": self._spec.spec_hash if self._spec else None,
            "goal": self._spec.goal if self._spec else "",
            "status": self._status,
            "nodes": nodes,
            "edges": edges,
            "timestamp": time.time(),
            # 图级起止（D3）：哨兵**统一成 ``null``**——``self._started_at`` 的构造期
            # 哨兵是 ``0.0``，前端会把它当 epoch 0 渲染成「56 年前」或算出天文耗时。
            # 也**不要**复用 ``_envelope`` 的 ``self._finished_at or time.time()``
            # 口径（那会把「还在跑」谎报成「刚跑完」）。
            "started_at": self._started_at or None,
            "finished_at": self._finished_at,
            # 图级预算（G13）：用户看到「预算超限（tokens）」的下一个动作必然是
            # 「花了多少」。``declared`` 态 ``self._budget is None`` → ``{}``，
            # 前端须容忍空 dict。
            "budget": self._budget_summary(),
        }
        if self._status in _SNAPSHOT_TERMINAL_STATUSES:
            units = self._unit_counts()
            payload["total"] = units["total"]
            payload["completed"] = units["completed_units"]
            payload["failed"] = units["failed_units"]
        if self._diagnostics:
            payload["diagnostics"] = dict(self._diagnostics)
        return payload

    def _graph_node_projection(self, state: NodeState) -> dict:
        """一个节点的 bounded 图投影（决策 4：显式挑字段）。

        ``reason`` 的截断在**这里**做（grill 决策 1）：``state.reason`` 可能取到完整
        异常文本（``_run_node`` 的 except 分支 + ``envelope["reason"]`` 两条链），
        而它是 ``_envelope`` 的字段、本体不能改——所以 bounded 由投影层保证。
        """
        node: dict[str, Any] = {
            "id": state.node.id,
            "kind": state.node.kind,
            "status": self._projected_status(state),
            "runs": state.runs,
            "summary": (state.summary or "")[:_SUMMARY_LIMIT],
            "reason": (state.reason or "")[:_SUMMARY_LIMIT] or None,
            "task": (state.node.task or "")[:_SUMMARY_LIMIT],
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            # 失败计数（change fix-issue-215 Q6 方案 D）：**一个有界整数**，不是证据
            # 列表——证据本身在 transcript 载荷里（「对话」tab 才取），这里只给
            # 「这个绿节点里面有没有工具失败」的线索，供「任务」tab 零请求地渲染一行。
            # 三态：``None`` = 没数据（不显示）、``0`` = 已检查无失败、``N`` = N 条。
            # 计数在 ``_launch_run`` 的终态点算好存进 ``NodeState``，这里只读取。
            "failure_count": state.failure_count,
        }
        if state.node.kind == "route":
            # route 的选中出口是控制边高亮的唯一信号（决策 6）。``verdict``/``raw``
            # 是父 Agent 诊断口径，不进快照。
            node["targets"] = list(state.targets)
        if state.node.kind == "foreach":
            # 折叠组的项数（决策 8）：展开项从来不是 ``NodeState``，只体现在这里。
            node["items"] = state.items
            if state.items is not None:
                # 项还没解析出来（容器未派发）时不发项级字段：``0/0 完成`` 比不发
                # 更糟——它会让人以为「派发过了，一项都没成功」。
                self._add_item_projection(node, state)
        elif state.node.id.startswith(AUTO_NODE_PREFIX):
            # 自动插层节点仍带 ``items``（#190 的既有口径），但**不带**项级计数与
            # ``item_states``——它永不经过 ``_execute_foreach``，恒显「0/3 完成」
            # 是自相矛盾的数据（M2.2）。
            node["items"] = state.items
        return node

    def _projected_status(self, state: NodeState) -> str:
        """节点状态的**投影层**修正（G3/M2.6：不动状态机、不多推一帧）。

        ``NodeState.status`` 从不写 ``queued``，而 ``_dispatch`` 在拿到 slot **之前**
        就置 ``started``（真正 ``_acquire_slot()`` 在 ``_launch_run`` 内部）。所以
        「等 slot」与「真正在跑」在图上同形：``_dispatch_capacity`` 是 25，最多 25
        个节点同时显示 running，其中 20 个其实在排队。

        **绝不给 ``NodeState.status`` 加 ``queued`` 赋值**：全仓 ``"queued"`` 只在
        读取侧判据出现，给写入点会让它们同时激活，其中一处参与 ``_in_flight_nodes``
        类收敛判断——预算 drain 正靠「在跑的 run 归零」落终态。
        """
        if state.status != "started":
            return state.status
        if state.subagent_id is None or state.run_id is None:
            return state.status
        run = self.manager.find_run(state.subagent_id, state.run_id)
        if run is not None and run.status == "queued":
            return "queued"
        return state.status

    def _add_item_projection(self, node: dict[str, Any], state: NodeState) -> None:
        """foreach 的 per-item 投影（G7/M2.2）：状态数组 + 三个派生计数。

        ``item_states`` 在投影时**现算**「已派发但未终态」的那一刻状态（排队 vs
        真正在跑），终态由 done 回调落盘——两者合起来才是权威 per-item 状态。
        """
        states: list[str] = []
        running = 0
        for index, recorded in enumerate(state.item_states):
            if recorded in _ITEM_TERMINAL_STATES:
                states.append(recorded)
                continue
            slot = state.item_runs[index] if index < len(state.item_runs) else None
            live = "pending" if slot is None else self._item_live_status(slot)
            if live == "running":
                running += 1
            states.append(live)
        node["item_states"] = states
        node["items_running"] = running
        node["items_completed"] = state.items_completed
        node["items_failed"] = state.items_failed

    def _edge_status(self, edge: WorkflowEdge) -> str:
        """边六档状态（决策 7 + Q5；第 6 档 ``satisfied`` 见 issue #207）。

        口径（优先级即语义，先命中先返回）：

        1. 控制边：route 已 ``completed`` 且 ``edge.target ∈ state.targets`` → ``passed``；
           其余（含「route completed 但 targets 被 ``_reset_subtree`` 清空的瞬时态」）
           → ``inactive``。
        2. 数据边被下游消费过（``_consumed_edges`` 记账）→ ``passed``。
        3. 目标 ``blocked``/``budget_exceeded``，或源 ``failed``/``cancelled`` → ``blocked``。
        4. 源或目标在跑 → ``active``。
        5. 源 ``completed`` 且目标仍 ``pending`` → ``ready``。
        6. **（change ``workflow-gate-only-edge-status``）** ``required`` 边 + 源
           ``completed`` + 目标**已越过 pending**（且非 ``skipped``）→ ``satisfied``
           （依赖已满足，但上游产出未被下游读取）。
        7. 兜底 ``inactive``。

        ``satisfied`` 的意义（issue #207）：区分「这条边起了门控作用、只是没传数据」
        与「这条边真的没参与」——两者此前都落兜底 ``inactive``（灰），用户看到
        `scan→fan`（fan 用字面 items、不读 scan 产出）会以为是条死线。
        """
        source = self._states.get(edge.source)
        target = self._states.get(edge.target)
        if self._plan is not None and self._plan.is_control_edge(edge):
            if source is None or source.status != "completed":
                return "inactive"
            return "passed" if edge.target in source.targets else "inactive"
        if (edge.source, edge.target) in self._consumed_edges:
            return "passed"
        if target is not None and target.status in _EDGE_BLOCKED_TARGET_STATUSES:
            return "blocked"
        if source is not None and source.status in _EDGE_BLOCKED_SOURCE_STATUSES:
            return "blocked"
        if (source is not None and source.status == "started") or (
            target is not None and target.status == "started"
        ):
            return "active"
        if (
            source is not None
            and source.status == "completed"
            and (target is None or target.status == "pending")
        ):
            return "ready"
        # ``satisfied``：依赖已满足（源 completed、目标已被放行并越过 pending），
        # 但产出没被读走（未被 ``_consumed_edges`` 记到，规则 2 没命中）。
        # 排除 ``skipped``：目标不跑是**控制边**决定的，这条数据边从未门控过派发
        # （grill Q1 用户拍板 B），标它会让「产出未被下游读取」变成假话。
        # ``source/target`` 的 None 是防御性分支——真实图不可达（_states 由
        # plan.nodes 构造、边端点解析期已校验），省掉它一旦发生就是 AttributeError
        # 打断整张图的快照推送（grill 决策 2）。
        if (
            source is not None
            and target is not None
            and edge.required
            and source.status == "completed"
            and target.status != "pending"
            and target.status != "skipped"
        ):
            return "satisfied"
        return "inactive"

    def _envelope(self, *, status: str) -> dict:
        plan = self._plan
        nodes = [
            self._states[node.id].to_dict() for node in (plan.nodes if plan else ())
        ]
        # 旧 run 计数字段：语义不动（C2 的 24 处断言依赖 completed/failed 的 run 口径）。
        completed = sum(
            1
            for ref in self._run_refs
            if getattr(ref, "status", None) == "completed"
        )
        failed = sum(
            1
            for ref in self._run_refs
            if getattr(ref, "status", None) in ("failed", "cancelled", "budget_exceeded")
        )
        units = self._unit_counts()
        finished_at = self._finished_at or time.time()
        payload: dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "spec_hash": self._spec.spec_hash if self._spec else None,
            "goal": self._spec.goal if self._spec else "",
            "status": status,
            "nodes": nodes,
            "completed": completed,
            "failed": failed,
            # 逻辑执行单元计数（Q2）：``total`` 是分母，其余是各终态桶 + pending。
            "total": units["total"],
            "cancelled": units["cancelled_units"],
            "budget_exceeded": units["budget_exceeded_units"],
            "blocked": units["blocked_units"],
            "pending": units["pending_units"],
            # 事件 ring buffer（Q5）：最近 5 次终态迁移，不用 bus 填。
            "latest_events": list(self._latest_events),
            "root_result_ref": self._root_result_ref,
            # 四维成本归因（D7）：bounded 摘要 + 落盘 ref（完整账单按需 Read）。
            "attribution": self._attribution_summary(),
            "attribution_ref": self._attribution_ref,
            "steps": self._steps,
            "peak_active": self._peak_active,
            "critical_path_s": round(finished_at - self._started_at, 6) if self._started_at else 0.0,
            "total_cost": round(self._ledger_total() - self._cost_before, 9),
            # 编排质量指标（change ``benchmark-workflow-replay``，D4）。
            # ``run_count`` 用 ``_run_refs``（只含派发成功的 run）——**不要**用
            # ``completed + failed``（漏掉被取消且未登记的 run），更不要用
            # ``self._runs``（派发前**预扣**的累计值，可能大于实际派发数，
            # 见 ``_budget_summary`` 的 docstring，Confirmed Decision 7）。
            "run_count": len(self._run_refs),
            "queue_wait_s": self._queue_wait_s(),
            "queue_cancelled_runs": self._queue_cancelled_runs(),
            "queue_full_runs": self._queue_full_runs,
            "graph_recursion_exceeded": self._graph_recursion_runs,
            "useful_runs": len(self._consumed_run_ids),
            "redundancy": self._redundancy(),
            "rejected_runs": self._rejected_runs(),
            "depth_capped_runs": self._rejection_counts_snapshot.get("depth_capped", 0),
            "spawn_budget_rejected": self._rejection_counts_snapshot.get("spawn_budget", 0),
            # spawn 快照（Q2/Confirmed Decision 7）：必须在 run() finally 释放桶之前取，
            # 释放后 ``manager.spawn_count()`` 会退化成 manager 生命周期计数。
            "workflow_spawn_count": self._spawn_count_snapshot,
            # 四维度预算快照（D7）：与顶层既有的 int 键 ``budget_exceeded`` 共存，
            # 语义不同、不得互相覆盖（Confirmed Decision 7）。
            "budget": self._budget_summary(),
            "started_at": self._started_at,
            "finished_at": finished_at,
            "current_nodes": [
                state.node.id for state in self._states.values() if state.status in ("queued", "started")
            ],
            "diagnostics": dict(self._diagnostics),
        }
        if plan is not None:
            # 三 hash 分离（Q3）：声明哈希是 replay 锚点，运行期哈希随自动插层变化。
            payload["declared_spec_hash"] = plan.declared_spec_hash
            payload["expansion_plan_hash"] = plan.expansion_plan_hash
            payload["runtime_graph_hash"] = plan.runtime_graph_hash
            payload["inserted_nodes"] = list(plan.inserted_nodes)
        if self.bus is not None:
            payload["bus"] = self.bus.snapshot_payload()
        return payload

    def parent_envelope(self) -> dict:
        """父 agent 面向的 **bounded** 投影（D3；review Issue 4）。

        与 ``status()``/``_envelope()`` 的关系：

        - ``_envelope()`` 是**权威** envelope，供 ``run()`` 返回值与 C2 断言使用
          （保留全量 ``nodes`` 与 per-node ``subagent_ids``，grill 决策 4 明确不能替换）。
        - 本方法是**父 agent 实际看到的东西**（工具返回），必须真的 bounded：bus 是
          非权威通道、不进这里（D4 自洽）；节点只保留 bounded 摘要（不展开
          ``slots``/全量 ``summary``/``subagent_ids``/``run_ids`` 这些随图规模线性增长的
          字段）；节点条数设硬上限，超出部分用 ``nodes_omitted`` 显式报告——不静默截断。
        """
        payload = self._envelope(status=self._status)
        # bus 是非权威广播通道（D4）：它不属于权威 envelope，也不该出现在父上下文里。
        payload.pop("bus", None)

        nodes = payload.get("nodes", [])
        total = len(nodes)
        visible = nodes[:_PARENT_NODES_LIMIT]
        payload["nodes"] = [_bounded_node(node) for node in visible]
        payload["nodes_total"] = total
        payload["nodes_omitted"] = max(total - _PARENT_NODES_LIMIT, 0)
        return payload

    def _write_root_result(self) -> None:
        """把根结果落盘并记录 ``root_result_ref``（D3：父 agent 只看 ref）。

        ``collect`` 聚合不产生 run（没有 per-run artifact），所以根结果是**工作流级
        落盘件**：取终态节点里最后一条有内容的 summary。落盘失败不影响 workflow 完成。
        """
        plan = self._plan
        if plan is None:
            return
        candidates = list(plan.terminal) or [node.id for node in plan.nodes]
        text = ""
        for node_id in candidates:
            state = self._states.get(node_id)
            if state is not None and (state.summary or "").strip():
                text = state.summary
                # 终态产出进了根结果也算一次消费（Q2）。
                self._mark_consumed(state)
        if not text:
            text = "\n\n".join(
                state.summary
                for state in self._states.values()
                if (state.summary or "").strip()
            )
        if not text:
            return
        try:
            self._root_result_ref = self._workflow_store().save_result("root", text)
        except Exception:  # noqa: BLE001 - 落盘是尽力而为的可观测性
            logger.warning("Failed to persist workflow root result", exc_info=True)



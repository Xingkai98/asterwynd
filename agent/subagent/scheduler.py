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
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from agent.subagent.bus import MessageBus
from agent.subagent.context import reset_bus, reset_node_id, reset_workflow_id, set_bus, set_node_id, set_workflow_id
from agent.subagent.workflow import (
    REDUCERS,
    WorkflowNode,
    WorkflowSpec,
    WorkflowValidationError,
)

if TYPE_CHECKING:
    from agent.subagent.manager import SubAgentManager, SubagentRunRecord

# 节点状态机（D3）。``queued``/``started`` 是「已派发、未终态」的两个子态。
NODE_STATUSES = ("pending", "queued", "started", "completed", "failed", "cancelled", "blocked")

# 终态节点状态：汇合门控只看这些。
TERMINAL_NODE_STATUSES = frozenset({"completed", "failed", "cancelled", "blocked"})

# Run 终态（与 manager.TERMINAL_RUN_STATUSES 同口径 + queue_full 这个「从未发生」态）。
TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "budget_exceeded", "queue_full"}
)

# ``_await_run`` 的轮询间隔：调度器与 run 任务同事件循环，靠让出调度来观察取消。
_POLL_INTERVAL_S = 0.01

_SUMMARY_LIMIT = 400


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
    #: 该节点的数据上游重跑后置位；在途节点跑完再被复位成 pending
    stale: bool = False
    verdict: str | None = None
    raw: str | None = None
    targets: list[str] = field(default_factory=list)
    items: int | None = None
    error: str | None = None

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
            payload["slots"] = dict(self.slots)
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
    """结构化标签匹配：大小写无关的整体词匹配，不做表达式求值。"""
    if not verdict or not label:
        return False
    return label.strip().upper() in verdict.upper()


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
        self._states: dict[str, NodeState] = {}
        self._cancelled = False
        self._cancel_event = asyncio.Event()
        self._progress = asyncio.Event()
        self._steps = 0
        self._runs = 0
        self._expanded_nodes = 0
        self._in_flight_runs = 0
        self._in_flight_nodes = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._route_counts: dict[str, int] = {}
        self._run_refs: list[Any] = []
        #: node_id -> 仍在跑的 (subagent_id, run_id)，取消路径据此找到 in-flight run
        self._live_runs: dict[str, list[tuple[str, str]]] = {}
        #: foreach 节点 id -> NodeState，供展开项派发时登记 run id
        self._foreach_state: dict[str, NodeState] = {}
        self._peak_active = 0
        self._started_at = 0.0
        self._finished_at: float | None = None
        self._status = "declared"
        #: False 之后调度器不再接受新的派发/复位（取消或图级超限后）
        self._accepting = True
        self._diagnostics: dict[str, Any] = {}
        self._cost_before = 0.0

    # -- 生命周期 -----------------------------------------------------------

    @property
    def spec(self) -> WorkflowSpec | None:
        return self._spec

    @spec.setter
    def spec(self, value: WorkflowSpec) -> None:
        """Attach the parsed spec before ``StartWorkflow`` drives the graph (D1)."""
        self._spec = value
        self._states = {node.id: NodeState(node=node) for node in value.nodes}
        self._expanded_nodes = len(value.nodes)

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
        self._states = {node.id: NodeState(node=node) for node in spec.nodes}
        self._expanded_nodes = len(spec.nodes)
        self._status = "running"
        self._started_at = time.time()
        self._cost_before = self._ledger_total()
        bus = self.bus or MessageBus()
        self.bus = bus
        self.manager.register_workflow_bucket(self.workflow_id, spec.max_runs * 2)
        try:
            await self._drive(raise_on_recursion=raise_on_recursion)
        finally:
            await self._teardown()
            self.manager.release_workflow_bucket(self.workflow_id)
            self._finished_at = time.time()
        return self.status()

    async def _teardown(self) -> None:
        """取消/收尾所有仍在途的节点任务，并标记未派发节点为 blocked。"""
        self._accepting = False
        for state in self._states.values():
            if state.status in ("queued", "started"):
                await self._cancel_node(state)
                if state.status in ("queued", "started"):
                    state.status = "cancelled"
            elif state.status == "pending":
                state.status = "blocked"
                state.reason = state.reason or "workflow ended before the node became ready"
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
                if dispatched == 0 and self._in_flight_nodes == 0:
                    # 没有可派发的节点、也没有在途节点：图已收敛（或存在不可达节点）。
                    self._status = "completed"
                    return
                await self._wait_for_progress()
        except GraphRecursionError as exc:
            self._accepting = False
            await self._cancel_all_in_flight()
            self._diagnostics = exc.to_dict()
            self._status = "graph_recursion_exceeded"
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

    # -- 就绪与派发 ---------------------------------------------------------

    def _data_deps_satisfied(self, state: NodeState) -> bool:
        spec = self._spec
        assert spec is not None
        for edge in spec.data_incoming(state.node.id):
            if not edge.required:
                continue
            upstream = self._states.get(edge.source)
            if upstream is None or upstream.status not in TERMINAL_NODE_STATUSES:
                return False
        return True

    def _has_control_incoming(self, node_id: str) -> bool:
        spec = self._spec
        assert spec is not None
        return any(spec.is_control_edge(edge) for edge in spec.incoming(node_id))

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
        return bool(self._spec and node_id in self._spec.entry)

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
        cost = self._run_cost(state.node)
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
        for edge in spec.data_outgoing(state.node.id):
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
        except Exception as exc:  # noqa: BLE001 - 节点失败不 fail-fast（D4）
            state.status = "failed"
            state.error = f"{type(exc).__name__}: {exc}"
            state.reason = state.reason or state.error
        finally:
            if state.finished_at is None:
                state.finished_at = time.time()
            self._in_flight_nodes -= 1
            self._on_node_finished(state)
            self._progress.set()

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
        spec = self._spec
        assert spec is not None
        for edge in spec.data_outgoing(state.node.id):
            successor = self._states.get(edge.target)
            if successor is None:
                continue
            if successor.status in TERMINAL_NODE_STATUSES:
                self._reset_subtree(successor)
            elif successor.status in ("queued", "started"):
                successor.stale = True

    def _reset_subtree(self, state: NodeState) -> None:
        """数据上游重跑 → 下游必须用新输入重跑（同一 session 复用）。"""
        if state.status == "pending":
            return
        state.status = "pending"
        state.stale = False
        state.activations = 0
        state.deadline_fired = False
        state.verdict = None
        state.targets = []
        spec = self._spec
        assert spec is not None
        for edge in spec.data_outgoing(state.node.id):
            successor = self._states.get(edge.target)
            if successor is not None:
                self._reset_subtree(successor)

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
        # collect：纯逻辑聚合，不产生 run（completed 只数真实 run）
        state.summary = merged or "\n".join(str(value) for value in state.slots.values())
        state.subagent_id = None
        state.run_id = None
        state.status = "completed"

    async def _execute_route(self, state: NodeState) -> None:
        """Q8：route 只匹配结构化标签/受限枚举，不执行任何模型生成代码。"""
        node = state.node
        raw = self._route_verdict(state)
        matched: str | None = None
        for case in node.cases:
            if matches_route(raw, case.when):
                matched = case.when
                state.targets = [case.to]
                break
        else:
            state.targets = [node.default] if node.default else []
        # ``verdict`` 是命中的结构化标签（default 分支为 None），``raw`` 是上游原文，
        # 便于诊断「为什么走了这条边」而不把整段产出塞回父上下文。
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
                self._reset_subtree(successor)

    async def _execute_foreach(self, state: NodeState) -> None:
        node = state.node
        self._foreach_state[node.id] = state
        items = self._resolve_items(state)
        state.items = len(items)
        state.subagent_id = None
        state.run_ids = []
        state.subagent_ids = []
        summaries: list[str] = []
        failures = 0
        for index, item in enumerate(items):
            if self._cancelled:
                state.status = "cancelled"
                return
            task_text = render_item_task(node.task, item, index=index)
            await self._acquire_slot()
            if self._cancelled:
                self._release(1)
                state.status = "cancelled"
                return
            state.run_ids.append(None)  # type: ignore[arg-type]
            envelope = await self._launch_run(
                node=node,
                task=task_text,
                mode=node.mode,
                reuse_state=None,
                session_name=f"{node.id}-{index}",
            )
            state.subagent_ids.append(envelope["subagent_id"])
            state.run_ids[-1] = envelope["run_id"]
            state.runs += 1
            summaries.append(envelope.get("summary", "") or "")
            if envelope["status"] != "completed":
                failures += 1
            self._release(1)
        state.summary = "\n".join(summaries)
        if items and failures == len(items):
            state.status = "failed"
            state.reason = "all foreach items failed"
        elif failures:
            state.status = "completed"
            state.reason = f"{failures}/{len(items)} foreach items did not complete"
        else:
            state.status = "completed"

    # -- run 派发（身份 contextvar 的唯一 set 点） ---------------------------

    async def _launch_run(
        self,
        *,
        node: WorkflowNode,
        task: str,
        mode: str | None,
        reuse_state: NodeState | None,
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
            )
        finally:
            reset_bus(token_bus)
            reset_node_id(token_node)
            reset_workflow_id(token_workflow)
        run_id = launched["run_id"]
        self._run_refs.append(manager._sessions[subagent_id].runs[-1])
        # 派发即登记：取消路径要能在 run 终态之前找到它。foreach 节点没有单一
        # session，所以只登记 live 列表，不写回 state.subagent_id（它是 None）。
        if reuse_state is not None:
            reuse_state.subagent_id = reuse_state.subagent_id or subagent_id
            reuse_state.run_id = run_id
        self._live_runs.setdefault(node.id, []).append((subagent_id, run_id))
        self._refresh_peak()
        if launched["status"] == "queue_full":
            # Q2：准入背压保证不出现；真出现时按失败记录，绝不静默丢。
            return {"subagent_id": subagent_id, "run_id": run_id, **launched}
        terminal = await self._await_run(subagent_id, run_id)
        self._live_runs.get(node.id, []).remove((subagent_id, run_id))
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
                return manager._format_run_envelope(subagent_id, run)  # type: ignore[arg-type]
            self._refresh_peak()
            await asyncio.sleep(_POLL_INTERVAL_S)

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
            for edge in spec.data_incoming(node.id):
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
        live = list(self._live_runs.get(state.node.id, []))
        if state.subagent_id is not None and state.run_id is not None:
            live.append((state.subagent_id, state.run_id))
        seen: set[tuple[str, str]] = set()
        for subagent_id, run_id in live:
            if (subagent_id, run_id) in seen:
                continue
            seen.add((subagent_id, run_id))
            try:
                await self.manager.cancel_subagent_run(
                    subagent_id=subagent_id, run_id=run_id
                )
            except Exception:  # noqa: BLE001 - 取消是尽力而为
                continue

    async def _acquire_slot(self) -> None:
        """背压门：在途 run 数达到 max_active + max_queued_runs 时让出调度。"""
        capacity = self._dispatch_capacity()
        cost = 1
        while self._in_flight_runs + cost > capacity:
            if self._cancelled:
                return
            self._progress.clear()
            await self._progress.wait()
        self._in_flight_runs += cost
        self._runs += cost

    # -- 槽 / 任务文本 -------------------------------------------------------

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
        spec = self._spec
        assert spec is not None
        reducer = "concat"
        for edge in spec.data_incoming(state.node.id):
            if edge.reducer:
                reducer = edge.reducer
                break
        return aggregate_slots(list(contributions.values()), reducer)

    def _collect_slots(self, state: NodeState) -> dict[str, str]:
        """按槽聚合每个数据上游的产出（每节点取最新一次 run，Q9/D7）。"""
        spec = self._spec
        assert spec is not None
        groups: dict[str, list[str]] = {}
        reducers: dict[str, str] = {}
        for edge in spec.data_incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None or upstream.status not in TERMINAL_NODE_STATUSES:
                continue
            for slot in upstream.node.outputs:
                value = self._node_output(upstream, slot)
                if value is None:
                    continue
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
        for edge in (self._spec.data_incoming(state.node.id) if self._spec else ()):
            upstream = self._states.get(edge.source)
            if upstream is not None and slot in upstream.slots:
                return upstream.slots[slot]
        return state.summary or None

    def _node_task_text(self, node: WorkflowNode) -> str:
        """subagent 节点的任务文本 = 节点 task + 上游产出（如果有）。"""
        spec = self._spec
        assert spec is not None
        parts = [node.task]
        goal = spec.goal
        if goal and goal not in node.task:
            parts.append(f"Overall goal: {goal}")
        for edge in spec.data_incoming(node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            text = self._node_output(upstream, edge_slots(edge)[0])
            if text:
                parts.append(f"Input from {edge.source}:\n{text}")
        return "\n\n".join(parts)

    def _aggregate_task_text(self, state: NodeState) -> str:
        spec = self._spec
        assert spec is not None
        parts = [state.node.task or f"Aggregate the results of {spec.goal or 'the workflow'}."]
        for slot, value in state.slots.items():
            parts.append(f"Slot {slot}:\n{value}")
        return "\n\n".join(parts)

    def _route_verdict(self, state: NodeState) -> str:
        """route 的判定文本 = 所有数据上游产出的拼接（只做标签匹配）。"""
        spec = self._spec
        assert spec is not None
        parts: list[str] = []
        for edge in spec.data_incoming(state.node.id):
            upstream = self._states.get(edge.source)
            if upstream is None:
                continue
            text = self._node_output(upstream, edge_slots(edge)[0])
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _resolve_items(self, state: NodeState) -> list[Any]:
        node = state.node
        if node.items is not None:
            items = list(node.items)
        else:
            source = self._states.get(node.source or "")
            value = self._node_output(source, node.source_field or "result") if source else None
            items = extract_collection(value, node.source_field)
        return items[: node.max_items]

    # -- 度量 ---------------------------------------------------------------

    def _ledger_total(self) -> float:
        ledger = getattr(self.manager, "cost_ledger", None)
        if ledger is None:
            return 0.0
        try:
            return float(ledger.total())
        except Exception:  # noqa: BLE001
            return 0.0

    def _refresh_peak(self) -> None:
        # Q9：peak_active = 本 workflow 内并发执行的 run 数（不被同 manager 其他
        # pattern 污染），因此从自己的 run record 里统计，而非许可池占用。
        running = sum(1 for run in self._run_refs if run.status == "running")
        self._peak_active = max(self._peak_active, running)

    def _envelope(self, *, status: str) -> dict:
        nodes = [self._states[node.id].to_dict() for node in (self._spec.nodes if self._spec else ())]
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
        finished_at = self._finished_at or time.time()
        payload: dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "spec_hash": self._spec.spec_hash if self._spec else None,
            "goal": self._spec.goal if self._spec else "",
            "status": status,
            "nodes": nodes,
            "completed": completed,
            "failed": failed,
            "steps": self._steps,
            "peak_active": self._peak_active,
            "critical_path_s": round(finished_at - self._started_at, 6) if self._started_at else 0.0,
            "total_cost": round(self._ledger_total() - self._cost_before, 9),
            "started_at": self._started_at,
            "finished_at": finished_at,
            "current_nodes": [
                state.node.id for state in self._states.values() if state.status in ("queued", "started")
            ],
            "diagnostics": dict(self._diagnostics),
        }
        if self.bus is not None:
            payload["bus"] = self.bus.snapshot_payload()
        return payload


def edge_slots(edge: Any) -> tuple[str, ...]:
    """边所承载的槽名（由源节点声明；默认单槽 ``result``）。"""
    return ("result",)

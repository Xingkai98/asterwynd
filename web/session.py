# web/session.py
"""Session manager: one AgentLoop + message history per browser session."""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalResponse,
)
from agent.question import Question, QuestionAnswer
from agent.config import (
    DEFAULT_APPROVAL_TIMEOUT_SECONDS,
    DEFAULT_QUESTION_TIMEOUT_SECONDS,
    AsterwyndConfig,
)
from agent.loop import AgentLoop
from agent.message import Message, extract_text
from agent.mcp import build_mcp_manager
from agent.run_identity import new_session_id
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.session import SessionSnapshot, SessionStore
from agent.skills import SkillRuntime
from agent.subagent.manager import SubAgentManager
from agent.tools.factory import build_default_tool_registry, build_sandbox_from_config
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.hooks.builtin import TracingHook
from web.debug_hook import DebugHook

logger = logging.getLogger("asterwynd.web.session")


def build_history_payload(session: "AgentSession") -> dict:
    """把 session 的消息历史序列化为前端可渲染的文本事件。

    历史消息的 content 用 ``extract_text`` 提取纯文本（图片 block 无文本则
    略过），供恢复连接后前端渲染，避免前端拿到内部 block 结构。

    从快照恢复的会话在首次 run 前 ``session.messages`` 为空，历史还在
    ``resume_snapshot.messages``（恢复上下文由 AgentLoop 首次 run 时重建），
    因此这里回退用快照历史渲染。
    """
    if not session.messages and session.resume_snapshot is not None:
        messages = session.resume_snapshot.messages
    else:
        messages = session.messages
    return {
        "type": "session_history",
        "data": {
            "session_id": session.session_id,
            "messages": [
                {"role": message.role, "content": extract_text(message.content)}
                for message in messages
            ],
        },
    }


def build_timeline_payload(session: "AgentSession") -> dict:
    """Shape a session's tool-call timeline for the debug UI.

    Reuses the TracingHook's per-execution records (``tool_name``,
    ``duration_ms``, ``success``). In-flight entries (``duration_ms == 0``,
    pre-set by ``before_tool_execute``) are filtered out; settled calls are
    returned sorted by duration descending with the original execution ``index``
    preserved and a ``bar_pct`` width for the frontend. All shaping lives in the
    backend so it is unit-testable; the frontend only renders.
    """
    hook = next(
        (h for h in session.agent.hooks.hooks if isinstance(h, TracingHook)),
        None,
    )
    calls = hook.calls if hook is not None else []
    settled = [(i, c) for i, c in enumerate(calls) if c.duration_ms > 0]
    if not settled:
        return {
            "session_id": session.session_id,
            "total_calls": 0,
            "max_duration_ms": 0.0,
            "calls": [],
        }
    max_duration = max(c.duration_ms for _, c in settled)
    ordered = sorted(settled, key=lambda ic: ic[1].duration_ms, reverse=True)
    return {
        "session_id": session.session_id,
        "total_calls": len(ordered),
        "max_duration_ms": max_duration,
        "calls": [
            {
                "index": orig_index,
                "tool_name": c.tool_name,
                "duration_ms": c.duration_ms,
                "success": c.success,
                "arguments": c.arguments,
                "bar_pct": round(c.duration_ms / max_duration * 100, 1),
            }
            for orig_index, c in ordered
        ],
    }


# pending 交互超时缺省直接取 ``WebConfig`` 的单一来源常量（Q1/D6），避免 600/300
# 在 config 与 session 两处各自漂移（见 ``__init__`` 的 timeout_seconds 默认值）。


@dataclass
class _PendingInteraction:
    """一条等待用户响应的 pending 交互：稳定 id + future + 可重放载荷。

    ``payload`` 是建立时的 ``to_event_data()`` 快照，供 WebSocket 重连补发；
    它与 id 存在同一对象里，读取时一次取整条记录，不存在「读到 id、读不到载荷」
    的中间态（M7）。
    """

    interaction_id: str
    future: asyncio.Future
    payload: dict


class WebApprovalHandler:
    def __init__(
        self,
        session_id: str,
        *,
        timeout_seconds: float | None = DEFAULT_APPROVAL_TIMEOUT_SECONDS,
    ):
        self.session_id = session_id
        #: 总等待时长（秒）；``None`` 表示不设超时（仅供测试/特殊场景）。
        self.timeout_seconds = timeout_seconds
        self._pending: _PendingInteraction | None = None

    @property
    def pending_approval_id(self) -> str | None:
        if self._pending is None:
            return None
        return self._pending.interaction_id

    def pending_approval_payload(self) -> tuple[str, dict] | None:
        """原子返回 ``(approval_id, payload)`` 快照；无 pending 时返回 ``None``。

        已 resolve（作答/超时/fail_pending）的 pending 不再算 pending——即使
        ``_pending`` 尚未在 ``finally`` 里清空，也不能被补发出去（终态单向推进）。
        """
        pending = self._pending
        if pending is None or pending.future.done():
            return None
        return pending.interaction_id, dict(pending.payload)

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        if self._pending is not None:
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,
                reason="another approval request is already pending",
            )
        future: asyncio.Future[ApprovalResponse] = asyncio.get_running_loop().create_future()
        self._pending = _PendingInteraction(
            interaction_id=request.approval_id,
            future=future,
            payload=request.to_event_data(),
        )
        try:
            if self.timeout_seconds is None:
                return await future
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            # fail-closed：超时绝不等于「同意」，绝不放行不可逆操作（调研 finding 7/8）。
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,
                reason=f"approval timed out after {self.timeout_seconds}s",
            )
        finally:
            if self._pending is not None and self._pending.interaction_id == request.approval_id:
                self._pending = None

    def submit_response(self, approval_id: str, decision: str) -> bool:
        if self._pending is None or self._pending.interaction_id != approval_id:
            return False
        future = self._pending.future
        if future.done():
            return False
        normalized = decision.strip().lower()
        if normalized in {"approved", "approve", "allow", "yes", "y"}:
            status = ApprovalDecisionStatus.APPROVED
            reason = "approved by web user"
        else:
            status = ApprovalDecisionStatus.DENIED
            reason = "denied by web user"
        future.set_result(
            ApprovalResponse(
                approval_id=approval_id,
                status=status,
                reason=reason,
            )
        )
        return True

    def fail_pending(self, reason: str) -> None:
        pending = self._pending
        if pending is None:
            return
        if not pending.future.done():
            pending.future.set_result(
                ApprovalResponse(
                    approval_id=pending.interaction_id,
                    status=ApprovalDecisionStatus.UNAVAILABLE,
                    reason=reason,
                )
            )


class WebQuestionHandler:
    def __init__(
        self,
        session_id: str,
        *,
        timeout_seconds: float | None = DEFAULT_QUESTION_TIMEOUT_SECONDS,
    ):
        self.session_id = session_id
        self.timeout_seconds = timeout_seconds
        self._pending: _PendingInteraction | None = None
        self._event_sender = None

    def set_event_sender(self, sender):
        self._event_sender = sender

    @property
    def pending_question_id(self) -> str | None:
        return self._pending.interaction_id if self._pending else None

    def pending_question_payload(self) -> tuple[str, dict] | None:
        """原子返回 ``(question_id, payload)`` 快照；无 pending 时返回 ``None``。"""
        pending = self._pending
        if pending is None or pending.future.done():
            return None
        return pending.interaction_id, dict(pending.payload)

    async def ask_question(self, question: Question) -> QuestionAnswer:
        if self._pending is not None:
            return QuestionAnswer(
                question_id=question.question_id,
                answer="[Error: another question is already pending]",
            )
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending = _PendingInteraction(
            interaction_id=question.question_id,
            future=future,
            payload=question.to_event_data(),
        )
        if self._event_sender:
            self._event_sender({"type": "user_question", "data": question.to_event_data()})
        try:
            if self.timeout_seconds is None:
                return await future
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            return QuestionAnswer(
                question_id=question.question_id,
                answer=f"[Error: question timed out after {self.timeout_seconds}s]",
            )
        finally:
            if self._pending and self._pending.interaction_id == question.question_id:
                self._pending = None

    def submit_answer(self, question_id: str, answer: str) -> bool:
        if self._pending is None or self._pending.interaction_id != question_id:
            return False
        future = self._pending.future
        if future.done():
            return False
        future.set_result(QuestionAnswer(question_id=question_id, answer=answer))
        return True

    def fail_pending(self, reason: str) -> None:
        pending = self._pending
        if pending is None:
            return
        if not pending.future.done():
            pending.future.set_result(
                QuestionAnswer(
                    question_id=pending.interaction_id,
                    answer=f"[Error: {reason}]",
                )
            )


class ConnectionHandle:
    """一条 WebSocket 连接在 session 事件出口上的句柄（D3）。

    出口按句柄而不是裸 callable 管理连接：per-connection detach（M2）与定点发送
    （M3，run 占用错误只回发起连接）都需要「能定位到具体连接」。``detach()``
    是幂等的，重复调用不报错。
    """

    def __init__(self, send, *, label: str = ""):
        self.send = send
        self.label = label
        self._channel: "SessionEventChannel | None" = None
        self._detached = False

    @property
    def detached(self) -> bool:
        return self._detached

    def detach(self) -> None:
        """把本连接从事务出口摘掉（幂等）。"""
        self._detached = True
        channel = self._channel
        if channel is not None:
            channel.detach(self)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"ConnectionHandle(label={self.label!r}, detached={self._detached})"


class SessionEventChannel:
    """session 级、跨 run 存活的 run 事件出口（D3/D7）。

    与 ``GraphEventForwarder`` 的区别：

    - forwarder 的 sink 语义是「同步、绝不抛、失败即丢 + 按 workflow 分桶合并」，
      适合可观测性的图快照；run 事件需要**顺序投递**与 per-connection 失败感知，
      因此单独实现而不是把合并逻辑硬塞进 run 事件路径。
    - 出口支持**多订阅者广播**（D7）：同一 session 的多 tab / 多设备都收到事件，
      某条连接断开只把自己摘掉，不影响其他连接。``GraphEventForwarder.rebind``
      是最后连接胜出，沿用会导致第二个 tab 抢走第一个的事件流。
    - ``send_to`` 提供**定点发送**：``run_session`` 早期返回的「另一个 run 正在
      执行」错误只回发起连接，走广播会让别的 tab 莫名出现错误消息（M3）。

    ``broadcast`` 永不抛：单条连接失败只摘该连接，drain 循环因此可以「永不退出、
    永远消费 queue」（M2），断连期间事件被丢弃而不是无界堆积。
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._handles: list[ConnectionHandle] = []

    @property
    def handles(self) -> tuple[ConnectionHandle, ...]:
        return tuple(self._handles)

    def __len__(self) -> int:
        return len(self._handles)

    def attach(self, handle: ConnectionHandle) -> ConnectionHandle:
        if handle._channel is self and not handle.detached:
            return handle
        if handle not in self._handles:
            self._handles.append(handle)
        handle._channel = self
        handle._detached = False
        return handle

    def detach(self, handle: ConnectionHandle) -> None:
        try:
            self._handles.remove(handle)
        except ValueError:
            pass
        handle._detached = True

    def detach_all(self) -> None:
        """session 被移除（reset / hub DELETE）时统一摘掉所有连接（M11/D8）。"""
        for handle in self._handles:
            handle._detached = True
            handle._channel = None
        self._handles.clear()

    async def broadcast(self, payload: dict) -> int:
        """把事件投给当前所有已绑定连接，返回成功条数。永不抛。"""
        delivered = 0
        for handle in list(self._handles):
            if handle.detached:
                continue
            try:
                await handle.send(payload)
                delivered += 1
            except Exception as exc:  # noqa: BLE001 - 断连只是这条连接没了，绝不能打断 run
                logger.info(
                    "session %s: sender dropped (%s): %s",
                    self.session_id,
                    handle.label or "ws",
                    exc,
                )
                self.detach(handle)
        return delivered

    async def send_to(self, handle: ConnectionHandle | None, payload: dict) -> bool:
        """定点发送给一条连接（M3）。句柄不可用时返回 ``False``，不抛。"""
        if handle is None or handle.detached:
            return False
        try:
            await handle.send(payload)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "session %s: point send failed (%s): %s",
                self.session_id,
                handle.label or "ws",
                exc,
            )
            self.detach(handle)
            return False


def fail_pending_interactions(session: "AgentSession", reason: str) -> None:
    """立刻把该 session 的全部 pending 交互判失败（reset/cancel/run 结束）。"""
    session.approval_handler.fail_pending(reason)
    session.question_handler.fail_pending(reason)


async def route_interaction_message(
    session: "AgentSession",
    raw: dict,
    channel: SessionEventChannel,
    *,
    handle: ConnectionHandle | None = None,
) -> bool:
    """把一条客户端消息路由给 session 的 pending 交互（Q3：所有路径共用一份逻辑）。

    返回 ``True`` 表示已处理；``False`` 表示不属于交互消息，调用方自行处理。

    终态一律经 ``channel`` 广播：run 存活时（``agent/loop.py`` 发终态）与 run
    不在时的 inline 回执必须行为一致，不能出现「run 活着其他端卡片失效、run
    结束其他端卡片停在 pending」的不一致（grill Q3）。
    """
    msg_type = raw.get("type")
    if msg_type == "approval_response":
        approval_id = str(raw.get("approval_id", "")).strip()
        decision = str(raw.get("decision", "")).strip()
        accepted = session.approval_handler.submit_response(approval_id, decision)
        await _deliver_interaction_receipt(
            channel,
            handle,
            accepted=accepted,
            payload={
                "type": "approval_response",
                "data": {
                    "approval_id": approval_id,
                    "status": "received" if accepted else "unavailable",
                    "reason": "received" if accepted else "no matching pending approval",
                    "session_id": session.session_id,
                },
            },
        )
        return True
    if msg_type == "user_answer":
        question_id = str(raw.get("question_id", "")).strip()
        answer = str(raw.get("answer", "")).strip()
        accepted = session.question_handler.submit_answer(question_id, answer)
        await _deliver_interaction_receipt(
            channel,
            handle,
            accepted=accepted,
            payload={
                "type": "user_answer",
                "data": {
                    "question_id": question_id,
                    "status": "received" if accepted else "unavailable",
                    "session_id": session.session_id,
                },
            },
        )
        return True
    if msg_type == "ping":
        await channel.send_to(handle, {"type": "pong"})
        return True
    return False


async def _deliver_interaction_receipt(
    channel: SessionEventChannel,
    handle: ConnectionHandle | None,
    *,
    accepted: bool,
    payload: dict,
) -> None:
    """投递作答回执：**被接受**的广播给所有连接，**被拒绝**的只回提交者。

    为什么区别对待（终态单调，调研 finding 8 / design Risks）：广播「被拒绝」的回执
    会把**已经收到终态**的连接也改写掉——先答者胜出后，落败者在另一个 tab 再点一次，
    所有连接（含胜出方）都会收到 `unavailable`，前端把胜出方卡片从「approved」改成
    「unavailable」，用户看到「自己批准过的卡片被判为不可用」，而工具其实已经执行。
    被拒绝的回执是「你这条提交没有生效」的**定向错误应答**，不是该审批的状态变更，
    因此只回提交者；被接受的才是全 session 共享的终态，按 Q3 广播（run 内 / run 外
    两条路径都走这里，行为一致）。
    """
    if accepted or handle is None:
        await channel.broadcast(payload)
        return
    await channel.send_to(handle, payload)


def build_pending_interaction_payloads(session: "AgentSession") -> list[dict]:
    """ws 重连补发的 pending 交互卡片列表（tasks 3.1/D4）。

    读取两个 handler 的**原子快照**（``(id, payload)`` 一次取整条记录），因此不会
    读到「有 id 无载荷」的中间态（M7）。已作答/已超时/已失败的 pending 不在此列
    （handler 侧按 future.done() 过滤），守住「已决请求不重放」的安全线。

    提问与审批在同一 session 内互斥（同一时刻最多一个 pending），顺序不影响语义。
    """
    payloads: list[dict] = []
    # 访问器返回的已经是载荷副本（见 ``pending_*_payload``），直接在其上补 session_id。
    question = session.question_handler.pending_question_payload()
    if question is not None:
        _, data = question
        data["session_id"] = session.session_id
        payloads.append({"type": "user_question", "data": data})
    approval = session.approval_handler.pending_approval_payload()
    if approval is not None:
        _, data = approval
        data["session_id"] = session.session_id
        payloads.append({"type": "approval_request", "data": data})
    return payloads


#: 快照合并的时间窗（Q4）：窗内同一 workflow 只保留**最新**一帧。
GRAPH_SNAPSHOT_WINDOW_S = 0.1


def _is_terminal_snapshot(data: dict) -> bool:
    """终态快照要**立即**发（Q4），不参与时间窗合并。

    ``running``/``declared`` 是过程态；其余（``completed``/``failed``/``cancelled``/
    ``budget_exceeded``/``graph_recursion_exceeded``）都是图停下的状态。
    """
    from agent.subagent.scheduler import _SNAPSHOT_TERMINAL_STATUSES

    return data.get("status") in _SNAPSHOT_TERMINAL_STATUSES


class GraphEventForwarder:
    """session 级 workflow 图事件出口（Q1 方案 A + Q4 合并 + Q11 隔离）。

    为什么不能复用 ``web/session.py`` 的 per-run queue（决策 3）：那个 queue 是
    ``_run_session_locked`` 的函数局部变量，消费者是同函数内的 drain 循环——父 run
    一结束 drain 就退出。``StartWorkflow(wait=false)`` 起的后台图在父 run 返回后仍在
    跑，往那个 queue 里 put 没人消费，快照全丢。

    本对象**持有 session 而非某次 run 的 queue**，因此跨 run 存活；``rebind()`` 让
    ws 重连把新的 ``ws_send`` 接上同一个 forwarder（Q1 的实现细节：重连走
    ``resume_session_async`` 命中内存 session，拿到的是同一个 ``AgentSession``）。

    两个硬约束：

    - **永不抛**（Q11）：send 异常一律吞掉。调用点全在节点任务的调用栈里，漏出去
      会被 ``_run_node`` 的 ``except Exception`` 吞成「节点 failed」。
    - **按 workflow 分桶合并**（Q4）：窗内只留每个 workflow 的最新快照，避免一张
      50 节点图推 150 次、3–4 MB 出流量。
    """

    def __init__(
        self,
        *,
        session_id: str,
        ws_send=None,
        window_s: float = GRAPH_SNAPSHOT_WINDOW_S,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.session_id = session_id
        self._ws_send = ws_send
        self._window_s = window_s
        self._loop = loop
        #: workflow_id -> 待发快照（合并缓冲，只留最新）
        self._pending: dict[str, dict] = {}
        #: 每个 workflow 的定时 flush 任务（窗口到点自动送出）
        self._flush_handles: dict[str, asyncio.TimerHandle] = {}
        #: 在途发送任务（``flush()`` 等它们收尾；失败已被 ``_swallow`` 吞掉）
        self._in_flight: set[asyncio.Task] = set()
        self._detached = False

    # -- 绑定生命周期 -------------------------------------------------------

    def rebind(self, ws_send) -> None:
        """ws 重连：把新的 ``ws_send`` 接上同一个 forwarder（Q1）。"""
        self._ws_send = ws_send
        self._detached = False

    def detach(self) -> None:
        """``reset`` 路径摘掉 sender（Q1）：之后的事件静默丢弃。"""
        self._detached = True
        self._ws_send = None
        for handle in self._flush_handles.values():
            handle.cancel()
        self._flush_handles.clear()
        self._pending.clear()

    # -- sink 接口（scheduler 调用，必须同步返回、绝不抛） ------------------

    def __call__(self, event_type: str, data: dict) -> None:
        try:
            payload = self._build_payload(event_type, data)
            if payload is None:
                return
            if event_type == "workflow_started" or _is_terminal_snapshot(data):
                # 「开一张新图」与「图停下」都不能被合并吃掉（Q4：终态立即发）。
                # 终态还要**顶掉**该 workflow 的待发过程态：一帧更旧的 running 快照
                # 绝不能排在终态之后到达（前端会把图倒退回 running）。
                self._drop_pending(payload["data"].get("workflow_id"))
                self._send_now(payload)
                return
            self._queue_coalesced(payload)
        except Exception:  # noqa: BLE001 - 可观测性通道绝不打断执行（Q11）
            logger.debug("graph event dropped", exc_info=True)

    def _build_payload(self, event_type: str, data: dict) -> dict | None:
        if self._detached or self._ws_send is None:
            return None
        if not isinstance(data, dict):
            return None
        # Q8：沿用既有两层形状 ``{"type": ..., "data": {...}}``，归属字段进 ``data``。
        payload = dict(data)
        payload["session_id"] = self.session_id
        payload.setdefault("timestamp", time.time())
        return {"type": event_type, "data": payload}

    # -- 合并缓冲（Q4） -----------------------------------------------------

    def _queue_coalesced(self, payload: dict) -> None:
        workflow_id = str(payload["data"].get("workflow_id") or "")
        self._pending[workflow_id] = payload
        if workflow_id in self._flush_handles:
            return
        handle = self._get_loop().call_later(self._window_s, self._flush_one, workflow_id)
        self._flush_handles[workflow_id] = handle

    def _drop_pending(self, workflow_id) -> None:
        """丢弃某个 workflow 的待发快照与其定时 flush（被更新的帧取代）。"""
        key = str(workflow_id or "")
        handle = self._flush_handles.pop(key, None)
        if handle is not None:
            handle.cancel()
        self._pending.pop(key, None)

    def _flush_one(self, workflow_id: str) -> None:
        self._flush_handles.pop(workflow_id, None)
        payload = self._pending.pop(workflow_id, None)
        if payload is not None:
            self._send_now(payload)

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:  # 无事件循环的同步上下文
                self._loop = asyncio.get_event_loop()
        return self._loop

    def _send_now(self, payload: dict) -> None:
        """送出：``ws_send`` 是 async callable，这里 fire-and-forget。

        失败一律吞（Q11）。用 ``ensure_future`` 而不是 await——scheduler 的 sink
        调用点是同步的，且推送绝不能让节点任务等待网络。
        """
        send = self._ws_send
        if send is None or self._detached:
            return
        try:
            result = send(payload)
        except Exception:  # noqa: BLE001 - 同步抛出的 send 同样吞掉
            logger.debug("graph event send failed", exc_info=True)
            return
        if asyncio.iscoroutine(result):
            task = asyncio.ensure_future(result)
            self._in_flight.add(task)
            task.add_done_callback(self._in_flight.discard)
            task.add_done_callback(self._swallow)

    @staticmethod
    def _swallow(task: "asyncio.Task") -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.debug("graph event send failed: %s", exc)

    # -- 测试/收尾用的显式 flush -------------------------------------------

    async def flush(self) -> None:
        """清空合并缓冲并等待在途发送（测试与 agent 收尾用）。"""
        for workflow_id in list(self._pending):
            self._flush_one(workflow_id)
        while self._in_flight:
            await asyncio.gather(*list(self._in_flight), return_exceptions=True)


def build_workflow_resume_payloads(manager, *, session_id: str) -> list[dict]:
    """ws 重连补发的快照列表（Q2/Q9）。

    口径（用户确认）：**当前 running + 最近 5 张终态**，按 ``started`` property
    过滤掉仅 ``DeclareWorkflow`` 未启动的图（``declared`` 态不该出现在列表里）。

    排序：注册表 ``_workflows`` 是 Python dict（保序），终态图按**插入序取最后 5 张**
    ——「最近」在这里是「最后注册」的近似（Q9 已确认该口径）。
    """
    from agent.subagent.scheduler import _SNAPSHOT_TERMINAL_STATUSES

    running: list[dict] = []
    terminal: list[dict] = []
    for workflow_id in manager.list_workflows():
        scheduler = manager.get_workflow(workflow_id)
        if scheduler is None or not getattr(scheduler, "started", False):
            continue
        try:
            data = scheduler.workflow_graph_snapshot()
        except Exception:  # noqa: BLE001 - 补发是尽力而为
            logger.debug("workflow resume snapshot failed for %s", workflow_id, exc_info=True)
            continue
        data["session_id"] = session_id
        payload = {"type": "workflow_snapshot", "data": data}
        if data.get("status") in _SNAPSHOT_TERMINAL_STATUSES:
            terminal.append(payload)
        else:
            running.append(payload)
    return running + terminal[-5:]


class AgentSession:
    """Holds one AgentLoop instance and its message history."""

    def __init__(
        self,
        session_id: str,
        agent: AgentLoop,
        approval_handler: WebApprovalHandler | None = None,
        question_handler: WebQuestionHandler | None = None,
    ):
        self.session_id = session_id
        self.agent = agent
        self.approval_handler = approval_handler or WebApprovalHandler(session_id)
        self.question_handler = question_handler or WebQuestionHandler(session_id)
        self.messages: list[Message] = []
        self.debug_turn = 0
        # 从持久化快照恢复的会话持有快照，仅在第一次 run 时传给 AgentLoop
        # 作为 resume_snapshot（AgentLoop 会把历史上下文灌回 messages）。
        self.resume_snapshot: SessionSnapshot | None = None
        # 会话归属的 workspace（issue #117）：决定 WorkspacePolicy 根与
        # SessionStore 归属；创建/恢复时设置，reset 沿用。
        self.workspace_root: Path | None = None
        # per-session run 互斥（issue #117 D8）：同一 session 并发 run 被拒，
        # 避免两个 WebSocket 并发驱动同一 AgentLoop 污染共享可变状态。
        self.run_lock: asyncio.Lock = asyncio.Lock()
        # workflow 图事件出口（change ``workflow-graph-visualization``，Q1 方案 A）：
        # session 级、跨 run 存活。在 ``_create_session`` 里装到该 session 的
        # ``SubAgentManager.graph_sink`` 上；ws 连上/重连时 ``rebind()``。
        self.graph_forwarder: GraphEventForwarder | None = None
        # run 事件出口（change ``web-reconnect-pending-interaction``，D3/D7）：
        # session 级、跨 run 存活，支持多连接广播与定点发送。ws 连上时 attach，
        # 断开只 detach 该连接、不终止 run。
        self.event_channel = SessionEventChannel(session_id)

    @property
    def current_mode(self) -> str:
        return self.agent.runtime_state.current_mode.value

    def init_messages(self, system_prompt: Optional[str] = None):
        if system_prompt:
            self.agent._user_system_prompt = system_prompt


class SessionManager:
    """Creates and manages AgentSession instances."""

    def __init__(
        self,
        debug_enabled: bool = False,
        mode: str | None = None,
        config: AsterwyndConfig | None = None,
        workspace_root: Path | None = None,
        allowed_workspaces: list[Path] | None = None,
    ):
        self._sessions: dict[str, AgentSession] = {}
        self.debug_enabled = debug_enabled
        self.config = config or AsterwyndConfig()
        self.workspace_root = workspace_root
        # 主 workspace：CLI --workspace 或启动目录（CLI 同语义）。
        self.primary_workspace = (workspace_root or Path.cwd()).resolve()
        # allowlist 中 resolve 后存在的路径（已排除不存在项，create_app 打 warning）。
        self._allowlist = [w.resolve() for w in (allowed_workspaces or [])]
        # 有效 workspace 集合 = {主 workspace} ∪ allowlist，启动时一次性解析。
        self._workspace_set = {self.primary_workspace, *self._allowlist}
        resolved_mode = mode or self.config.agent.default_mode.value
        self.initial_mode = parse_agent_mode(resolved_mode)
        # per-workspace SessionStore：key 为 resolve 后的绝对路径（issue #117 D3）。
        self._stores: dict[str, SessionStore] = {}

    def _store_for(self, workspace_root: Path | None) -> SessionStore:
        """按 workspace 解析 SessionStore，惰性创建。

        key 用 resolve() 规范化后的绝对路径（None → cwd.resolve()），避免同一
        目录因写法不同产生多个 store。
        """
        key = str((workspace_root or Path.cwd()).resolve())
        store = self._stores.get(key)
        if store is None:
            store = SessionStore(str(Path(key) / ".asterwynd" / "sessions"))
            self._stores[key] = store
        return store

    def resolve_workspace(self, workspace: str | Path | None) -> Path:
        """统一校验用户可控 workspace 输入（issue #117 D4）。

        None/空 → 主 workspace；否则 expanduser().resolve() 后校验落入有效
        集合，否则抛 ValueError（结构化拒绝）。覆盖 /api/sessions、/ws/new、
        /ws/{id}?workspace= 全部入口，防 .. 穿越 / 符号链接 / 尾部斜杠。
        """
        if workspace is None or workspace == "":
            return self.primary_workspace
        resolved = Path(str(workspace)).expanduser().resolve()
        if resolved not in self._workspace_set:
            raise ValueError("workspace_not_allowed")
        return resolved

    def create_session(self, llm, tools: Optional[list] = None) -> AgentSession:
        if self.config.mcp.servers:
            raise RuntimeError("create_session with MCP config requires create_session_async")
        return self._create_session(llm, tools=tools, mcp_manager=None)

    async def create_session_async(
        self,
        llm,
        tools: Optional[list] = None,
        *,
        mode: str | None = None,
        workspace_root: Path | None = None,
    ) -> AgentSession:
        """创建新 session，可指定 mode 与 workspace（issue #117 D2/D3）。

        mode/workspace 缺省回落 manager 初始 mode / 主 workspace。
        """
        mcp_manager = await build_mcp_manager(self.config)
        initial_mode = parse_agent_mode(mode) if mode else None
        return self._create_session(
            llm,
            tools=tools,
            mcp_manager=mcp_manager,
            initial_mode=initial_mode,
            workspace_root=workspace_root,
        )

    async def resume_session_async(
        self,
        session_id: str,
        llm,
        tools: Optional[list] = None,
        *,
        workspace: str | Path | None = None,
    ) -> Optional[AgentSession]:
        """按 id 恢复 session：内存命中直接复用，否则从持久化快照重建。

        workspace 显式传入（hub 列表 / URL ?workspace=）→ 用该 workspace 的
        store 恢复；未传 → 按确定顺序（主 → allowlist 配置序）搜索，首个命中
        即恢复。快照也不存在时返回 None，由调用方回退新建。返回的 session
        持有 ``resume_snapshot``，首次 run 时传给 AgentLoop 恢复上下文。

        归属闭环（issue #117 D3）：命中哪个 store，就用该 workspace 创建
        session（workspace_root / WorkspacePolicy / _store_for 均用命中值），
        保证恢复后的会话下次 run 仍落盘回原 workspace。
        """
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        if workspace is not None:
            ws = self.resolve_workspace(workspace)
            snapshot = self._store_for(ws).load(session_id)
            if snapshot is None:
                return None
            return await self._restore_snapshot(snapshot, ws, llm, tools)
        for ws in self._search_order():
            snapshot = self._store_for(ws).load(session_id)
            if snapshot is not None:
                logger.info("Resumed session %s from store %s", session_id, ws)
                return await self._restore_snapshot(snapshot, ws, llm, tools)
        return None

    async def _restore_snapshot(
        self,
        snapshot: SessionSnapshot,
        workspace_root: Path,
        llm,
        tools: Optional[list],
    ) -> AgentSession:
        mcp_manager = await build_mcp_manager(self.config)
        # 不预填 session.messages：恢复的历史由 AgentLoop 首次 run 时从
        # resume_snapshot 重建（_run 的 resume 分支），避免快照历史重复入参。
        # session_history 渲染由 build_history_payload 回退到 resume_snapshot。
        session = self._create_session(
            llm,
            tools=tools,
            mcp_manager=mcp_manager,
            initial_mode=snapshot.mode,
            resume_snapshot=snapshot,
            workspace_root=workspace_root,
        )
        logger.info("Resumed session %s from store", snapshot.session_id)
        return session

    def _search_order(self) -> list[Path]:
        """确定性搜索顺序：主 workspace → allowlist 配置序（去重）。"""
        order = [self.primary_workspace]
        for ws in self._allowlist:
            if ws not in order:
                order.append(ws)
        return order

    def list_workspaces(self) -> list[tuple[Path, bool]]:
        """有序 workspace 列表：(path, is_primary)，主 workspace 置顶 + allowlist。

        供 hub ``GET /api/workspaces`` 使用。
        """
        items = [(self.primary_workspace, True)]
        for ws in self._allowlist:
            if ws != self.primary_workspace:
                items.append((ws, False))
        return items

    def _create_session(
        self,
        llm,
        tools: Optional[list] = None,
        mcp_manager=None,
        *,
        initial_mode: Optional[AgentMode] = None,
        resume_snapshot: Optional[SessionSnapshot] = None,
        workspace_root: Path | None = None,
    ) -> AgentSession:
        session_id = resume_snapshot.session_id if resume_snapshot else new_session_id()
        # pending 交互超时（change web-reconnect-pending-interaction, Q1/D6）：
        # 走 ``WebConfig``，两项都必须可配置（正整数校验在 ``_parse_web_config``）。
        approval_handler = WebApprovalHandler(
            session_id,
            timeout_seconds=self.config.web.approval_timeout_seconds,
        )
        question_handler = WebQuestionHandler(
            session_id,
            timeout_seconds=self.config.web.question_timeout_seconds,
        )
        resolved_mode = initial_mode or self.initial_mode
        run_config = AgentRunConfig(mode=resolved_mode)
        session_workspace = (
            (workspace_root or self.primary_workspace).resolve()
        )
        workspace_policy = WorkspacePolicy(
            workspace_root=session_workspace,
            command_denylist=self.config.tools.command_denylist,
        )
        sandbox = build_sandbox_from_config(self.config)
        registry = build_default_tool_registry(
            policy=workspace_policy,
            mode_policy=ModePolicy(
                run_config,
                deny_tools_by_mode=self.config.deny_tools_by_mode(),
                permission_profiles_by_mode=self.config.permission_profiles_by_mode(),
            ),
            ignore_patterns=self.config.tools.ignore_patterns,
            code_intelligence_config=self.config.tools.code_intelligence,
            web_search_config=self.config.tools.web_search,
            browser_config=self.config.tools.browser,
            mcp_manager=mcp_manager,
            tools=tools,
            selection_config=self.config.tools.selection,
            sandbox=sandbox,
        )
        subagent_manager = SubAgentManager(
            llm=llm,
            config=self.config,
            workspace_policy=workspace_policy,
            parent_mode=run_config.mode,
            sandbox=sandbox,
        )
        skill_runtime = SkillRuntime.from_roots(self.config.skills.roots)

        agent = AgentLoop(
            llm=llm,
            tool_registry=registry,
            hooks=HookManager([TracingHook()]),
            memory=MemoryManager(max_tokens=80_000),
            subagent_manager=subagent_manager,
            expose_subagent_tools=True,
            run_config=run_config,
            tool_result_display=self.config.tools.display,
            skill_runtime=skill_runtime,
            approval_handler=approval_handler,
            question_handler=question_handler,
            mcp_manager=mcp_manager,
            session_store=self._store_for(session_workspace),
        )
        session = AgentSession(session_id, agent, approval_handler, question_handler)
        session.workspace_root = session_workspace
        # manager 与 session 1:1（Q1）：给该 session 的 manager 装 session 级 sender。
        # sender 持有 session 而非某次 run 的 queue，因此 ``wait=false`` 的后台图在
        # 父 run 结束后仍能推快照（决策 3）。
        forwarder = GraphEventForwarder(session_id=session_id)
        session.graph_forwarder = forwarder
        subagent_manager.graph_sink = forwarder
        if resume_snapshot is not None:
            session.resume_snapshot = resume_snapshot
            session.init_messages(resume_snapshot.user_system_prompt)
        else:
            session.init_messages()
        self._sessions[session_id] = session
        logger.info(f"Created session {session_id} workspace={session_workspace}")
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str, workspace: str | Path | None = None):
        session = self._sessions.pop(session_id, None)
        # Q1：session 被移除（reset / hub DELETE）时摘掉 sender，避免后台 workflow
        # 继续往一个已死 session 的 ws 推事件。
        if session is not None and session.graph_forwarder is not None:
            session.graph_forwarder.detach()
            session.graph_forwarder = None
        # D8/M11：run 事件出口随 session 一起清理，否则旧 ws sender 仍被 session 引用。
        if session is not None:
            session.event_channel.detach_all()
        # workspace 显式传入（hub DELETE 端点，冷会话常态）→ 用该 workspace 的
        # store 删快照；缺省（reset 路径）→ 回退内存 session 的 workspace_root。
        if workspace is not None:
            ws = self.resolve_workspace(workspace)
            self._store_for(ws).remove(session_id)
        elif session is not None and session.workspace_root is not None:
            self._store_for(session.workspace_root).remove(session_id)
        else:
            self._store_for(self.primary_workspace).remove(session_id)

    async def set_mode(self, session: AgentSession, mode: str) -> dict:
        return await session.agent.set_mode(
            mode,
            source="web",
            session_id=session.session_id,
        )

    async def run_session(
        self,
        session: AgentSession,
        user_message: str,
        ws_send=None,
        ws_receive=None,
        images: list[dict] | None = None,
        *,
        handle: ConnectionHandle | None = None,
    ) -> None:
        """Run the agent with user message, streaming events via the session channel.

        同一 session 并发 run 互斥（issue #117 D8）：锁被占用时回发 error
        事件并返回，不阻塞 WS 连接；成功则整个 run 流程（含 queue drain）都
        在锁内，避免两个 WebSocket 并发驱动同一 AgentLoop。

        ``handle`` 是发起本次 run 的连接（``websocket_endpoint`` 传入，已在
        session 的 ``event_channel`` 上 attach）。直接调用（测试/内嵌）时可只传
        ``ws_send``，此时临时造一个句柄挂在同一个出口上，run 结束后摘掉；两者都
        不传表示「本次 run 没有发起连接」，事件广播给出口上已有的连接（可能为空，
        广播退化为丢弃，不报错）。
        """
        channel = session.event_channel
        transient_handle: ConnectionHandle | None = None
        if handle is None and ws_send is not None:
            transient_handle = channel.attach(ConnectionHandle(ws_send, label="transient"))
            handle = transient_handle
        try:
            # Python 3.12 的 asyncio.Lock 无 acquire_nowait；wait_for(timeout=0)
            # 会因 acquire 的调度延迟误判（锁可用也超时）。改用 locked() 检查 +
            # acquire()：asyncio 单线程事件循环下，locked() 检查与 acquire() 的
            # 锁设置之间无 await 点（acquire 对可用锁是同步路径），故无
            # check-then-act 竞态；锁被占用时在 if 直接拒绝，不会走到 acquire
            # 阻塞（区别于 async with 写法）。
            if session.run_lock.locked():
                # 定点发送（M3）：跑到别的 tab 的 DOM 里会让用户看到莫名其妙的错误。
                # ``code`` 供前端映射成用户可读文案（Q4）。
                await channel.send_to(handle, {
                    "type": "error",
                    "data": {
                        "message": "another run is already in progress",
                        "code": "run_in_progress",
                    },
                })
                return
            await session.run_lock.acquire()
            try:
                await self._run_session_locked(
                    session, user_message, channel, handle, ws_receive, images
                )
            finally:
                session.run_lock.release()
        finally:
            if transient_handle is not None:
                channel.detach(transient_handle)

    async def _receive_interactions(
        self,
        session: AgentSession,
        ws_receive,
        channel: SessionEventChannel,
        handle: ConnectionHandle | None,
    ) -> None:
        """消费本连接的消息直到断开；断开只退出本循环，不失败 pending（D2/D3）。

        断连检测点唯一（M2）：``websocket_endpoint`` 在 ``await run_session`` 期间
        不会调用 ``ws.receive_json()``，FastAPI 不会抛 ``WebSocketDisconnect``——这里
        的 ``await ws_receive()`` 抛异常就是唯一可靠的断连信号。

        **循环不因单条畸形消息退出**：``receive_json`` 对非 JSON 文本帧抛
        ``JSONDecodeError``，那不是「连接没了」。把两者混为一谈会把仍然活着的连接从
        出口摘掉，run 后续事件全丢（客户端界面停在半截）。因此解码失败只记录并继续
        下一条；只有 ``ws_receive`` 真的抛（连接层异常）才 detach 退出。
        """
        while True:
            try:
                raw = await ws_receive()
            except asyncio.CancelledError:
                raise
            except (
                json.JSONDecodeError,   # 文本帧不是合法 JSON
                UnicodeDecodeError,     # 文本帧不是合法 UTF-8
                KeyError,               # 二进制帧：starlette 文本模式取 message["text"]
            ) as exc:
                # 畸形帧 ≠ 断连：这条连接还活着，只是客户端发了一条我们没法当消息读的东西。
                logger.info("ignoring malformed frame from client: %s", exc)
                continue
            except Exception as exc:  # noqa: BLE001 - 断开不是用户放弃，绝不能 fail_pending
                logger.info("interaction receiver stopped: %s", exc)
                if handle is not None:
                    handle.detach()
                return
            if not isinstance(raw, dict):
                logger.info(
                    "ignoring non-object frame from client: %r", type(raw).__name__
                )
                continue
            if not await route_interaction_message(session, raw, channel, handle=handle):
                msg_type = raw.get("type")
                if msg_type in {"reset", "cancel"}:
                    fail_pending_interactions(session, f"{msg_type} received")

    async def _run_session_locked(
        self,
        session: AgentSession,
        user_message: str,
        channel: SessionEventChannel,
        handle: ConnectionHandle | None,
        ws_receive=None,
        images: list[dict] | None = None,
    ) -> None:
        """``run_session`` 的锁内实现：实际驱动 AgentLoop 与 queue drain。"""
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event_type: str, data: dict):
            await queue.put({"type": event_type, "data": data})

        # Wire question handler's event sender to the queue
        session.question_handler.set_event_sender(
            lambda event: queue.put_nowait(event)
        )

        # Add debug hook if debug is enabled
        if self.debug_enabled:
            session.debug_turn += 1
            debug_turn = session.debug_turn

            def emit_debug(event: dict):
                event = dict(event)
                event["turn"] = debug_turn
                queue.put_nowait(event)

            debug_hook = DebugHook(emit=emit_debug, force_enabled=True)
            session.agent.hooks.hooks.append(debug_hook)

        if images:
            from agent.message import TextBlock
            from agent.uploads import create_image_message, create_image_message_from_upload
            content_blocks: list = [TextBlock(text=user_message)] if user_message else []
            for img in images:
                upload_id = str(img.get("upload_id", "")).strip()
                if upload_id:
                    content_blocks.append(create_image_message_from_upload(upload_id))
                    continue
                data_url = str(img.get("url", ""))
                if data_url:
                    content_blocks.append(create_image_message(data_url))
            session.messages.append(Message(role="user", content=content_blocks if content_blocks else user_message))
        else:
            session.messages.append(Message(role="user", content=user_message))

        # Run agent in background, send queued events through websocket
        async def run_agent():
            try:
                await session.agent.run(
                    session.messages,
                    on_event=on_event,
                    session_id=session.session_id,
                    resume_snapshot=session.resume_snapshot,
                )
            except Exception as exc:
                logger.exception("Session run failed")
                await queue.put({
                    "type": "error",
                    "data": {"message": f"{type(exc).__name__}: {exc}"},
                })
                await queue.put({
                    "type": "done",
                    "data": {
                        "content": "",
                        "stop_reason": "error",
                    },
                })
            finally:
                # resume_snapshot 只消费一次：run 完成后恢复上下文已并入
                # session.messages，后续 run 不再重复恢复。
                session.resume_snapshot = None
                await queue.put(None)  # sentinel

        agent_task = asyncio.create_task(run_agent())
        receiver_task = None
        if ws_receive is not None:
            receiver_task = asyncio.create_task(
                self._receive_interactions(session, ws_receive, channel, handle)
            )

        try:
            # drain 永不退出、永远消费 queue（M2）：无绑定连接时事件被丢弃而不是
            # 无界堆积；单条连接 send 失败只摘该连接（channel.broadcast 内部处理），
            # SHALL NOT break、SHALL NOT cancel agent_task（D3）。
            while True:
                event = await queue.get()
                if event is None:
                    break
                await channel.broadcast(event)
        finally:
            # run 真正结束：pending 立即失败（既有语义，tasks 2.4）。断连走不到这里——
            # 断连只摘连接，run 继续跑到 sentinel。
            fail_pending_interactions(session, "session run ended")
            if receiver_task is not None and not receiver_task.done():
                receiver_task.cancel()
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass
            if not agent_task.done():
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass

        # Remove debug hook
        if self.debug_enabled:
            session.agent.hooks.hooks = [
                h for h in session.agent.hooks.hooks
                if not isinstance(h, DebugHook)
            ]

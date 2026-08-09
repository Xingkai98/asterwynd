# web/session.py
"""Session manager: one AgentLoop + message history per browser session."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalResponse,
)
from agent.question import Question, QuestionAnswer
from agent.config import AsterwyndConfig
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


class WebApprovalHandler:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._pending: tuple[str, asyncio.Future[ApprovalResponse]] | None = None

    @property
    def pending_approval_id(self) -> str | None:
        if self._pending is None:
            return None
        return self._pending[0]

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        if self._pending is not None:
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,
                reason="another approval request is already pending",
            )
        future: asyncio.Future[ApprovalResponse] = asyncio.get_running_loop().create_future()
        self._pending = (request.approval_id, future)
        try:
            return await future
        finally:
            if self._pending is not None and self._pending[0] == request.approval_id:
                self._pending = None

    def submit_response(self, approval_id: str, decision: str) -> bool:
        if self._pending is None or self._pending[0] != approval_id:
            return False
        future = self._pending[1]
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
        if self._pending is None:
            return
        approval_id, future = self._pending
        if not future.done():
            future.set_result(
                ApprovalResponse(
                    approval_id=approval_id,
                    status=ApprovalDecisionStatus.UNAVAILABLE,
                    reason=reason,
                )
            )


class WebQuestionHandler:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._pending: tuple[str, asyncio.Future] | None = None
        self._event_sender = None

    def set_event_sender(self, sender):
        self._event_sender = sender

    @property
    def pending_question_id(self) -> str | None:
        return self._pending[0] if self._pending else None

    async def ask_question(self, question: Question) -> QuestionAnswer:
        if self._pending is not None:
            return QuestionAnswer(
                question_id=question.question_id,
                answer="[Error: another question is already pending]",
            )
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending = (question.question_id, future)
        if self._event_sender:
            self._event_sender({"type": "user_question", "data": question.to_event_data()})
        try:
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            return QuestionAnswer(
                question_id=question.question_id,
                answer="[Error: question timed out after 5 minutes]",
            )
        finally:
            if self._pending and self._pending[0] == question.question_id:
                self._pending = None

    def submit_answer(self, question_id: str, answer: str) -> bool:
        if self._pending is None or self._pending[0] != question_id:
            return False
        _, future = self._pending
        if future.done():
            return False
        future.set_result(QuestionAnswer(question_id=question_id, answer=answer))
        return True

    def fail_pending(self, reason: str) -> None:
        if self._pending is None:
            return
        qid, future = self._pending
        if not future.done():
            future.set_result(
                QuestionAnswer(question_id=qid, answer=f"[Error: {reason}]")
            )


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
        approval_handler = WebApprovalHandler(session_id)
        question_handler = WebQuestionHandler(session_id)
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
        ws_send,
        ws_receive=None,
        images: list[dict] | None = None,
    ) -> None:
        """Run the agent with user message, streaming events via WebSocket.

        同一 session 并发 run 互斥（issue #117 D8）：锁被占用时回发 error
        事件并返回，不阻塞 WS 连接；成功则整个 run 流程（含 queue drain）都
        在锁内，避免两个 WebSocket 并发驱动同一 AgentLoop。
        """
        # Python 3.12 的 asyncio.Lock 无 acquire_nowait；wait_for(timeout=0)
        # 会因 acquire 的调度延迟误判（锁可用也超时）。改用 locked() 检查 +
        # acquire()：asyncio 单线程事件循环下，locked() 检查与 acquire() 的
        # 锁设置之间无 await 点（acquire 对可用锁是同步路径），故无
        # check-then-act 竞态；锁被占用时在 if 直接拒绝，不会走到 acquire
        # 阻塞（区别于 async with 写法）。
        if session.run_lock.locked():
            await ws_send({
                "type": "error",
                "data": {"message": "another run is already in progress"},
            })
            return
        await session.run_lock.acquire()
        try:
            await self._run_session_locked(
                session, user_message, ws_send, ws_receive, images
            )
        finally:
            session.run_lock.release()

    async def _run_session_locked(
        self,
        session: AgentSession,
        user_message: str,
        ws_send,
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

        async def receive_approval_responses():
            try:
                while True:
                    raw = await ws_receive()
                    msg_type = raw.get("type")
                    if msg_type == "approval_response":
                        approval_id = str(raw.get("approval_id", "")).strip()
                        decision = str(raw.get("decision", "")).strip()
                        accepted = session.approval_handler.submit_response(
                            approval_id,
                            decision,
                        )
                        if not accepted:
                            await queue.put({
                                "type": "approval_response",
                                "data": {
                                    "approval_id": approval_id,
                                    "status": "unavailable",
                                    "reason": "no matching pending approval",
                                    "session_id": session.session_id,
                                },
                            })
                        continue
                    if msg_type == "user_answer":
                        question_id = str(raw.get("question_id", "")).strip()
                        answer = str(raw.get("answer", "")).strip()
                        accepted = session.question_handler.submit_answer(question_id, answer)
                        await queue.put({
                            "type": "user_answer",
                            "data": {
                                "question_id": question_id,
                                "status": "received" if accepted else "unavailable",
                            },
                        })
                        continue
                    if msg_type in {"reset", "cancel"}:
                        session.approval_handler.fail_pending(
                            f"{msg_type} received while approval was pending"
                        )
                        session.question_handler.fail_pending(
                            f"{msg_type} received while question was pending"
                        )
                        continue
                    if msg_type == "ping":
                        await queue.put({"type": "pong"})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.info("Approval response receiver stopped: %s", exc)
                session.approval_handler.fail_pending("websocket disconnected")
                session.question_handler.fail_pending("websocket disconnected")

        if ws_receive is not None:
            receiver_task = asyncio.create_task(receive_approval_responses())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                await ws_send(event)
        finally:
            session.approval_handler.fail_pending("session run ended")
            session.question_handler.fail_pending("session run ended")
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

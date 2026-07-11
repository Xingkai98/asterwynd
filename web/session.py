# web/session.py
"""Session manager: one AgentLoop + message history per browser session."""
import asyncio
import logging
from typing import Optional

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalResponse,
)
from agent.config import AsterwyndConfig
from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.mcp import build_mcp_manager
from agent.run_identity import new_session_id
from agent.run_config import AgentRunConfig, ModePolicy, parse_agent_mode
from agent.skills import SkillRuntime
from agent.subagent.manager import SubAgentManager
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.hooks.builtin import TracingHook
from web.debug_hook import DebugHook

logger = logging.getLogger("asterwynd.web.session")


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


class AgentSession:
    """Holds one AgentLoop instance and its message history."""

    def __init__(
        self,
        session_id: str,
        agent: AgentLoop,
        approval_handler: WebApprovalHandler | None = None,
    ):
        self.session_id = session_id
        self.agent = agent
        self.approval_handler = approval_handler or WebApprovalHandler(session_id)
        self.messages: list[Message] = []
        self.debug_turn = 0

    @property
    def current_mode(self) -> str:
        return self.agent.runtime_state.current_mode.value

    def init_messages(self, system_prompt: Optional[str] = None):
        default_system = (
            "你是一个有用、诚实的人工智能助手。"
            "你可以调用工具来完成任务。"
        )
        self.messages.append(system_message(default_system))
        if system_prompt:
            self.messages.append(system_message(system_prompt))


class SessionManager:
    """Creates and manages AgentSession instances."""

    def __init__(
        self,
        debug_enabled: bool = False,
        mode: str | None = None,
        config: AsterwyndConfig | None = None,
    ):
        self._sessions: dict[str, AgentSession] = {}
        self.debug_enabled = debug_enabled
        self.config = config or AsterwyndConfig()
        resolved_mode = mode or self.config.agent.default_mode.value
        self.initial_mode = parse_agent_mode(resolved_mode)

    def create_session(self, llm, tools: Optional[list] = None) -> AgentSession:
        if self.config.mcp.servers:
            raise RuntimeError("create_session with MCP config requires create_session_async")
        return self._create_session(llm, tools=tools, mcp_manager=None)

    async def create_session_async(self, llm, tools: Optional[list] = None) -> AgentSession:
        mcp_manager = await build_mcp_manager(self.config)
        return self._create_session(llm, tools=tools, mcp_manager=mcp_manager)

    def _create_session(
        self,
        llm,
        tools: Optional[list] = None,
        mcp_manager=None,
    ) -> AgentSession:
        session_id = new_session_id()
        approval_handler = WebApprovalHandler(session_id)
        run_config = AgentRunConfig(mode=self.initial_mode)
        workspace_policy = WorkspacePolicy(
            command_denylist=self.config.tools.command_denylist,
        )
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
        )
        subagent_manager = SubAgentManager(
            llm=llm,
            config=self.config,
            workspace_policy=workspace_policy,
            parent_mode=run_config.mode,
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
            mcp_manager=mcp_manager,
        )
        session = AgentSession(session_id, agent, approval_handler)
        session.init_messages()
        self._sessions[session_id] = session
        logger.info(f"Created session {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str):
        self._sessions.pop(session_id, None)

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
        """Run the agent with user message, streaming events via WebSocket."""
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event_type: str, data: dict):
            await queue.put({"type": event_type, "data": data})

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
                    if msg_type in {"reset", "cancel"}:
                        session.approval_handler.fail_pending(
                            f"{msg_type} received while approval was pending"
                        )
                        continue
                    if msg_type == "ping":
                        await queue.put({"type": "pong"})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.info("Approval response receiver stopped: %s", exc)
                session.approval_handler.fail_pending("websocket disconnected")

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

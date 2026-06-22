# web/session.py
"""Session manager: one AgentLoop + message history per browser session."""
import asyncio
import logging
import uuid
from typing import Optional, AsyncGenerator

from agent.config import MyAgentConfig
from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.run_config import AgentRunConfig, ModePolicy, parse_agent_mode
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.hooks.builtin import TracingHook
from web.debug_hook import DebugHook

logger = logging.getLogger("myagent.web.session")


class AgentSession:
    """Holds one AgentLoop instance and its message history."""

    def __init__(self, session_id: str, agent: AgentLoop):
        self.session_id = session_id
        self.agent = agent
        self.messages: list[Message] = []
        self.debug_turn = 0

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
        config: MyAgentConfig | None = None,
    ):
        self._sessions: dict[str, AgentSession] = {}
        self.debug_enabled = debug_enabled
        self.config = config or MyAgentConfig()
        resolved_mode = mode or self.config.agent.default_mode.value
        self.run_config = AgentRunConfig(mode=parse_agent_mode(resolved_mode))

    def create_session(self, llm, tools: Optional[list] = None) -> AgentSession:
        session_id = uuid.uuid4().hex[:12]
        registry = build_default_tool_registry(
            policy=WorkspacePolicy(
                command_denylist=self.config.tools.command_denylist,
            ),
            mode_policy=ModePolicy(
                self.run_config,
                deny_tools_by_mode=self.config.deny_tools_by_mode(),
            ),
            ignore_patterns=self.config.tools.ignore_patterns,
            tools=tools,
        )

        agent = AgentLoop(
            llm=llm,
            tool_registry=registry,
            hooks=HookManager([TracingHook()]),
            memory=MemoryManager(max_tokens=80_000),
            run_config=self.run_config,
        )
        session = AgentSession(session_id, agent)
        session.init_messages()
        self._sessions[session_id] = session
        logger.info(f"Created session {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    async def run_session(
        self,
        session: AgentSession,
        user_message: str,
        ws_send,
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

        session.messages.append(Message(role="user", content=user_message))

        # Run agent in background, send queued events through websocket
        async def run_agent():
            try:
                await session.agent.run(session.messages, on_event=on_event)
            except Exception:
                logger.exception("Session run failed")
            finally:
                await queue.put(None)  # sentinel

        agent_task = asyncio.create_task(run_agent())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                await ws_send(event)
        finally:
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

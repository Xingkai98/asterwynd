"""Multi-turn TUI session controller.

The controller owns AgentLoop lifecycle, message history, session/run identity,
and renderable TUI state. It stays decoupled from Textual widgets.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING

from agent.commands.registry import CommandContext, CommandResult, SlashCommandRegistry
from agent.message import Message, system_message
from agent.run_identity import new_run_id
from agent.tui.reducer import TranscriptEntry, TUIState, reduce_tui_state

if TYPE_CHECKING:
    from agent.loop import AgentLoop

logger = logging.getLogger("asterwynd.tui.controller")


class TUIController:
    """TUI session controller.

    It owns AgentLoop, message history, session id, and TUI state. Each run gets
    a fresh run id and funnels runtime events through the TUI reducer.
    """

    def __init__(
        self,
        agent: AgentLoop,
        session_id: str,
        command_registry: SlashCommandRegistry,
    ) -> None:
        self.agent = agent
        self.session_id = session_id
        self.command_registry = command_registry
        self.state = TUIState(session_id=session_id)
        self.messages: list[Message] = []
        self.should_exit = False
        self._current_run_task: asyncio.Task | None = None

        # Initialize messages with system prompt
        self.messages.append(
            system_message(
                "你是一个有用、诚实的人工智能助手。"
                "你可以调用工具来完成任务。"
            )
        )

    @property
    def current_mode(self) -> str:
        return self.agent.runtime_state.current_mode.value

    def _init_state_for_run(self, run_id: str) -> None:
        """Reset run-scoped state before a new run starts."""
        self.state = reduce_tui_state(self.state, "run_started", {
            "mode": self.current_mode,
            "run_id": run_id,
            "session_id": self.session_id,
        })

    async def _handle_event(self, event_type: str, data: dict) -> None:
        """Reduce one runtime event into controller state."""
        self.state = reduce_tui_state(self.state, event_type, data)

    async def run_async(self, user_input: str) -> dict:
        """Run one AgentLoop turn asynchronously.

        Args:
            user_input: User input text.

        Returns:
            A dict containing session_id and run_id.
        """
        run_id = new_run_id()
        self._init_state_for_run(run_id)

        # Add the user message to both runtime history and TUI transcript.
        self.messages.append(Message(role="user", content=user_input))
        self.state = self.state.add_user_message(user_input)

        async def on_event(event_type: str, data: dict) -> None:
            await self._handle_event(event_type, data)

        self._current_run_task = asyncio.current_task()
        try:
            if "on_event" in inspect.signature(self.agent.run).parameters:
                result = await self.agent.run(
                    self.messages,
                    on_event=on_event,
                    session_id=self.session_id,
                    run_id=run_id,
                )
            else:
                result = await self.agent.run(
                    self.messages,
                    session_id=self.session_id,
                    run_id=run_id,
                )
        except asyncio.CancelledError:
            logger.info("Agent run cancelled by user")
            await self._handle_event("done", {
                "content": "",
                "stop_reason": "cancelled",
            })
            return {"session_id": self.session_id, "run_id": run_id, "cancelled": True}
        except Exception as exc:
            logger.exception("AgentLoop run failed")
            await self._handle_event("error", {
                "message": f"{type(exc).__name__}: {exc}",
            })
            return {"session_id": self.session_id, "run_id": run_id, "error": str(exc)}
        finally:
            self._current_run_task = None

        return {"session_id": self.session_id, "run_id": run_id, "result": result}

    def run_sync(self, user_input: str) -> dict:
        """Run one AgentLoop turn from synchronous test/CLI contexts."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(user_input))
        raise RuntimeError("run_sync cannot be called from a running event loop; use run_async")

    async def execute_slash_command_async(self, user_input: str) -> CommandResult | None:
        """Execute a slash command and apply local command side effects.

        This method does not start AgentLoop for `run_agent` command metadata.
        The Textual app uses that metadata to launch the run in a background
        worker so the UI event loop remains responsive.
        """
        stripped = user_input.strip()
        if not stripped.startswith("/"):
            return None

        model_str = getattr(getattr(self.agent, "llm", None), "model", "unknown")
        context = CommandContext(
            agent=self.agent,
            messages=self.messages,
            session_id=self.session_id,
            provider="unknown",
            model=str(model_str),
        )
        result = await self.command_registry.try_execute(user_input, context)
        if result is None:
            return None

        if result.message:
            self.state.transcript = [
                *self.state.transcript,
                TranscriptEntry.event("slash_command", result.message),
            ]

        if not result.continue_session:
            self.should_exit = True

        transition = result.metadata.get("transition")
        if transition:
            new_mode = transition.get("new_mode", "")
            if new_mode:
                self.state = reduce_tui_state(self.state, "mode_changed", {
                    "old_mode": transition.get("old_mode", ""),
                    "new_mode": new_mode,
                    "source": "slash_command",
                })

        if result.metadata.get("run_agent"):
            skill_runtime = getattr(self.agent, "skill_runtime", None)
            skill_name = result.metadata.get("skill_name")
            if skill_runtime is not None and skill_name:
                skill_runtime.queue_activation(
                    str(skill_name),
                    source=str(result.metadata.get("activation_source", "slash_command")),
                )

        return result

    async def handle_slash_command_async(self, user_input: str) -> bool:
        """Handle a slash command and run AgentLoop for prompt commands."""
        result = await self.execute_slash_command_async(user_input)
        if result is None:
            return False
        if result.metadata.get("run_agent"):
            agent_input = str(result.metadata.get("agent_input") or "").strip()
            if not agent_input:
                agent_input = user_input
            await self.run_async(agent_input)
        return True

    def handle_slash_command(self, user_input: str) -> bool:
        """Synchronous wrapper for tests and non-Textual contexts.

        Returns:
            True when the input was consumed as a command; otherwise False.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.handle_slash_command_async(user_input))
        raise RuntimeError(
            "handle_slash_command cannot be called from a running event loop; "
            "use handle_slash_command_async"
        )

    def cancel_run(self) -> None:
        """Cancel the current AgentLoop run and update TUI state."""
        self.state = reduce_tui_state(self.state, "done", {
            "content": "",
            "stop_reason": "cancelled",
        })
        if self._current_run_task is not None and not self._current_run_task.done():
            self._current_run_task.cancel()

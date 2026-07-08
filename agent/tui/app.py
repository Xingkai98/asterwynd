"""Textual TUI app.

Provides a multi-turn terminal conversation surface with transcript, input,
status, tool summary, planning state, slash suggestions, and approval handling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)

from agent.tui.commands import filter_commands_by_prefix, strip_command_prefix
from agent.tui.reducer import TUIState, reduce_tui_state
from agent.tui.widgets import (
    PlanningPanel,
    SlashSuggestionList,
    StatusBar,
    ToolSummaryPanel,
    TranscriptArea,
)

if TYPE_CHECKING:
    from agent.tui.controller import TUIController

logger = logging.getLogger("asterwynd.tui.app")


class TUIApp(App):
    """Asterwynd multi-turn Textual TUI application."""

    CSS = """
    #tui-container {
        height: 100%;
        layout: vertical;
    }

    #tui-status {
        dock: top;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    #tui-transcript {
        height: 1fr;
        border: solid $primary-background;
    }

    #transcript-log {
        height: 1fr;
    }

    #tui-planning {
        height: auto;
        max-height: 12;
        border: solid $primary-background;
        padding: 0 1;
        margin: 0 1;
    }

    #tui-tool-summary {
        height: auto;
        max-height: 10;
        border: solid $primary-background;
        padding: 0 1;
        margin: 0 1;
    }

    #tui-suggestions {
        height: auto;
        max-height: 12;
        padding: 0 1;
        margin: 0 1;
        color: $text-muted;
    }

    #tui-input-container {
        dock: bottom;
        height: auto;
        min-height: 3;
        padding: 0 1 1 1;
    }

    #tui-input {
        width: 100%;
    }

    #tui-approval-bar {
        height: auto;
        padding: 0 1;
        color: $warning;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("escape", "cancel_or_clear", "Cancel/Clear", show=True),
    ]

    def __init__(
        self,
        session_id: str,
        controller: TUIController | None = None,
        initial_prompt: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.session_id = session_id
        self._controller = controller
        self._initial_prompt = initial_prompt
        self._exit_requested = False
        self._slash_suggestions: list[dict] = []
        self._refresh_task: asyncio.Task | None = None
        self._running_worker: bool = False

    @property
    def tui_controller(self) -> TUIController | None:
        return self._controller

    @tui_controller.setter
    def tui_controller(self, ctrl: TUIController) -> None:
        self._controller = ctrl

    def compose(self) -> ComposeResult:
        """Build the UI layout."""
        yield StatusBar(id="tui-status")

        with Vertical(id="tui-container"):
            yield TranscriptArea(id="tui-transcript")
            yield PlanningPanel(id="tui-planning")
            yield ToolSummaryPanel(id="tui-tool-summary")
            yield SlashSuggestionList(id="tui-suggestions")

        yield Static(id="tui-approval-bar")

        with Container(id="tui-input-container"):
            yield Input(
                placeholder="Type a message or /command...",
                id="tui-input",
            )

    def on_mount(self) -> None:
        """Initialize refresh timers and initial state after mount."""
        self._update_status_bar()

        self.set_interval(0.15, self._refresh_display)

        if self._initial_prompt:
            self._submit_user_input(self._initial_prompt)

    def _update_status_bar(self) -> None:
        """Update the status bar from controller state."""
        status = self.query_one("#tui-status", StatusBar)
        if self._controller:
            state = self._controller.state
            status.session_id = state.session_id
            status.run_id = state.run_id
            status.mode = state.current_mode
            status.is_running = state.is_running
        else:
            status.session_id = self.session_id

    def _refresh_display(self) -> None:
        """Refresh all widgets from controller state."""
        if self._controller is None:
            return
        state = self._controller.state
        self._update_status_bar()

        transcript = self.query_one("#tui-transcript", TranscriptArea)
        self._sync_transcript(transcript, state)

        tool_panel = self.query_one("#tui-tool-summary", ToolSummaryPanel)
        tool_panel.update_tools(state.tool_events)

        planning_panel = self.query_one("#tui-planning", PlanningPanel)
        planning_panel.update_planning(state.planning_state, state.planning_document)

        suggestions = self.query_one("#tui-suggestions", SlashSuggestionList)
        suggestions.update_suggestions(self._slash_suggestions)

        approval_bar = self.query_one("#tui-approval-bar", Static)
        if state.pending_approval:
            req = state.pending_approval
            tool_name = req.get("tool_name", "unknown")
            reason = req.get("reason", "")
            args_summary = req.get("args_summary", "")
            approval_bar.update(
                f"[bold yellow]! Approval Required:[/] {tool_name}\n"
                f"  Reason: {reason}\n"
                f"  Args: {args_summary}\n"
                f"  Type [bold]/approve[/] or [bold]/deny[/] to respond."
            )
        else:
            approval_bar.update("")

    def _sync_transcript(self, transcript: TranscriptArea, state: TUIState) -> None:
        """Append transcript entries that are not yet rendered."""
        log = transcript.log
        target_lines = len(state.transcript)
        current_lines = getattr(self, "_transcript_line_count", 0)

        for i in range(current_lines, target_lines):
            entry = state.transcript[i]
            if entry.role == "user":
                log.write(f"[bold cyan]You:[/] {entry.content}")
            elif entry.role == "assistant":
                log.write(f"[bold green]Assistant:[/] {entry.content}")
            elif entry.role == "event":
                log.write(f"[dim italic]{entry.content}[/]")

        self._transcript_line_count = target_lines

        if state.assistant_streaming and not self._running_worker:
            # Only show streaming during active run
            pass

    def _submit_user_input(self, text: str) -> None:
        """Submit user input to the controller in a background worker."""
        if self._controller is None:
            return
        if self._running_worker:
            return

        self._running_worker = True
        self.run_worker(
            self._run_agent_turn(text),
            exclusive=True,
        )

    async def _run_agent_turn(self, user_input: str) -> None:
        """Background worker for one AgentLoop turn."""
        if self._controller is None:
            self._running_worker = False
            return

        input_widget = self.query_one("#tui-input", Input)
        input_widget.disabled = True

        try:
            await self._controller.run_async(user_input)
        except Exception as exc:
            logger.exception("Agent turn failed")
            self._controller.state = reduce_tui_state(
                self._controller.state, "error",
                {"message": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            self._running_worker = False
            input_widget.disabled = False
            input_widget.focus()
            self._refresh_display()

    def _check_approval(self, user_input: str) -> bool:
        """Return True when user input is consumed as an approval decision.

        Returns:
            True when input was consumed as approval.
        """
        if self._controller is None:
            return False
        state = self._controller.state
        if state.pending_approval is None:
            return False

        approval_handler = getattr(self._controller.agent, "approval_handler", None)
        if approval_handler is None:
            return False

        pending_id = getattr(approval_handler, "pending_approval_id", None)
        if pending_id is None:
            return False

        decision = user_input.strip()
        if not decision:
            return False

        if decision.startswith("/"):
            cmd_name, _remainder = strip_command_prefix(decision)
            if cmd_name in ("approve", "yes", "y", "accept"):
                approval_handler.submit_response(pending_id, "approved")
                return True
            if cmd_name in ("deny", "no", "n", "reject"):
                approval_handler.submit_response(pending_id, "denied")
                return True

        approval_handler.submit_response(pending_id, decision)
        return True

    def action_cancel_or_clear(self) -> None:
        """Clear input or cancel the current run."""
        input_widget = self.query_one("#tui-input", Input)
        if input_widget.value:
            input_widget.clear()
        elif self._controller and self._controller.state.is_running:
            self._controller.cancel_run()

    def request_exit(self) -> None:
        """Request app exit."""
        self._exit_requested = True
        self.exit()

    def update_status(self, session_id: str = "", run_id: str = "") -> None:
        """Update status bar fields from tests or external callers."""
        if session_id:
            self.session_id = session_id
        status = self.query_one("#tui-status", StatusBar)
        if session_id:
            status.session_id = session_id
        if run_id:
            status.run_id = run_id

    # ---- Input handling ----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle submitted input."""
        user_input = event.value.strip()
        event.input.clear()

        if not user_input:
            return

        if self._check_approval(user_input):
            return

        if user_input.startswith("/"):
            if await self._handle_slash_input(user_input):
                return

        self._clear_suggestions()
        self._submit_user_input(user_input)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update slash suggestions when input changes."""
        value = event.value
        if not value.startswith("/"):
            self._clear_suggestions()
            return

        if self._controller is None:
            return

        try:
            catalog = self._controller.command_registry.catalog()
        except Exception:
            return

        self._slash_suggestions = filter_commands_by_prefix(catalog, value)
        suggestions_widget = self.query_one("#tui-suggestions", SlashSuggestionList)
        suggestions_widget.update_suggestions(self._slash_suggestions)

    async def _handle_slash_input(self, user_input: str) -> bool:
        """Handle slash command input.

        Returns:
            True when the command consumed the input.
        """
        if self._controller is None:
            return False

        cmd_name, _remainder = strip_command_prefix(user_input)

        if cmd_name in ("exit", "quit", "q"):
            self._controller.should_exit = True
            self.request_exit()
            return True

        result = await self._controller.execute_slash_command_async(user_input)
        if result is None:
            return False

        self._clear_suggestions()
        if self._controller.should_exit:
            self.request_exit()
        if result.metadata.get("run_agent"):
            agent_input = str(result.metadata.get("agent_input") or "").strip()
            if not agent_input:
                agent_input = user_input
            self._submit_user_input(agent_input)
        return True

    def _clear_suggestions(self) -> None:
        """Clear slash command suggestions."""
        self._slash_suggestions = []
        suggestions_widget = self.query_one("#tui-suggestions", SlashSuggestionList)
        suggestions_widget.update_suggestions([])


async def run_tui_app(
    agent,
    session_id: str,
    command_registry,
    initial_prompt: str | None = None,
) -> int:
    """Run the TUI app.

    Args:
        agent: AgentLoop instance.
        session_id: Session id.
        command_registry: SlashCommandRegistry instance.
        initial_prompt: Optional prompt to submit after startup.

    Returns:
        Process exit code.
    """
    from agent.tui.controller import TUIController

    controller = TUIController(
        agent=agent,
        session_id=session_id,
        command_registry=command_registry,
    )
    from agent.tui.approval import TUIApprovalHandler
    if not isinstance(agent.approval_handler, TUIApprovalHandler):
        agent.approval_handler = TUIApprovalHandler()

    app = TUIApp(
        session_id=session_id,
        controller=controller,
        initial_prompt=initial_prompt,
    )

    await app.run_async(
        headless=False,
        size=None,
    )

    approval_handler = getattr(agent, "approval_handler", None)
    if hasattr(approval_handler, "fail_pending"):
        approval_handler.fail_pending("TUI session closed")

    return 0

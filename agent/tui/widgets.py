"""Textual widgets for the TUI.

Widgets render state passed in by the app and do not parse AgentLoop internals.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
    TextArea,
)
from textual.widget import Widget
from textual.reactive import reactive
from textual.binding import Binding


class StatusBar(Widget):
    """Status bar showing session id, run id, and current mode."""

    session_id: reactive[str] = reactive("")
    run_id: reactive[str | None] = reactive(None)
    mode: reactive[str] = reactive("build")
    is_running: reactive[bool] = reactive(False)

    def render(self) -> str:
        run_text = f"Run: {self.run_id}" if self.run_id else "Run: —"
        mode_style = "[bold green]" if self.is_running else ""
        mode_end = "[/]" if self.is_running else ""
        return (
            f"Session: {self.session_id}  |  "
            f"{run_text}  |  "
            f"Mode: {mode_style}{self.mode}{mode_end}"
        )


class TranscriptArea(VerticalScroll, can_focus=False):
    """Scrollable transcript area."""

    def __init__(self, **kwargs):
        kwargs.setdefault("id", "tui-transcript")
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=True, id="transcript-log")

    @property
    def log(self) -> RichLog:
        return self.query_one("#transcript-log", RichLog)

    def append_user(self, text: str) -> None:
        self.log.write(f"[bold cyan]You:[/] {text}")

    def append_assistant(self, text: str) -> None:
        self.log.write(f"[bold green]Assistant:[/] {text}")

    def append_event(self, event_type: str, text: str) -> None:
        self.log.write(f"[dim italic]{text}[/]")

    def append_streaming(self, delta: str) -> None:
        # Write to the end of the last line (streaming mode)
        # RichLog doesn't support in-place append; we use a dedicated streaming line
        pass

    def clear(self) -> None:
        self.log.clear()


class ToolSummaryPanel(Widget):
    """Tool call summary panel for the latest run."""

    tool_count: reactive[int] = reactive(0)
    _tool_lines: list[str] = []

    def update_tools(self, tool_events: list) -> None:
        lines: list[str] = []
        for i, tool in enumerate(tool_events, start=1):
            status_icon = "ok" if tool.status == "done" else "run" if tool.status == "running" else "err"
            summary = ""
            if tool.display:
                chars = tool.display.get("char_count", 0)
                lines_count = tool.display.get("line_count", 0)
                if tool.display.get("collapsed"):
                    summary = f" — {chars} chars, {lines_count} lines (collapsed)"
                else:
                    summary = f" — {chars} chars, {lines_count} lines"
            arg_preview = ""
            if tool.arguments:
                args_str = str(tool.arguments)
                if len(args_str) > 60:
                    arg_preview = f" {args_str[:57]}..."
                else:
                    arg_preview = f" {args_str}"
            lines.append(f"  {status_icon} {tool.name}{arg_preview}{summary}")
        self._tool_lines = lines
        self.tool_count = len(tool_events)

    def render(self) -> str:
        if not self._tool_lines:
            return "[dim]No tool calls[/]"
        header = f"[bold]Tool Calls ({self.tool_count}):[/]"
        return "\n".join([header, *self._tool_lines])


class PlanningPanel(Widget):
    """Planning state panel."""

    has_content: reactive[bool] = reactive(False)
    _content_lines: list[str] = []

    def update_planning(self, planning_state: dict | None, planning_document: dict | None) -> None:
        lines: list[str] = []
        if planning_document and planning_document.get("markdown"):
            title = planning_document.get("title", "Plan")
            status = planning_document.get("status", "")
            lines.append(f"[bold]Plan: {title}[/] ({status})")

            steps = planning_document.get("steps", [])
            for i, step in enumerate(steps, start=1):
                lines.append(f"  {i}. {step}")
        elif planning_state:
            items = planning_state.get("items", [])
            if items:
                lines.append("[bold]Planning State:[/]")
                for item in items:
                    item_id = item.get("id", "")
                    content = item.get("content", "")
                    status = item.get("status", "")
                    status_icon = (
                        "done"
                        if status == "completed"
                        else "todo"
                        if status == "pending"
                        else "doing"
                    )
                    lines.append(f"  {status_icon} [{item_id}] {content}")
        self._content_lines = lines
        self.has_content = len(lines) > 0

    def render(self) -> str:
        if not self._content_lines:
            return ""
        return "\n".join(self._content_lines)


class SlashSuggestionList(Widget):
    """Slash command suggestion list."""

    has_suggestions: reactive[bool] = reactive(False)
    _suggestions: list[dict] = []

    def update_suggestions(self, suggestions: list[dict]) -> None:
        self._suggestions = suggestions
        self.has_suggestions = len(suggestions) > 0

    def get_selected_insert_text(self) -> str | None:
        """Return the currently selected command insert text."""
        if not self._suggestions:
            return None
        return self._suggestions[0].get("insert_text")

    def render(self) -> str:
        if not self._suggestions:
            return ""
        lines = ["[bold]Commands:[/]"]
        for cmd in self._suggestions[:10]:
            usage = cmd.get("usage", "")
            desc = cmd.get("description", "")
            source = cmd.get("source", "")
            kind = cmd.get("kind", "")
            badge = ""
            if source == "skill":
                badge = " [dim](skill)[/]"
            elif kind == "prompt":
                badge = " [dim](prompt)[/]"
            lines.append(f"  [bold]{usage}[/]{badge} — {desc}")
        return "\n".join(lines)

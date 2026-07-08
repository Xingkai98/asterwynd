"""TUI 多轮 session/controller 测试。

覆盖同一 session 多个 run、message history、session id 复用、run id 更新、
退出路径和本地控制命令不启动 Agent run。
"""

import pytest

from agent.commands.registry import CommandContext, build_default_slash_command_registry
from agent.message import Message, system_message
from agent.result import RunResult, StopReason
from agent.run_identity import new_session_id
from agent.tui.controller import TUIController


class FakeLoop:
    """Fake AgentLoop that tracks runs and returns scripted results."""

    def __init__(self, content="fake response"):
        self.content = content
        self.max_iterations = 20
        self.tool_registry = type("FakeToolRegistry", (), {"mode_policy": type("FakePolicy", (), {"runtime_state": type("FakeState", (), {"current_mode": type("FakeMode", (), {"value": "build"})()})()})()})()
        self.runtime_state = type("FakeRuntimeState", (), {"current_mode": type("FakeMode", (), {"value": "build"})()})()
        self.memory = type("FakeMemory", (), {"messages": []})()
        self.run_count = 0
        self.events_received: list[tuple[str, dict]] = []
        self.on_event_handler = None

    async def run(self, messages, on_event=None, session_id=None, run_id=None):
        self.run_count += 1
        if on_event:
            await on_event("run_started", {
                "mode": "build",
                "run_id": run_id,
                "session_id": session_id,
            })
            await on_event("assistant_delta", {"delta": self.content, "content": self.content})
            await on_event("assistant_stream_complete", {
                "content": self.content,
                "stop_reason": "end_turn",
            })
            await on_event("llm_response", {
                "content": self.content,
                "stop_reason": "end_turn",
                "tool_calls": [],
                "streamed": True,
            })
            await on_event("done", {
                "content": self.content,
                "stop_reason": "end_turn",
            })
        return RunResult(
            content=self.content,
            stop_reason=StopReason.END_TURN,
            tool_calls_made=[],
        )


@pytest.fixture
def controller():
    fake = FakeLoop()
    cmd_registry = build_default_slash_command_registry(skill_runtime=None)
    ctrl = TUIController(agent=fake, session_id=new_session_id(), command_registry=cmd_registry)
    return ctrl


# ---------------------------------------------------------------------------
# session id
# ---------------------------------------------------------------------------

def test_controller_session_id_persists_across_runs(controller):
    sid = controller.session_id
    assert sid is not None
    assert len(sid) > 0

    controller.run_sync("first message")
    assert controller.session_id == sid

    controller.run_sync("second message")
    assert controller.session_id == sid


# ---------------------------------------------------------------------------
# run id rotation
# ---------------------------------------------------------------------------

def test_controller_generates_new_run_id_per_run(controller):
    result1 = controller.run_sync("first")
    run_id_1 = result1["run_id"]

    result2 = controller.run_sync("second")
    run_id_2 = result2["run_id"]

    assert run_id_1 != run_id_2
    assert controller.state.run_id == run_id_2


# ---------------------------------------------------------------------------
# message history
# ---------------------------------------------------------------------------

def test_controller_accumulates_messages(controller):
    controller.run_sync("first")
    controller.run_sync("second")

    user_messages = [
        m.content for m in controller.messages if m.role == "user"
    ]
    assert "first" in user_messages
    assert "second" in user_messages


def test_controller_message_history_preserves_system_message(controller):
    # Messages should start with system message
    controller.run_sync("hello")
    assert controller.messages[0].role == "system"


# ---------------------------------------------------------------------------
# run result fields
# ---------------------------------------------------------------------------

def test_controller_run_result_includes_session_and_run_id(controller):
    result = controller.run_sync("hello")
    assert "session_id" in result
    assert "run_id" in result
    assert result["session_id"] == controller.session_id


# ---------------------------------------------------------------------------
# exit command
# ---------------------------------------------------------------------------

def test_controller_handles_exit_slash_command(controller):
    handled = controller.handle_slash_command("/exit")
    assert handled is True
    assert controller.should_exit is True


def test_controller_handles_quit_alias(controller):
    handled = controller.handle_slash_command("/quit")
    assert handled is True
    assert controller.should_exit is True


# ---------------------------------------------------------------------------
# local commands don't start agent run
# ---------------------------------------------------------------------------

def test_controller_help_does_not_run_agent(controller):
    before_count = controller.agent.run_count
    handled = controller.handle_slash_command("/help")
    assert handled is True
    assert controller.agent.run_count == before_count


def test_controller_status_does_not_run_agent(controller):
    before_count = controller.agent.run_count
    handled = controller.handle_slash_command("/status")
    assert handled is True
    assert controller.agent.run_count == before_count


def test_controller_clear_does_not_run_agent(controller):
    controller.run_sync("hello")
    before_count = controller.agent.run_count
    handled = controller.handle_slash_command("/clear")
    assert handled is True
    assert controller.agent.run_count == before_count


# ---------------------------------------------------------------------------
# unknown slash command
# ---------------------------------------------------------------------------

def test_controller_unknown_slash_command_does_not_run_agent(controller):
    before_count = controller.agent.run_count
    handled = controller.handle_slash_command("/unknown")
    assert handled is True
    assert controller.agent.run_count == before_count


# ---------------------------------------------------------------------------
# transcript entries
# ---------------------------------------------------------------------------

def test_controller_state_has_user_and_assistant_entries(controller):
    result = controller.run_sync("hello")
    state = controller.state
    roles = [entry.role for entry in state.transcript]
    assert "user" in roles
    assert "assistant" in roles


def test_controller_state_has_final_content_after_run(controller):
    controller.run_sync("hello")
    assert controller.state.final_content is not None
    assert controller.state.is_running is False


# ---------------------------------------------------------------------------
# cancel run
# ---------------------------------------------------------------------------

def test_controller_cancel_stops_running_state():
    ctrl = TUIController(
        agent=FakeLoop(),
        session_id=new_session_id(),
        command_registry=build_default_slash_command_registry(),
    )
    ctrl.state.is_running = True
    ctrl.cancel_run()
    assert ctrl.state.is_running is False


# ---------------------------------------------------------------------------
# initial state fields
# ---------------------------------------------------------------------------

def test_controller_initial_state_has_session_id(controller):
    assert controller.state.session_id == controller.session_id


def test_controller_initial_state_not_running(controller):
    assert controller.state.is_running is False


def test_controller_initial_state_empty_transcript(controller):
    assert len(controller.state.transcript) == 0

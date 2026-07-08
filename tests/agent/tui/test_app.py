"""Lightweight Textual app smoke tests."""

import pytest

from agent.commands.registry import build_default_slash_command_registry
from agent.result import RunResult, StopReason
from agent.run_identity import new_session_id
from agent.tui.app import TUIApp
from agent.tui.commands import filter_commands_by_prefix
from agent.tui.controller import TUIController


class FakeLoop:
    def __init__(self):
        self.run_count = 0
        self.tool_registry = type("FakeTR", (), {"mode_policy": type("FakeP", (), {"runtime_state": type("FakeS", (), {"current_mode": type("FakeM", (), {"value": "build"})()})()})()})()
        self.runtime_state = type("FakeRS", (), {"current_mode": type("FakeM", (), {"value": "build"})()})()
        self.memory = type("FakeMem", (), {"messages": []})()
        self.max_iterations = 20

    async def run(self, messages, on_event=None, session_id=None, run_id=None):
        self.run_count += 1
        return RunResult(content="ok", stop_reason=StopReason.END_TURN, tool_calls_made=[])


class EventingFakeLoop(FakeLoop):
    async def run(self, messages, on_event=None, session_id=None, run_id=None):
        self.run_count += 1
        user_content = messages[-1].content
        if on_event:
            await on_event("assistant_stream_complete", {
                "content": f"response to {user_content}",
                "stop_reason": "end_turn",
            })
            await on_event("llm_response", {
                "content": f"response to {user_content}",
                "streamed": True,
            })
            await on_event("done", {
                "content": f"response to {user_content}",
                "stop_reason": "end_turn",
            })
        return RunResult(
            content=f"response to {user_content}",
            stop_reason=StopReason.END_TURN,
            tool_calls_made=[],
        )


@pytest.mark.asyncio
async def test_app_can_be_constructed():
    session_id = new_session_id()
    app = TUIApp(session_id=session_id)
    assert app.session_id == session_id
    assert app.title is not None


@pytest.mark.asyncio
async def test_app_can_mount_and_exit():
    session_id = new_session_id()
    app = TUIApp(session_id=session_id)

    async with app.run_test(size=(120, 40)) as pilot:
        assert pilot.app is not None
        await pilot.exit(0)


@pytest.mark.asyncio
async def test_app_status_bar_shows_session_id():
    session_id = "test-session-abc123"
    app = TUIApp(session_id=session_id)

    async with app.run_test(size=(120, 40)) as pilot:
        app.update_status(session_id=session_id, run_id="run-xyz")
        await pilot.pause()


@pytest.mark.asyncio
async def test_app_input_area_exists():
    app = TUIApp(session_id=new_session_id())

    async with app.run_test(size=(120, 40)) as pilot:
        input_widget = app.query_one("#tui-input")
        assert input_widget is not None
        await pilot.exit(0)


@pytest.mark.asyncio
async def test_app_transcript_area_exists():
    app = TUIApp(session_id=new_session_id())

    async with app.run_test(size=(120, 40)) as pilot:
        transcript = app.query_one("#tui-transcript")
        assert transcript is not None
        await pilot.exit(0)


@pytest.mark.asyncio
async def test_app_exit_command_stops_app():
    app = TUIApp(session_id=new_session_id())

    async with app.run_test(size=(120, 40)) as pilot:
        app.request_exit()
        await pilot.pause()
        # app should be in exiting state
        assert app._exit_requested is True


@pytest.mark.asyncio
async def test_app_submitted_slash_command_executes_when_suggestions_visible():
    registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(
        agent=FakeLoop(),
        session_id="session-test",
        command_registry=registry,
    )
    app = TUIApp(session_id="session-test", controller=controller)

    async with app.run_test(size=(120, 40)):
        app._slash_suggestions = filter_commands_by_prefix(registry.catalog(), "/status")
        handled = await app._handle_slash_input("/status")

        assert handled is True
        assert controller.agent.run_count == 0
        assert app._slash_suggestions == []
        assert any(
            "Session ID: session-test" in entry.content
            for entry in controller.state.transcript
        )


@pytest.mark.asyncio
async def test_app_does_not_append_rendered_transcript_again_after_each_turn():
    controller = TUIController(
        agent=EventingFakeLoop(),
        session_id="session-test",
        command_registry=build_default_slash_command_registry(skill_runtime=None),
    )
    app = TUIApp(session_id="session-test", controller=controller)

    async with app.run_test(size=(120, 40)):
        transcript = app.query_one("#tui-transcript")
        writes: list[str] = []

        def capture_write(message, *args, **kwargs):
            writes.append(str(message))

        transcript.log.write = capture_write

        await app._run_agent_turn("first")
        await app._run_agent_turn("second")

        assert sum("You:[/] first" in write for write in writes) == 1
        assert sum("Assistant:[/] response to first" in write for write in writes) == 1
        assert sum("You:[/] second" in write for write in writes) == 1
        assert sum("Assistant:[/] response to second" in write for write in writes) == 1

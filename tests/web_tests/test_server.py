# tests/web/test_server.py
"""Integration tests for FastAPI server (HTTP + WebSocket) with Mock LLM."""
import os
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

from agent.llm import LLMResponse, ToolCallDelta
from agent.config import MyAgentConfig, AgentConfig
from agent.run_config import AgentMode
from agent.tools.base import Tool, tool_parameters
from web.server import create_app
from web.debug_hook import debug_enabled


@tool_parameters(name="Echo", description="Echo tool", parameters={"type": "object", "properties": {}, "required": []})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo tool"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"


class MockLLM:
    def __init__(self, responses=None):
        self.responses = responses or [LLMResponse(content="Hello!")]
        self.call_count = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
        else:
            resp = LLMResponse(content="default")
        self.call_count += 1
        return resp


@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def app(mock_llm):
    return create_app(mock_llm)


@pytest.mark.asyncio
async def test_chat_page_returns_html(app):
    """GET / returns HTML."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_debug_page_disabled_by_default(app):
    """GET /debug returns 404 when debug is disabled."""
    old = os.environ.get("MYAGENT_DEBUG", "")
    try:
        if "MYAGENT_DEBUG" in os.environ:
            del os.environ["MYAGENT_DEBUG"]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/debug")
            assert resp.status_code == 404
    finally:
        os.environ["MYAGENT_DEBUG"] = old


@pytest.mark.asyncio
async def test_debug_page_enabled(app):
    """GET /debug returns 200 when debug is enabled."""
    old = os.environ.get("MYAGENT_DEBUG", "")
    try:
        # Re-create app with debug enabled
        mock = MockLLM([LLMResponse(content="Hello")])
        os.environ["MYAGENT_DEBUG"] = "enabled"
        debug_app = create_app(mock)
        transport = ASGITransport(app=debug_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/debug")
            assert resp.status_code == 200
    finally:
        os.environ["MYAGENT_DEBUG"] = old


@pytest.mark.asyncio
async def test_api_debug_status(app):
    """GET /api/debug-status returns correct status."""
    old = os.environ.get("MYAGENT_DEBUG", "")
    try:
        if "MYAGENT_DEBUG" in os.environ:
            del os.environ["MYAGENT_DEBUG"]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/debug-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] == debug_enabled()
    finally:
        os.environ["MYAGENT_DEBUG"] = old


@pytest.mark.asyncio
async def test_static_files_served(app):
    """Static files (style.css) are served."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_websocket_chat_flow():
    """WebSocket chat: connect -> send message -> receive events."""
    old_debug = os.environ.get("MYAGENT_DEBUG", "")
    try:
        if "MYAGENT_DEBUG" in os.environ:
            del os.environ["MYAGENT_DEBUG"]
        mock_llm = MockLLM([LLMResponse(content="Hello from agent!")])
        app = create_app(mock_llm)

        with TestClient(app) as client:
            with client.websocket_connect("/ws/new") as ws:
                created = ws.receive_json()
                assert created["type"] == "session_created"
                assert created["mode"] == "build"
                assert created["session_id"]

                ws.send_json({"type": "chat", "content": "hello"})
                events = []
                while True:
                    event = ws.receive_json()
                    events.append(event)
                    if event["type"] == "done":
                        break
    finally:
        os.environ["MYAGENT_DEBUG"] = old_debug
    assert [e["type"] for e in events] == ["run_started", "llm_response", "done"]
    assert events[0]["data"]["session_id"] == created["session_id"]
    assert events[0]["data"]["run_id"]
    assert events[-1]["data"]["content"] == "Hello from agent!"


def test_web_static_assets_include_session_and_run_display():
    index = (Path(__file__).parents[2] / "web" / "static" / "index.html").read_text()
    script = (Path(__file__).parents[2] / "web" / "static" / "chat.js").read_text()
    styles = (Path(__file__).parents[2] / "web" / "static" / "style.css").read_text()

    assert 'id="session-id"' in index
    assert 'id="run-id"' in index
    assert "sessionIdEl.textContent" in script
    assert "runIdEl.textContent" in script
    assert "addToolResultMessage(event.data)" in script
    assert "tool-result-toggle" in script
    assert "aria-expanded" in script
    assert "case 'error'" in script
    assert "max_iterations" in script
    assert ".tool-result-toggle" in styles

    toggle_start = script.index("toggle.addEventListener")
    toggle_end = script.index("controls.appendChild(toggle)", toggle_start)
    toggle_handler = script[toggle_start:toggle_end]
    assert "scrollHeight" not in toggle_handler


def test_websocket_session_created_includes_configured_mode():
    app = create_app(MockLLM([LLMResponse(content="Hello")]), mode="plan")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["mode"] == "plan"


def test_websocket_session_created_uses_config_default_mode():
    app = create_app(
        MockLLM([LLMResponse(content="Hello")]),
        config=MyAgentConfig(agent=AgentConfig(default_mode=AgentMode.PLAN)),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["mode"] == "plan"


def test_websocket_ping_and_reset(app):
    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"
            first_session = created["session_id"]

            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}

            ws.send_json({"type": "reset"})
            reset = ws.receive_json()
            assert reset["type"] == "session_created"
            assert reset["session_id"] != first_session
            assert reset["mode"] == "build"


def test_websocket_tool_events():
    old_debug = os.environ.get("MYAGENT_DEBUG", "")
    try:
        if "MYAGENT_DEBUG" in os.environ:
            del os.environ["MYAGENT_DEBUG"]
        mock_llm = MockLLM([
            LLMResponse(
                content=None,
                tool_calls=[ToolCallDelta(id="c1", name="Bash", arguments='{"cmd": "printf websocket"}')],
                stop_reason="tool_calls",
            ),
            LLMResponse(content="Done after tool", stop_reason="end_turn"),
        ])
        app = create_app(mock_llm)

        with TestClient(app) as client:
            with client.websocket_connect("/ws/new") as ws:
                ws.receive_json()
                ws.send_json({"type": "chat", "content": "run a command"})
                events = []
                while True:
                    event = ws.receive_json()
                    events.append(event)
                    if event["type"] == "done":
                        break
    finally:
        os.environ["MYAGENT_DEBUG"] = old_debug

    event_types = [e["type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert "websocket" in tool_result["data"]["result"]
    assert tool_result["data"]["display"]["collapsed"] is False
    assert tool_result["data"]["display"]["preview"]


@pytest.mark.asyncio
async def test_debug_websocket_events_enabled():
    """With debug enabled, WebSocket receives debug events."""
    old_debug = os.environ.get("MYAGENT_DEBUG", "")
    try:
        os.environ["MYAGENT_DEBUG"] = "enabled"
        mock_llm = MockLLM([LLMResponse(content="Debug test")])
        app = create_app(mock_llm)
        with TestClient(app) as client:
            with client.websocket_connect("/ws/new") as ws:
                ws.receive_json()
                ws.send_json({"type": "chat", "content": "debug"})
                events = []
                while True:
                    event = ws.receive_json()
                    events.append(event)
                    if event["type"] == "done":
                        break
    finally:
        os.environ["MYAGENT_DEBUG"] = old_debug

    assert any(e["type"] == "debug" and e["phase"] == "before_iteration" for e in events)
    assert any(e["type"] == "debug" and e["phase"] == "after_llm_call" for e in events)

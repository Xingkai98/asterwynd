# tests/web/test_server.py
"""Integration tests for FastAPI server (HTTP + WebSocket) with fake LLM."""
import os
import base64
import json
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

from agent.llm import LLMResponse, ToolCallDelta
from agent.config import AsterwyndConfig, AgentConfig, SkillsConfig
from agent.run_config import AgentMode
from agent.tools.base import Tool, tool_parameters
from web.server import create_app
from web.debug_hook import debug_enabled
from tests.support.llm_harness import ScriptedLLM


TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)
TINY_PNG_BYTES = base64.b64decode(TINY_PNG_DATA_URL.split(",", 1)[1])


@tool_parameters(name="Echo", description="Echo tool", parameters={"type": "object", "properties": {}, "required": []})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo tool"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"


@pytest.fixture
def mock_llm():
    return ScriptedLLM()


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
    old = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        if "ASTERWYND_DEBUG" in os.environ:
            del os.environ["ASTERWYND_DEBUG"]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/debug")
            assert resp.status_code == 404
    finally:
        os.environ["ASTERWYND_DEBUG"] = old


@pytest.mark.asyncio
async def test_debug_page_enabled(app):
    """GET /debug returns 200 when debug is enabled."""
    old = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        # Re-create app with debug enabled
        mock = ScriptedLLM([LLMResponse(content="Hello")])
        os.environ["ASTERWYND_DEBUG"] = "enabled"
        debug_app = create_app(mock)
        transport = ASGITransport(app=debug_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/debug")
            assert resp.status_code == 200
    finally:
        os.environ["ASTERWYND_DEBUG"] = old


@pytest.mark.asyncio
async def test_api_debug_status(app):
    """GET /api/debug-status returns correct status."""
    old = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        if "ASTERWYND_DEBUG" in os.environ:
            del os.environ["ASTERWYND_DEBUG"]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/debug-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] == debug_enabled()
    finally:
        os.environ["ASTERWYND_DEBUG"] = old


@pytest.mark.asyncio
async def test_api_slash_commands_returns_catalog(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/slash-commands")
        assert resp.status_code == 200
        data = resp.json()

    commands = data["commands"]
    names = {command["name"] for command in commands}
    assert {"help", "status", "clear", "compact", "mode"}.issubset(names)
    mode = next(command for command in commands if command["name"] == "mode")
    assert mode["command"] == "/mode"
    assert mode["argument_hint"] == "<build|read_only|plan>"
    assert mode["source"] == "builtin"
    assert mode["kind"] == "local"
    assert mode["insert_text"] == "/mode "


@pytest.mark.asyncio
async def test_api_slash_commands_includes_configured_skills(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "code-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: code-review\n"
        "description: 审查代码变更\n"
        "argument_hint: <request>\n"
        "user_invocable: true\n"
        "---\n"
        "Review instructions\n",
        encoding="utf-8",
    )
    app = create_app(
        ScriptedLLM([LLMResponse(content="Hello")]),
        config=AsterwyndConfig(skills=SkillsConfig(roots=(skills_root,))),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/slash-commands")
        assert resp.status_code == 200
        data = resp.json()

    skill_command = next(
        command for command in data["commands"]
        if command["name"] == "code-review"
    )
    assert skill_command["source"] == "skill"
    assert skill_command["kind"] == "prompt"
    assert skill_command["insert_text"] == "/code-review "


@pytest.mark.asyncio
async def test_static_files_served(app):
    """Static files (style.css) are served."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_brand_assets_are_served(app):
    """Brand wordmark assets are served for the Web UI header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/assets/asterwynd-web-wordmark.png")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")
        assert resp.content.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_websocket_chat_flow():
    """WebSocket chat: connect -> send message -> receive events."""
    old_debug = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        if "ASTERWYND_DEBUG" in os.environ:
            del os.environ["ASTERWYND_DEBUG"]
        mock_llm = ScriptedLLM([LLMResponse(content="Hello from agent!")])
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
        os.environ["ASTERWYND_DEBUG"] = old_debug
    assert [e["type"] for e in events] == ["run_started", "llm_response", "done"]
    assert events[0]["data"]["session_id"] == created["session_id"]
    assert events[0]["data"]["run_id"]
    assert events[-1]["data"]["content"] == "Hello from agent!"


def test_websocket_accepts_image_only_chat_message(tmp_path, monkeypatch):
    """Image-only WebSocket messages should start an agent run."""
    monkeypatch.chdir(tmp_path)
    mock_llm = ScriptedLLM([LLMResponse(content="saw image")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"

            ws.send_json({
                "type": "chat",
                "content": "",
                "images": [{"url": TINY_PNG_DATA_URL}],
            })
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    assert [e["type"] for e in events] == ["run_started", "llm_response", "done"]
    assert events[-1]["data"]["content"] == "saw image"
    assert mock_llm.call_count == 1
    last_user_message = mock_llm.last_messages[-1]
    assert last_user_message.role == "user"
    assert [type(block).__name__ for block in last_user_message.content] == ["ImageBlock"]


def test_uploads_api_accepts_multipart_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_llm = ScriptedLLM()
    app = create_app(mock_llm)

    with TestClient(app) as client:
        resp = client.post(
            "/api/uploads",
            files={"file": ("tiny.png", TINY_PNG_BYTES, "image/png")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["upload_id"].startswith("sha256_")
    assert data["upload_id"].endswith(".png")
    assert data["mime"] == "image/png"
    assert data["size"] == len(TINY_PNG_BYTES)
    assert (tmp_path / ".asterwynd" / "uploads" / data["upload_id"]).exists()


def test_websocket_accepts_uploaded_image_reference(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_llm = ScriptedLLM([LLMResponse(content="saw uploaded image")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        upload_resp = client.post(
            "/api/uploads",
            files={"file": ("tiny.png", TINY_PNG_BYTES, "image/png")},
        )
        upload_id = upload_resp.json()["upload_id"]

        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"

            ws.send_json({
                "type": "chat",
                "content": "",
                "images": [{"upload_id": upload_id}],
            })
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    assert [e["type"] for e in events] == ["run_started", "llm_response", "done"]
    assert events[-1]["data"]["content"] == "saw uploaded image"
    assert mock_llm.call_count == 1
    last_user_message = mock_llm.last_messages[-1]
    assert [type(block).__name__ for block in last_user_message.content] == ["ImageBlock"]
    assert last_user_message.content[0].file_path.endswith(upload_id)


def test_websocket_chunked_image_upload_returns_upload_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(ScriptedLLM())
    b64 = TINY_PNG_DATA_URL.split(",", 1)[1]

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"

            ws.send_json({
                "type": "image_upload_start",
                "client_upload_id": "client-1",
                "mime": "image/png",
                "total_chars": len(b64),
            })
            assert ws.receive_json() == {
                "type": "image_upload_started",
                "data": {"client_upload_id": "client-1"},
            }

            ws.send_json({
                "type": "image_upload_chunk",
                "client_upload_id": "client-1",
                "index": 0,
                "chunk": b64[:20],
            })
            chunk_ack = ws.receive_json()
            assert chunk_ack["type"] == "image_upload_chunk_ack"
            assert chunk_ack["data"]["client_upload_id"] == "client-1"
            assert chunk_ack["data"]["index"] == 0

            ws.send_json({
                "type": "image_upload_chunk",
                "client_upload_id": "client-1",
                "index": 1,
                "chunk": b64[20:],
            })
            chunk_ack = ws.receive_json()
            assert chunk_ack["type"] == "image_upload_chunk_ack"

            ws.send_json({
                "type": "image_upload_finish",
                "client_upload_id": "client-1",
            })
            complete = ws.receive_json()

    assert complete["type"] == "image_upload_complete"
    data = complete["data"]
    assert data["client_upload_id"] == "client-1"
    assert data["upload_id"].startswith("sha256_")
    assert data["upload_id"].endswith(".png")
    assert data["mime"] == "image/png"
    assert data["size"] == len(TINY_PNG_BYTES)
    assert (tmp_path / ".asterwynd" / "uploads" / data["upload_id"]).exists()


def test_websocket_image_upload_start_rejects_invalid_total_chars(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(ScriptedLLM())
    b64 = TINY_PNG_DATA_URL.split(",", 1)[1]

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"

            invalid_starts = [
                {
                    "type": "image_upload_start",
                    "client_upload_id": "bad-non-int",
                    "mime": "image/png",
                    "total_chars": "not-an-int",
                },
                {
                    "type": "image_upload_start",
                    "client_upload_id": "bad-missing",
                    "mime": "image/png",
                },
                {
                    "type": "image_upload_start",
                    "client_upload_id": "bad-negative",
                    "mime": "image/png",
                    "total_chars": -1,
                },
            ]
            for start in invalid_starts:
                ws.send_json(start)
                assert ws.receive_json() == {
                    "type": "image_upload_error",
                    "data": {"client_upload_id": start["client_upload_id"], "message": "invalid image size"},
                }

            ws.send_json({
                "type": "image_upload_start",
                "client_upload_id": "client-after-error",
                "mime": "image/png",
                "total_chars": len(b64),
            })
            assert ws.receive_json() == {
                "type": "image_upload_started",
                "data": {"client_upload_id": "client-after-error"},
            }


def test_web_static_assets_include_session_and_run_display():
    index = (Path(__file__).parents[2] / "web" / "static" / "index.html").read_text()
    script = (Path(__file__).parents[2] / "web" / "static" / "chat.js").read_text()
    styles = (Path(__file__).parents[2] / "web" / "static" / "style.css").read_text()

    assert 'id="session-id"' in index
    assert 'id="run-id"' in index
    assert "Asterwynd · Asterwynd Web UI" in index
    assert 'class="brand-wordmark"' in index
    assert 'src="/assets/asterwynd-web-wordmark.png?v=3"' in index
    assert 'id="mode-value"' in index
    assert 'id="mode-select"' in index
    assert 'id="mode-apply"' in index
    assert 'id="slash-suggestions"' in index
    assert 'id="plan-document-panel"' in index
    assert "/static/markdown.js?v=6" in index
    assert "/static/style.css?v=15" in index
    assert "/static/chat.js?v=17" in index
    assert 'id="image-previews"' in index
    assert 'id="image-file-input"' in index
    assert 'id="upload-btn"' in index
    assert "uploadBtn.addEventListener" in script
    assert "addImageFromFile" in script
    assert "pendingImages" in script
    assert "prepareImageForSend" in script
    assert "uploadImageDataUrl" in script
    assert "uploadImageDataUrlOverWebSocket" in script
    assert "HTTP_UPLOAD_TIMEOUT_MS" in script
    assert "AbortController" in script
    assert "image_upload_chunk" in script
    assert "image_upload_complete" in script
    assert "addUserMessage" in script
    assert "appendMessageImages" in script
    assert "openImageLightbox" in script
    assert "FormData" in script
    assert "fetch('/api/uploads'" in script
    assert "image/heic" in script
    assert "MAX_CHAT_PAYLOAD_CHARS" in script
    assert "sendInFlight" in script
    assert "Connection closed before the message was sent" in script
    assert "Connection is not ready" in script
    assert "fetch('/api/upload-image')" not in script
    assert "renderImagePreviews" in script
    assert index.index("/static/markdown.js") < index.index("/static/chat.js")
    assert "sessionIdEl.textContent" in script
    assert "runIdEl.textContent" in script
    assert "modeValueEl.textContent" in script
    assert "modeApplyBtn.addEventListener('click', sendModeChange)" in script
    assert "addToolResultMessage(event.data)" in script
    assert "case 'assistant_delta'" in script
    assert "case 'mode_changed'" in script
    assert "case 'command_result'" in script
    assert "metadata.transition" in script
    assert "function updateSlashSuggestions" in script
    assert "slashQueryFromInput" in script
    assert "command.name.startsWith(query)" in script
    assert "aliases.some(alias => alias.startsWith(query))" in script
    assert "moveSlashSelection" in script
    assert "applySlashSuggestion" in script
    assert "fetch('/api/slash-commands')" in script
    assert "shouldReconnect" in script
    assert "data.continue_session === false" in script
    assert "data.streamed" in script
    assert "appendAssistantContent(currentAssistantMsg, data.content)" in script
    assert "body.classList.add('markdown-body')" in script
    assert "tool-result-toggle" in script
    assert "aria-expanded" in script
    assert "case 'error'" in script
    assert "case 'plan_document_updated'" in script
    assert "case 'plan_document_submitted'" in script
    assert "case 'approval_request'" in script
    assert "function sendApprovalDecision" in script
    assert "function renderPlanDocument" in script
    assert "max_iterations" in script
    assert ".message-images" in styles
    assert ".image-lightbox" in styles
    assert ".plan-document-panel" in styles
    assert ".tool-result-toggle" in styles
    assert ".message.system" in styles
    assert "#slash-suggestions" in styles
    assert ".slash-suggestion.active" in styles
    assert "#mode-controls" in styles
    assert ".brand-lockup" in styles
    assert ".brand-fallback" in styles
    assert ".markdown-body pre" in styles

    toggle_start = script.index("toggle.addEventListener")
    toggle_end = script.index("controls.appendChild(toggle)", toggle_start)
    toggle_handler = script[toggle_start:toggle_end]
    assert "scrollHeight" not in toggle_handler

    tool_result_start = script.index("function addToolResultMessage")
    tool_result_end = script.index("function renderPlanningState", tool_result_start)
    tool_result_renderer = script[tool_result_start:tool_result_end]
    assert "innerHTML" not in tool_result_renderer
    assert "body.textContent" in tool_result_renderer


def _render_markdown(markdown: str) -> str:
    renderer = Path(__file__).parents[2] / "web" / "static" / "markdown.js"
    node_script = """
const fs = require('fs');
const vm = require('vm');
const renderer = fs.readFileSync(process.argv[1], 'utf8');
const markdown = JSON.parse(process.argv[2]);
const context = {
  URL,
  window: { location: { href: 'http://localhost/' } }
};
vm.createContext(context);
vm.runInContext(renderer, context);
process.stdout.write(JSON.stringify(context.window.AsterwyndMarkdown.render(markdown)));
"""
    result = subprocess.run(
        ["node", "-e", node_script, str(renderer), json.dumps(markdown)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_markdown_renderer_supports_basic_assistant_markdown():
    html = _render_markdown(
        "# Plan\n\n"
        "- read `README.md`\n"
        "- run tests\n\n"
        "```python\n"
        "print('<safe>')\n"
        "```\n\n"
        "[docs](https://example.com/docs)"
    )

    assert "<h3>Plan</h3>" in html
    assert "<ul><li>read <code>README.md</code></li><li>run tests</li></ul>" in html
    assert '<code class="language-python">print(&#39;&lt;safe&gt;&#39;)</code>' in html
    assert (
        '<a href="https://example.com/docs" target="_blank" '
        'rel="noopener noreferrer">docs</a>'
    ) in html


def test_markdown_renderer_escapes_raw_html_and_blocks_unsafe_links():
    html = _render_markdown(
        "<img src=x onerror=alert(1)>\n"
        "[bad](javascript:alert(1))\n"
        "<script>alert(1)</script>"
    )

    assert "<img" not in html
    assert "<script" not in html
    assert "onerror" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "href=\"javascript:" not in html
    assert ">bad</a>" not in html


def test_websocket_session_created_includes_configured_mode():
    app = create_app(ScriptedLLM([LLMResponse(content="Hello")]), mode="plan")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["mode"] == "plan"


def test_websocket_session_created_uses_config_default_mode():
    app = create_app(
        ScriptedLLM([LLMResponse(content="Hello")]),
        config=AsterwyndConfig(agent=AgentConfig(default_mode=AgentMode.PLAN)),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()

    assert created["type"] == "session_created"
    assert created["mode"] == "plan"


def test_websocket_set_mode_updates_session_mode_for_next_run():
    app = create_app(ScriptedLLM([LLMResponse(content="Hello")]), mode="build")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"
            assert created["mode"] == "build"

            ws.send_json({"type": "set_mode", "mode": "read_only"})
            mode_changed = ws.receive_json()
            assert mode_changed["type"] == "mode_changed"
            assert mode_changed["data"]["old_mode"] == "build"
            assert mode_changed["data"]["new_mode"] == "read_only"
            assert mode_changed["data"]["source"] == "web"
            assert mode_changed["data"]["session_id"] == created["session_id"]

            ws.send_json({"type": "chat", "content": "hello"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    run_started = next(event for event in events if event["type"] == "run_started")
    assert run_started["data"]["mode"] == "read_only"


def test_websocket_set_mode_rejects_bypass():
    app = create_app(ScriptedLLM([LLMResponse(content="Hello")]), mode="build")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            ws.send_json({"type": "set_mode", "mode": "bypass"})
            error = ws.receive_json()

            assert error["type"] == "error"
            assert "bypass" in error["data"]["message"]

            ws.send_json({"type": "chat", "content": "hello"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    run_started = next(event for event in events if event["type"] == "run_started")
    assert created["mode"] == "build"
    assert run_started["data"]["mode"] == "build"


def test_websocket_plan_mode_emits_plan_document_and_planning_state():
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallDelta(
                    id="p1",
                    name="ExitPlanMode",
                    arguments=(
                        '{"title":"Add plan mode",'
                        '"plan_markdown":"# Add plan mode\\n\\n## Steps\\n- Read docs",'
                        '"steps":["Read docs","Implement"]}'
                    ),
                )
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="计划已生成。", stop_reason="end_turn"),
    ])
    app = create_app(mock_llm, mode="plan")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["mode"] == "plan"
            ws.send_json({"type": "chat", "content": "plan add-plan-mode"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    event_types = [event["type"] for event in events]
    assert "planning_state_updated" in event_types
    assert "plan_document_submitted" in event_types
    plan_event = next(event for event in events if event["type"] == "plan_document_submitted")
    assert plan_event["data"]["title"] == "Add plan mode"
    assert plan_event["data"]["status"] == "submitted"
    assert plan_event["data"]["steps"] == ["Read docs", "Implement"]


def test_websocket_plan_mode_emits_draft_plan_updates():
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallDelta(
                    id="p1",
                    name="UpdatePlan",
                    arguments=(
                        '{"title":"Draft plan",'
                        '"plan_markdown":"# Draft plan",'
                        '"steps":["Read docs"]}'
                    ),
                )
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="草案已更新。", stop_reason="end_turn"),
    ])
    app = create_app(mock_llm, mode="plan")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()
            ws.send_json({"type": "chat", "content": "draft plan"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    event_types = [event["type"] for event in events]
    assert "planning_state_updated" in event_types
    assert "plan_document_updated" in event_types
    draft_event = next(event for event in events if event["type"] == "plan_document_updated")
    assert draft_event["data"]["title"] == "Draft plan"
    assert draft_event["data"]["status"] == "draft"


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


def test_websocket_slash_status_does_not_start_agent_run():
    mock_llm = ScriptedLLM([LLMResponse(content="should not be used")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()

            ws.send_json({"type": "chat", "content": "/status"})
            command_result = ws.receive_json()
            done = ws.receive_json()

    assert command_result["type"] == "command_result"
    assert "Session ID:" in command_result["data"]["message"]
    assert created["session_id"] in command_result["data"]["message"]
    assert done["type"] == "done"
    assert done["data"]["stop_reason"] == "command"
    assert mock_llm.call_count == 0


def test_websocket_unknown_slash_command_does_not_start_agent_run():
    mock_llm = ScriptedLLM([LLMResponse(content="should not be used")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()

            ws.send_json({"type": "chat", "content": "/unknown"})
            command_result = ws.receive_json()
            done = ws.receive_json()

    assert command_result["type"] == "command_result"
    assert "Unknown command: /unknown" in command_result["data"]["message"]
    assert done["data"]["stop_reason"] == "command"
    assert mock_llm.call_count == 0


def test_websocket_clear_slash_command_clears_session_history():
    mock_llm = ScriptedLLM([LLMResponse(content="first response")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()

            ws.send_json({"type": "chat", "content": "first"})
            while True:
                event = ws.receive_json()
                if event["type"] == "done":
                    break

            ws.send_json({"type": "chat", "content": "/clear"})
            command_result = ws.receive_json()
            done = ws.receive_json()

            ws.send_json({"type": "chat", "content": "/status"})
            status_result = ws.receive_json()
            ws.receive_json()

    assert command_result["type"] == "command_result"
    assert command_result["data"]["metadata"]["command"] == "clear"
    assert done["data"]["stop_reason"] == "command"
    assert "Messages: 1" in status_result["data"]["message"]


def test_websocket_mode_slash_command_updates_session_mode_without_agent_run():
    mock_llm = ScriptedLLM([LLMResponse(content="should not be used")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["mode"] == "build"

            ws.send_json({"type": "chat", "content": "/mode read_only"})
            command_result = ws.receive_json()
            done = ws.receive_json()

            ws.send_json({"type": "chat", "content": "/status"})
            status_result = ws.receive_json()
            ws.receive_json()

    assert command_result["type"] == "command_result"
    assert command_result["data"]["metadata"]["command"] == "mode"
    assert command_result["data"]["metadata"]["transition"]["new_mode"] == "read_only"
    assert done["data"]["stop_reason"] == "command"
    assert "Mode: read_only" in status_result["data"]["message"]
    assert mock_llm.call_count == 0


def test_websocket_skill_slash_command_activates_skill_and_runs_agent(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "code-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: code-review\n"
        "description: 审查代码变更\n"
        "argument_hint: <request>\n"
        "user_invocable: true\n"
        "---\n"
        "Review instructions\n",
        encoding="utf-8",
    )
    mock_llm = ScriptedLLM([LLMResponse(content="review done")])
    app = create_app(
        mock_llm,
        config=AsterwyndConfig(skills=SkillsConfig(roots=(skills_root,))),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()

            ws.send_json({"type": "chat", "content": "/code-review 帮我审一下这个 change"})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break

    event_types = [event["type"] for event in events]
    assert event_types[0] == "command_result"
    assert "run_started" in event_types
    assert events[-1]["data"]["content"] == "review done"
    assert mock_llm.call_count == 1
    assert mock_llm.last_messages is not None
    assert [message.content for message in mock_llm.last_messages if message.role == "user"] == [
        "帮我审一下这个 change"
    ]
    system_text = "\n".join(
        message.content or ""
        for message in mock_llm.last_messages
        if message.role == "system"
    )
    assert "Available skills:" in system_text
    assert "## Active Skill: code-review" in system_text
    assert "Review instructions" in system_text


def test_websocket_exit_slash_command_closes_without_agent_run():
    mock_llm = ScriptedLLM([LLMResponse(content="should not be used")])
    app = create_app(mock_llm)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()

            ws.send_json({"type": "chat", "content": "/exit"})
            command_result = ws.receive_json()
            done = ws.receive_json()

    assert command_result["type"] == "command_result"
    assert command_result["data"]["continue_session"] is False
    assert done["data"]["stop_reason"] == "command"
    assert mock_llm.call_count == 0


def test_websocket_tool_events():
    old_debug = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        if "ASTERWYND_DEBUG" in os.environ:
            del os.environ["ASTERWYND_DEBUG"]
        mock_llm = ScriptedLLM([
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
                    if event["type"] == "approval_request":
                        ws.send_json({
                            "type": "approval_response",
                            "approval_id": event["data"]["approval_id"],
                            "decision": "approved",
                        })
                    if event["type"] == "done":
                        break
    finally:
        os.environ["ASTERWYND_DEBUG"] = old_debug

    event_types = [e["type"] for e in events]
    assert "approval_request" in event_types
    assert any(
        e["type"] == "approval_response"
        and e["data"]["status"] == "approved"
        for e in events
    )
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert "websocket" in tool_result["data"]["result"]
    assert tool_result["data"]["display"]["collapsed"] is False
    assert tool_result["data"]["display"]["preview"]


@pytest.mark.asyncio
async def test_debug_websocket_events_enabled():
    """With debug enabled, WebSocket receives debug events."""
    old_debug = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        os.environ["ASTERWYND_DEBUG"] = "enabled"
        mock_llm = ScriptedLLM([LLMResponse(content="Debug test")])
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
        os.environ["ASTERWYND_DEBUG"] = old_debug

    assert any(e["type"] == "debug" and e["phase"] == "before_iteration" for e in events)
    assert any(e["type"] == "debug" and e["phase"] == "after_llm_call" for e in events)

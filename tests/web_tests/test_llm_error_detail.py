"""Web 层 LLM 错误详情与恢复历史只读修复（issue #304）。"""
import json
from datetime import datetime, timezone

import httpx
import pytest

from agent.hooks.manager import HookManager
from agent.llm import HTTP_BODY_ATTRIBUTE, LLMResponse, ToolCallDelta
from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX, Message
from agent.run_config import AgentMode
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot
from agent.tools.registry import ToolRegistry
from web.session import SessionManager, _group_failure_summary, build_history_payload

BODY = json.dumps({
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "provider body sentinel sk-secret",
    },
})


def _http_error(body: str = BODY, status: int = 400) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://fake.invalid/v1/messages")
    response = httpx.Response(status, content=body.encode(), request=request)
    exc = httpx.HTTPStatusError("provider failed", request=request, response=response)
    setattr(exc, HTTP_BODY_ATTRIBUTE, body)
    return exc


class FailingLLM:
    def __init__(self, exc: Exception):
        self.exc = exc

    async def chat(self, messages, tools=None, model=None) -> LLMResponse:
        raise self.exc


class TextOnlyLLM:
    async def chat(self, messages, tools=None, model=None) -> LLMResponse:
        return LLMResponse(content="done", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_web_error_event_carries_bounded_detail_and_status():
    manager = SessionManager()
    session = manager.create_session(FailingLLM(_http_error()))
    events = []

    async def collect(event):
        events.append(event)

    await manager.run_session(session, "hi", ws_send=collect)

    error = next(e for e in events if e["type"] == "error")
    assert error["data"]["status_code"] == 400
    assert error["data"]["detail"] == BODY
    assert "provider body sentinel" in error["data"]["detail"]
    assert session.last_turn is not None
    assert session.last_turn.message == "HTTP 400 (invalid_request_error)"


@pytest.mark.asyncio
async def test_web_error_event_non_http_shape_unchanged():
    manager = SessionManager()
    session = manager.create_session(FailingLLM(RuntimeError("boom")))
    events = []

    async def collect(event):
        events.append(event)

    await manager.run_session(session, "hi", ws_send=collect)

    error = next(e for e in events if e["type"] == "error")
    assert error["data"] == {"message": "RuntimeError: boom"}
    assert session.last_turn is not None
    assert session.last_turn.message == ""


def test_group_failure_summary_is_fixed_allowlist():
    assert _group_failure_summary({
        "status_code": 400, "detail": BODY,
    }) == "HTTP 400 (invalid_request_error)"
    # provider 控制的未知类型/自由文本不进入共享日志
    assert _group_failure_summary({
        "status_code": 400,
        "detail": json.dumps({"error": {"type": "sk-secret", "message": "secret"}}),
    }) == "HTTP 400 (unknown)"
    assert _group_failure_summary({"message": "no status"}) == ""


def _dangling_snapshot(session_id: str) -> SessionSnapshot:
    now = datetime.now(timezone.utc).isoformat()
    return SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id=session_id,
        created_at=now,
        updated_at=now,
        messages=[
            Message(role="user", content="go"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
            ),
        ],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="",
        iteration=0,
    )


def test_build_history_payload_repairs_resume_snapshot_read_only():
    manager = SessionManager()
    session = manager.create_session(TextOnlyLLM())
    snapshot = _dangling_snapshot(session.session_id)
    session.resume_snapshot = snapshot

    payload = build_history_payload(session)

    tools = [m for m in payload["data"]["messages"] if m["role"] == "tool"]
    assert len(tools) == 1
    assert tools[0]["tool_call_id"] == "c1"
    assert tools[0]["content"].startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    # 只读：快照对象没有被修改
    assert not any(m.role == "tool" for m in snapshot.messages)


@pytest.mark.asyncio
async def test_web_session_runner_failure_message_is_fixed_summary():
    from web.session import WebSessionRunner

    manager = SessionManager()
    session = manager.create_session(FailingLLM(_http_error()))
    runner = WebSessionRunner(manager)

    outcome = await runner.run(session.session_id, "hi")

    assert outcome.status == "failed"
    assert outcome.message == "HTTP 400 (invalid_request_error)"

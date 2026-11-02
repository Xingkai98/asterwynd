"""Web SessionManager 重启恢复路径（issue #304）：取消 → unload → resume → 再 run。"""
import asyncio
import json

import pytest

from agent.llm import LLMResponse, ToolCallDelta
from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX
from agent.tools.base import Tool, tool_parameters
from web.session import SessionManager


class SlowTool(Tool):
    name = "SlowTool"
    description = "blocks until cancelled"
    parameters = {}

    def __init__(self):
        self.started = asyncio.Event()

    async def execute(self, **kwargs) -> str:
        self.started.set()
        await asyncio.Event().wait()
        return "never"


tool_parameters(
    name="SlowTool",
    description="blocks",
    parameters={"type": "object", "properties": {}, "required": []},
)(SlowTool)


class ToolCallingLLM:
    async def chat(self, messages, tools=None, model=None) -> LLMResponse:
        return LLMResponse(
            content="",
            tool_calls=[ToolCallDelta(id="c1", name="SlowTool", arguments="{}")],
            stop_reason="tool_calls",
        )


class TextLLM:
    async def chat(self, messages, tools=None, model=None) -> LLMResponse:
        return LLMResponse(content="resumed ok", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_web_session_cancel_unload_resume_next_run_succeeds(tmp_path):
    manager = SessionManager(workspace_root=tmp_path)
    tool = SlowTool()
    session = manager.create_session(ToolCallingLLM(), tools=[tool])
    sid = session.session_id

    run_task = asyncio.create_task(manager.run_session(session, "hi"))
    try:
        await asyncio.wait_for(tool.started.wait(), timeout=5)
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if not run_task.done():
            run_task.cancel()

    # 模拟服务重启：卸载内存 session 后从落盘快照恢复。
    manager.unload_session(sid)
    resumed = await manager.resume_session_async(sid, TextLLM(), tools=[])
    assert resumed is not None
    assert resumed.resume_snapshot is not None
    tool_messages = [
        m for m in resumed.resume_snapshot.messages if m.role == "tool"
    ]
    assert [m.tool_call_id for m in tool_messages] == ["c1"]
    assert str(tool_messages[0].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)

    events = []

    async def collect(event):
        events.append(event)

    await manager.run_session(resumed, "next", ws_send=collect)

    assert not [e for e in events if e["type"] == "error"]
    assert resumed.last_turn is not None
    assert resumed.last_turn.status == "text"
    assert resumed.last_turn.text == "resumed ok"
    # 上下文中仍保留修复后的 tool_result
    assert any(m.role == "tool" and m.tool_call_id == "c1" for m in resumed.messages)


@pytest.mark.asyncio
async def test_group_member_timeout_does_not_brick_next_turn(tmp_path):
    from web.session import WebSessionRunner

    manager = SessionManager(workspace_root=tmp_path)
    tool = SlowTool()
    session = manager.create_session(ToolCallingLLM(), tools=[tool])
    runner = WebSessionRunner(manager)

    first = await runner.run(session.session_id, "hi", timeout=0.1)
    assert first.status == "timeout"

    # 下一轮换回文本 LLM；修复后的历史必须可用。
    session.agent.llm = TextLLM()
    second = await runner.run(session.session_id, "next", timeout=2.0)

    assert second.status == "text"
    assert second.text == "resumed ok"
    assert any(m.role == "tool" and m.tool_call_id == "c1" for m in session.messages)

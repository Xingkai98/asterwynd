"""issue #304 复现：被打断的 run 留下悬空 assistant ``tool_calls`` → 会话永久 400。

场景（真实代码路径，不手搓会话 JSON）：

1. ``AgentLoop`` + ``SessionStore`` 跑一轮；assistant 的 ``tool_calls`` 先进入
   消息链（``agent/loop.py:867``），随后工具执行阻塞在 ``_execute_tool_calls``；
2. 此时 cancel 掉 run（等价于重启 Web 服务 / 进程被杀），``run()`` 的 ``finally``
   仍会把消息链落盘（``agent/loop.py:658-660``）——``tool_result`` 尚未写入；
3. 从 ``SessionStore`` 重新加载（等价于 ``resume_session_async``），再发起下一次
   用户请求；
4. 真实 ``AnthropicLLM`` 序列化后发给一个**按 Anthropic 协议校验**的 fake endpoint
   （``httpx.MockTransport``）：assistant ``tool_use`` 后没有配对的 ``tool_result``
   ⇒ 返回 400，run 抛 ``HTTPStatusError``。

修复方向成立（加载/续跑自愈，或中断路径补配对）后，本测试应当 PASS。
本测试不修改生产代码。
"""
import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from agent.anthropic_llm import AnthropicLLM
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta
from agent.loop import AgentLoop
from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX, Message
from agent.run_config import AgentMode, AgentRunConfig
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore
from agent.tools.base import Tool, tool_parameters
from agent.tools.registry import ToolRegistry
from agent.trace_recorder import TraceRecorder


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


class SlowTool(Tool):
    """执行时阻塞到被取消，制造「tool_calls 已落消息链、tool_result 未写」的窗口。"""

    name = "SlowTool"
    description = "blocks until cancelled"
    parameters = {}

    def __init__(self, messages=None):
        self.started = asyncio.Event()
        self.messages = messages
        self.trigger_asserted = False

    async def execute(self, **kwargs) -> str:
        if self.messages is not None:
            # 中断前断言：assistant tool_calls 已 append，尚无匹配 tool 消息。
            self.trigger_asserted = (
                any(m.role == "assistant" and m.tool_calls for m in self.messages)
                and not any(m.role == "tool" for m in self.messages)
            )
        self.started.set()
        await asyncio.Event().wait()  # 永不返回，只能被取消
        return "never"


tool_parameters(
    name="SlowTool",
    description="blocks",
    parameters={"type": "object", "properties": {}, "required": []},
)(SlowTool)


class ProtocolCheckingAnthropic:
    """按 Anthropic Messages 协议校验请求的 fake endpoint。

    规则：每个含 ``tool_use`` 的 assistant 消息，其**下一条**消息必须是 ``user``，
    且包含每个 ``tool_use.id`` 对应的 ``tool_result``。违反则返回 400（与真实
    Anthropic/DeepSeek 的 ``tool_use`` 无配对 ``tool_result`` 错误一致）。
    """

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.violations: list[dict] = []
        self._first = True

    @staticmethod
    def _merge_consecutive_user_messages(messages: list[dict]) -> list[dict]:
        """模拟 Anthropic「Consecutive user turns combined into a single turn」."""
        merged: list[dict] = []
        for message in messages:
            if (
                merged
                and message.get("role") == "user"
                and merged[-1].get("role") == "user"
            ):
                prev = merged[-1].get("content")
                cur = message.get("content")
                prev_blocks = prev if isinstance(prev, list) else [{"type": "text", "text": str(prev or "")}]
                cur_blocks = cur if isinstance(cur, list) else [{"type": "text", "text": str(cur or "")}]
                merged[-1] = {"role": "user", "content": [*prev_blocks, *cur_blocks]}
                continue
            merged.append(dict(message))
        return merged

    @classmethod
    def _violations(cls, payload: dict) -> list[dict]:
        found = []
        messages = cls._merge_consecutive_user_messages(payload.get("messages", []))
        seen_tool_use_ids: set[str] = set()
        seen_tool_result_ids: set[str] = set()
        for index, message in enumerate(messages):
            role = message.get("role")
            content = message.get("content")
            blocks = content if isinstance(content, list) else []
            if role == "assistant":
                tool_use_ids = [
                    block["id"]
                    for block in blocks
                    if isinstance(block, dict) and block.get("type") == "tool_use"
                ]
                if not tool_use_ids:
                    continue
                following = messages[index + 1] if index + 1 < len(messages) else None
                following_blocks = (
                    following.get("content")
                    if following is not None
                    and following.get("role") == "user"
                    and isinstance(following.get("content"), list)
                    else []
                )
                result_ids = [
                    block.get("tool_use_id")
                    for block in following_blocks
                    if isinstance(block, dict) and block.get("type") == "tool_result"
                ]
                missing = [tool_id for tool_id in tool_use_ids if tool_id not in result_ids]
                if missing:
                    found.append({"index": index, "missing": missing, "following": following})
                # tool_result blocks must come first in the following user turn.
                first_non_result = next(
                    (
                        pos
                        for pos, block in enumerate(following_blocks)
                        if not (isinstance(block, dict) and block.get("type") == "tool_result")
                    ),
                    len(following_blocks),
                )
                if any(
                    isinstance(block, dict) and block.get("type") == "tool_result"
                    for block in following_blocks[first_non_result:]
                ):
                    found.append({"index": index, "reason": "tool_result_after_text"})
                seen_tool_use_ids.update(tool_use_ids)
            elif role == "user":
                for block in blocks:
                    if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                        continue
                    result_id = block.get("tool_use_id")
                    if result_id not in seen_tool_use_ids:
                        found.append({"index": index, "reason": "orphan_tool_result", "id": result_id})
                    if result_id in seen_tool_result_ids:
                        found.append({"index": index, "reason": "duplicate_tool_result", "id": result_id})
                    seen_tool_result_ids.add(result_id)
        return found

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append(payload)
        violations = self._violations(payload)
        if violations:
            self.violations.extend(violations)
            first = violations[0]
            if "missing" in first:
                message = (
                    f"messages.{first['index']}: `tool_use` ids were found without "
                    f"`tool_result` blocks immediately after: "
                    f"{', '.join(first['missing'])}. Each `tool_use` block must have "
                    f"a corresponding `tool_result` block in the next message."
                )
            else:
                message = (
                    f"messages.{first['index']}: invalid tool_result shape "
                    f"({first.get('reason', 'unknown')})."
                )
            body = {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": message},
            }
            return httpx.Response(400, json=body)

        if self._first:
            # 第一轮：让模型发起一次耗时的工具调用。
            self._first = False
            stream = _event("message_start", {
                "type": "message_start",
                "message": {
                    "id": "msg_1", "type": "message", "role": "assistant",
                    "content": [], "model": "claude-test",
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            }) + _event("content_block_start", {
                "type": "content_block_start", "index": 0,
                "content_block": {
                    "type": "tool_use", "id": "toolu_01", "name": "SlowTool", "input": {},
                },
            }) + _event("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": "{}"},
            }) + _event("content_block_stop", {"type": "content_block_stop", "index": 0}) \
              + _event("message_delta", {
                "type": "message_delta", "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 5},
            }) + _event("message_stop", {"type": "message_stop"})
        else:
            # 恢复后的下一轮：只要历史合法就正常回一段文本。
            stream = _event("message_start", {
                "type": "message_start",
                "message": {
                    "id": "msg_2", "type": "message", "role": "assistant",
                    "content": [], "model": "claude-test",
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            }) + _event("content_block_start", {
                "type": "content_block_start", "index": 0,
                "content_block": {"type": "text", "text": ""},
            }) + _event("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "text_delta", "text": "recovered ok"},
            }) + _event("content_block_stop", {"type": "content_block_stop", "index": 0}) \
              + _event("message_delta", {
                "type": "message_delta", "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 5},
            }) + _event("message_stop", {"type": "message_stop"})

        return httpx.Response(
            200,
            content=stream.encode(),
            headers={"content-type": "text/event-stream"},
        )


def _make_llm(endpoint: ProtocolCheckingAnthropic) -> AnthropicLLM:
    llm = AnthropicLLM(api_key="fake", base_url="http://fake.invalid", model="claude-test")
    llm.stream = True
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(endpoint.handler))
    return llm


def _make_loop(tmp_path, endpoint, store, tool=None) -> AgentLoop:
    registry = ToolRegistry()
    if tool is not None:
        registry.register(tool)
    return AgentLoop(
        llm=_make_llm(endpoint),
        tool_registry=registry,
        hooks=HookManager(),
        session_store=store,
        run_config=AgentRunConfig(),
    )


@pytest.mark.asyncio
async def test_cancelled_mid_tool_call_session_stays_usable_after_restart(tmp_path):
    """中断 → 重启加载 → 下一次请求：会话必须仍然可用（当前 400，故 FAIL）。

    这正是 issue #304 的「会话永久卡死」：悬空 ``tool_calls`` 被原样回放，
    fake endpoint 按 Anthropic 协议拒绝。修复（加载/续跑自愈或中断补配对）
    落地后，本测试应当 PASS。
    """
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    messages = [Message(role="user", content="please call the slow tool")]
    tool = SlowTool(messages)
    first_endpoint = ProtocolCheckingAnthropic()
    first_loop = _make_loop(tmp_path, first_endpoint, store, tool=tool)

    trace = TraceRecorder()
    run_task = asyncio.create_task(
        first_loop.run(messages, session_id="issue304-session", trace_recorder=trace)
    )
    try:
        await asyncio.wait_for(tool.started.wait(), timeout=5)
        # 中断前断言：assistant 的 tool_calls 已进入消息链（agent/loop.py:867），
        # tool_result 还在工具执行之后（agent/loop.py:1099）。
        assert tool.trigger_asserted
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if not run_task.done():
            run_task.cancel()

    # finally 的 best-effort 修复应在落盘前补齐配对。
    snapshot = store.load("issue304-session")
    assert snapshot is not None
    tool_messages = [m for m in snapshot.messages if m.role == "tool"]
    assert [m.tool_call_id for m in tool_messages] == ["toolu_01"]
    assert str(tool_messages[0].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    finally_steps = [
        s for s in trace.steps
        if s.type == "tool_pairing_repaired" and s.data.get("source") == "finally"
    ]
    assert finally_steps, "finally 修复应同步记录 trace step"

    # 模拟重启 Web 服务：从持久化快照恢复（web/session.py:resume_session_async
    # → AgentLoop._run 的 resume 分支），然后发起下一次用户请求。
    second_endpoint = ProtocolCheckingAnthropic()
    second_endpoint._first = False  # 恢复后的下一轮直接回文本
    second_loop = _make_loop(tmp_path, second_endpoint, store)
    session_messages = [
        Message(role="user", content="Members: the user, Bob and you (admin) ...")
    ]

    try:
        result = await second_loop.run(
            session_messages,
            session_id="issue304-session",
            resume_snapshot=snapshot,
        )
        assert result.content == "recovered ok"
        assert second_endpoint.violations == [], (
            "恢复后的请求 payload 含未配对的 tool_use："
            + json.dumps(second_endpoint.requests[-1], ensure_ascii=False)
        )
    finally:
        await first_loop.llm._client.aclose()
        await second_loop.llm._client.aclose()


def _dangling_snapshot(session_id: str) -> SessionSnapshot:
    now = datetime.now(timezone.utc).isoformat()
    return SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id=session_id,
        created_at=now,
        updated_at=now,
        messages=[
            Message(role="user", content="please call the slow tool"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCallDelta(id="toolu_01", name="SlowTool", arguments="{}")],
            ),
        ],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="run-1",
        iteration=0,
    )


@pytest.mark.asyncio
async def test_run_start_resume_repairs_dangling_snapshot(tmp_path):
    """直接构造旧版本/SIGKILL 留下的悬空快照，覆盖 _run 起点 resume 修复。"""
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    store.save(_dangling_snapshot("issue304-resume"))
    snapshot = store.load("issue304-resume")
    assert snapshot is not None

    endpoint = ProtocolCheckingAnthropic()
    endpoint._first = False  # 修复后直接回文本
    loop = _make_loop(tmp_path, endpoint, store)
    events = []

    async def on_event(event_type, data):
        events.append((event_type, data))

    try:
        result = await loop.run(
            [Message(role="user", content="next question")],
            on_event=on_event,
            session_id="issue304-resume",
            resume_snapshot=snapshot,
        )
        assert result.content == "recovered ok"
        assert endpoint.violations == []
        assert any(
            event_type == "tool_pairing_repaired" and data.get("source") == "resume"
            for event_type, data in events
        )
        # 展示/运行修复不应修改原始 resume snapshot 对象
        assert not any(m.role == "tool" for m in snapshot.messages)
        saved = store.load("issue304-resume")
        assert saved is not None
        saved_tools = [m for m in saved.messages if m.role == "tool"]
        assert [m.tool_call_id for m in saved_tools] == ["toolu_01"]
        assert str(saved_tools[0].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    finally:
        await loop.llm._client.aclose()


@pytest.mark.asyncio
async def test_cancelled_run_repairs_in_memory_for_same_process_retry(tmp_path):
    """同进程取消后的下一次 run 不依赖 resume_snapshot，直接复用已修复的 messages。"""
    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    messages = [Message(role="user", content="please call the slow tool")]
    tool = SlowTool(messages)
    first_loop = _make_loop(
        tmp_path, ProtocolCheckingAnthropic(), store, tool=tool,
    )
    run_task = asyncio.create_task(
        first_loop.run(messages, session_id="issue304-same-process")
    )
    try:
        await asyncio.wait_for(tool.started.wait(), timeout=5)
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if not run_task.done():
            run_task.cancel()

    assert any(m.role == "tool" and m.tool_call_id == "toolu_01" for m in messages)

    endpoint = ProtocolCheckingAnthropic()
    endpoint._first = False
    second_loop = _make_loop(tmp_path, endpoint, store)
    try:
        result = await second_loop.run(messages, session_id="issue304-same-process")
        assert result.content == "recovered ok"
        assert endpoint.violations == []
    finally:
        await first_loop.llm._client.aclose()
        await second_loop.llm._client.aclose()


class TextOnlyLLM:
    async def chat(self, messages, tools=None, model=None) -> LLMResponse:
        return LLMResponse(content="done", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_normal_run_does_not_synthesize_or_emit_repair_event(tmp_path):
    loop = AgentLoop(
        llm=TextOnlyLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(),
    )
    messages = [Message(role="user", content="hi")]
    events = []

    async def on_event(event_type, data):
        events.append((event_type, data))

    result = await loop.run(messages, on_event=on_event)

    assert result.content == "done"
    assert [m.role for m in messages] == ["user", "assistant"]
    assert not any(m.role == "tool" for m in messages)
    assert not any(event_type == "tool_pairing_repaired" for event_type, _ in events)


class FakeSkillRuntime:
    def __init__(self):
        self.active_skill_names = []

    def restore_skills(self, names):
        self.active_skill_names = list(names)

    def begin_run(self, user_input):
        pass


@pytest.mark.asyncio
async def test_resume_early_cancel_preserves_history_todos_skills_prompt(tmp_path):
    """ADV-8/ADV-D2：set_mode await 期间取消不得用截断历史/未恢复状态覆盖快照。"""
    from agent.planning import PlanItem

    store = SessionStore(sessions_root=str(tmp_path / "sessions"))
    now = datetime.now(timezone.utc).isoformat()
    snapshot = SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id="issue304-resume-cancel",
        created_at=now,
        updated_at=now,
        messages=[
            Message(role="user", content="old question"),
            Message(role="assistant", content="old answer"),
        ],
        mode=AgentMode.PLAN,
        todos=[PlanItem(id="1", content="keep me")],
        active_skills=["skill-a"],
        user_system_prompt="persona prompt",
        run_id="",
        iteration=0,
    )
    store.save(snapshot)
    loaded = store.load("issue304-resume-cancel")
    assert loaded is not None

    skill_runtime = FakeSkillRuntime()
    loop = AgentLoop(
        llm=TextOnlyLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        session_store=store,
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        skill_runtime=skill_runtime,
    )
    mode_change_started = asyncio.Event()

    async def on_event(event_type, data):
        if event_type == "mode_changed":
            mode_change_started.set()
            await asyncio.Event().wait()

    run_task = asyncio.create_task(loop.run(
        [Message(role="user", content="new question")],
        on_event=on_event,
        session_id="issue304-resume-cancel",
        resume_snapshot=loaded,
    ))
    try:
        await asyncio.wait_for(mode_change_started.wait(), timeout=5)
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if not run_task.done():
            run_task.cancel()

    saved = store.load("issue304-resume-cancel")
    assert saved is not None
    contents = [str(m.content) for m in saved.messages]
    assert "old question" in contents
    assert "new question" in contents
    assert any("Session resumed" in text for text in contents)
    assert saved.user_system_prompt == "persona prompt"
    assert [t.content for t in saved.todos] == ["keep me"]
    assert saved.active_skills == ["skill-a"]


@pytest.mark.asyncio
async def test_normal_run_start_repair_emits_run_source_event(tmp_path):
    """无 resume_snapshot 的普通 run 起点修复：source="run" 事件。"""
    messages = [
        Message(role="user", content="go"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
        ),
    ]
    loop = AgentLoop(
        llm=TextOnlyLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(),
    )
    events = []

    async def on_event(event_type, data):
        events.append((event_type, data))

    result = await loop.run(messages, on_event=on_event)

    assert result.content == "done"
    repair_events = [
        data for event_type, data in events
        if event_type == "tool_pairing_repaired"
    ]
    assert len(repair_events) == 1
    assert repair_events[0]["source"] == "run"
    assert repair_events[0]["count"] == 1
    assert any(m.role == "tool" and m.tool_call_id == "c1" for m in messages)

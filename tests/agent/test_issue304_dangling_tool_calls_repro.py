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
import os

import httpx
import pytest

from agent.anthropic_llm import AnthropicLLM
from agent.hooks.manager import HookManager
from agent.loop import AgentLoop
from agent.message import Message
from agent.run_config import AgentRunConfig
from agent.session import SessionStore
from agent.tools.base import Tool, tool_parameters
from agent.tools.registry import ToolRegistry


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


class SlowTool(Tool):
    """执行时阻塞到被取消，制造「tool_calls 已落消息链、tool_result 未写」的窗口。"""

    name = "SlowTool"
    description = "blocks until cancelled"
    parameters = {}

    def __init__(self):
        self.started = asyncio.Event()

    async def execute(self, **kwargs) -> str:
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
    def _violations(payload: dict) -> list[dict]:
        found = []
        messages = payload.get("messages", [])
        for index, message in enumerate(messages):
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            tool_use_ids = [
                block["id"]
                for block in content
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]
            if not tool_use_ids:
                continue
            following = messages[index + 1] if index + 1 < len(messages) else None
            result_ids = []
            if (
                following is not None
                and following.get("role") == "user"
                and isinstance(following.get("content"), list)
            ):
                result_ids = [
                    block.get("tool_use_id")
                    for block in following["content"]
                    if isinstance(block, dict) and block.get("type") == "tool_result"
                ]
            missing = [tool_id for tool_id in tool_use_ids if tool_id not in result_ids]
            if missing:
                found.append({"index": index, "missing": missing, "following": following})
        return found

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append(payload)
        violations = self._violations(payload)
        if violations:
            self.violations.extend(violations)
            first = violations[0]
            body = {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": (
                        f"messages.{first['index']}: `tool_use` ids were found without "
                        f"`tool_result` blocks immediately after: "
                        f"{', '.join(first['missing'])}. Each `tool_use` block must have "
                        f"a corresponding `tool_result` block in the next message."
                    ),
                },
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
    tool = SlowTool()
    first_endpoint = ProtocolCheckingAnthropic()
    first_loop = _make_loop(tmp_path, first_endpoint, store, tool=tool)

    messages = [Message(role="user", content="please call the slow tool")]
    run_task = asyncio.create_task(
        first_loop.run(messages, session_id="issue304-session")
    )
    try:
        await asyncio.wait_for(tool.started.wait(), timeout=5)
        # assistant 的 tool_calls 已进入消息链（agent/loop.py:867），
        # tool_result 还在工具执行之后（agent/loop.py:1099），此刻中断。
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if not run_task.done():
            run_task.cancel()

    # 落盘状态：assistant tool_calls 在，配对 tool 消息不在（触发条件已真实产生）。
    snapshot = store.load("issue304-session")
    assert snapshot is not None
    dangling = [
        message
        for message in snapshot.messages
        if message.role == "assistant" and message.tool_calls
    ]
    assert dangling, "中断应发生在 assistant tool_calls 已写入之后"
    assert not [message for message in snapshot.messages if message.role == "tool"]

    # 模拟重启 Web 服务：从持久化快照恢复（web/session.py:resume_session_async
    # → AgentLoop._run 的 resume 分支），然后发起下一次用户请求。
    second_endpoint = ProtocolCheckingAnthropic()
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

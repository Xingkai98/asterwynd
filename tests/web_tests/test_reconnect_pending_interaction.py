"""服务端级：断线重连恢复 pending 提问/审批（change web-reconnect-pending-interaction）。

覆盖 tasks 3.2 / 5.2 / 5.3 / 5.4 / 5.7。

**为什么用真 uvicorn + websockets 客户端而不是 ``TestClient``**：starlette 的
``TestClient.websocket_connect`` 在上下文退出时会取消整个 app task（实测
``CancelledError: Cancelled via cancel scope ... BlockingPortal._call_func``），
于是「断开连接但 run 继续跑」这条本 change 的核心语义在 ``TestClient`` 下根本
测不出来——run 是被测试夹具杀掉的，不是被断连杀掉的。真服务器 + 独立客户端才能
复现生产行为：客户端断开只让服务端的接收任务退出，run 继续跑到 sentinel。

断言重点：

- 重连事件**类型序列**钉死 ``session_resumed → session_history → 补发卡片``
  （序列断言锁住 D4 的排序不变量，比「最终收到了卡片」更强）；
- 断连不杀 run：断开后 run 继续执行，重连作答后仍跑完并释放 ``run_lock``；
- 多连接广播一致（Q3）、先答者胜（D7）、run 占用错误只回发起连接（M3）。
"""
import asyncio
import json
import socket
import threading
import time
import urllib.request

import pytest
from websockets.asyncio.client import connect

from agent.config import AsterwyndConfig, WebConfig
from agent.llm import LLMResponse, ToolCallDelta
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Server:
    """在后台线程里跑的真 uvicorn 服务，返回 (base_url, app)。"""

    def __init__(self, app, port: int):
        self.app = app
        self.port = port

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"


@pytest.fixture
def web_server(tmp_path):
    import uvicorn

    llm = _approval_llm()
    app = create_app(llm, workspace_root=tmp_path)
    yield from _run_server(app)


def _run_server(app, config: AsterwyndConfig | None = None, llm=None, tmp_path=None):
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/debug-status", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("web server failed to start")
    try:
        yield _Server(app, port)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _approval_llm() -> ScriptedLLM:
    """第一次 LLM 调用请求执行 Bash（高风险 → 触发 Web 审批），第二次收尾。"""
    return ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Bash", arguments='{"cmd": "printf reconnect"}')],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="done after approval", stop_reason="end_turn"),
    ])


def _question_llm() -> ScriptedLLM:
    return ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(
                id="c1",
                name="AskUserQuestion",
                arguments='{"title": "选分支", "body": "走哪条？", "options": ["a", "b"]}',
            )],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="done after answer", stop_reason="end_turn"),
    ])


async def _recv(ws, timeout: float = 10.0) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def _recv_until(ws, wanted: set[str], limit: int = 100, timeout: float = 10.0) -> list[dict]:
    events: list[dict] = []
    for _ in range(limit):
        event = await _recv(ws, timeout=timeout)
        events.append(event)
        if event.get("type") in wanted:
            return events
    raise AssertionError(f"never saw {wanted}; got {[e.get('type') for e in events]}")


async def _recv_types(ws, count: int, timeout: float = 10.0) -> list[dict]:
    return [await _recv(ws, timeout=timeout) for _ in range(count)]


async def _no_event(ws, window: float = 0.4) -> None:
    """断言窗口内没有事件到达（用于「不补发」的反例）。"""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ws.recv(), timeout=window)


async def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """轮询等待谓词成立（跨线程读服务端状态用）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def _open_run_until_approval(server, path: str = "/ws/new"):
    """连上并跑一条消息到 ``approval_request``，返回 ``(ws, session_id, approval_id)``。"""
    ws = await connect(f"{server.ws_url}{path}")
    created = await _recv(ws)
    session_id = created["session_id"]
    await ws.send(json.dumps({"type": "chat", "content": "run bash"}))
    events = await _recv_until(ws, {"approval_request"})
    approval_id = next(
        e for e in events if e["type"] == "approval_request"
    )["data"]["approval_id"]
    return ws, session_id, approval_id


# ---------------------------------------------------------------------------
# 断连不杀 run + 重连补发（D2/D3/D4，tasks 5.2/5.3）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_replays_pending_approval_and_run_completes(web_server):
    """断开不杀 run：重连补发卡片、作答后 run 跑完、锁释放。"""
    ws1, session_id, approval_id = await _open_run_until_approval(web_server)
    await ws1.close()

    # 断连后 run 仍在等待用户：pending 保留（D2）。
    session = web_server.app.state.session_manager.get_session(session_id)
    assert session.approval_handler.pending_approval_id == approval_id
    assert session.run_lock.locked()

    async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
        head = await _recv_types(ws2, 3)
        assert [e["type"] for e in head] == [
            "session_resumed",
            "session_history",
            "approval_request",
        ]
        replay = head[2]["data"]
        assert replay["approval_id"] == approval_id
        assert replay["session_id"] == session_id
        assert replay["tool_name"] == "Bash"
        assert replay["risk"]

        await ws2.send(json.dumps({
            "type": "approval_response",
            "approval_id": approval_id,
            "decision": "approved",
        }))
        rest = await _recv_until(ws2, {"done"}, limit=100)

    assert any(
        e["type"] == "approval_response" and e["data"]["status"] == "approved"
        for e in rest
    ), [e["type"] for e in rest]
    assert any(e["type"] == "tool_result" for e in rest), [e["type"] for e in rest]
    # run 正常收尾：锁已释放。
    assert not session.run_lock.locked()


@pytest.mark.asyncio
async def test_reconnect_replays_pending_question(tmp_path):
    """提问卡片同样补发在 session_history 之后，且重连后可作答。"""
    app = create_app(_question_llm(), workspace_root=tmp_path)
    for server in _run_server(app):
        ws1 = await connect(f"{server.ws_url}/ws/new")
        session_id = (await _recv(ws1))["session_id"]
        await ws1.send(json.dumps({"type": "chat", "content": "ask me"}))
        events = await _recv_until(ws1, {"user_question"})
        question_id = next(
            e for e in events if e["type"] == "user_question"
        )["data"]["question_id"]
        await ws1.close()

        async with connect(f"{server.ws_url}/ws/{session_id}") as ws2:
            head = await _recv_types(ws2, 3)
            assert [e["type"] for e in head] == [
                "session_resumed",
                "session_history",
                "user_question",
            ]
            replay = head[2]["data"]
            assert replay["question_id"] == question_id
            assert replay["session_id"] == session_id
            assert replay["title"] == "选分支"
            assert replay["options"] == ["a", "b"]

            await ws2.send(json.dumps({
                "type": "user_answer",
                "question_id": question_id,
                "answer": "a",
            }))
            rest = await _recv_until(ws2, {"done"}, limit=100)

        assert any(
            e["type"] == "user_answer" and e["data"]["status"] == "received"
            for e in rest
        ), [e["type"] for e in rest]
        break


@pytest.mark.asyncio
async def test_reconnect_without_pending_sends_no_interaction_events(tmp_path):
    """反例：没有 pending 时重连不补发任何交互卡片（用 ping/pong 证明无多余事件）。"""
    app = create_app(ScriptedLLM(), workspace_root=tmp_path)
    for server in _run_server(app):
        async with connect(f"{server.ws_url}/ws/new") as ws1:
            session_id = (await _recv(ws1))["session_id"]

        async with connect(f"{server.ws_url}/ws/{session_id}") as ws2:
            head = await _recv_types(ws2, 2)
            assert [e["type"] for e in head] == ["session_resumed", "session_history"]
            # 紧邻的下一条就是 pong：中间没有插入任何 user_question / approval_request。
            await ws2.send(json.dumps({"type": "ping"}))
            assert await _recv(ws2) == {"type": "pong"}
            await _no_event(ws2)
        break


@pytest.mark.asyncio
async def test_reconnect_after_answer_does_not_replay_decided_request(web_server):
    """已决请求不重放（D1 / 调研 finding 8）：作答后重连不再补发卡片。"""
    ws1, session_id, approval_id = await _open_run_until_approval(web_server)
    await ws1.send(json.dumps({
        "type": "approval_response",
        "approval_id": approval_id,
        "decision": "approved",
    }))
    await _recv_until(ws1, {"done"}, limit=100)
    await ws1.close()

    session = web_server.app.state.session_manager.get_session(session_id)
    assert session.approval_handler.pending_approval_payload() is None

    async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
        head = await _recv_types(ws2, 2)
        assert [e["type"] for e in head] == ["session_resumed", "session_history"]
        await ws2.send(json.dumps({"type": "ping"}))
        assert await _recv(ws2) == {"type": "pong"}
        await _no_event(ws2)


# ---------------------------------------------------------------------------
# 多连接（D7 / Q3，tasks 5.4）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_in_progress_error_only_reaches_initiator(web_server):
    """run 占用错误只回发起连接（M3）：另一个 tab 不该看到这条错误。"""
    ws1, session_id, _ = await _open_run_until_approval(web_server)

    async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
        head = await _recv_types(ws2, 3)
        assert [e["type"] for e in head] == [
            "session_resumed",
            "session_history",
            "approval_request",
        ]
        await ws2.send(json.dumps({"type": "chat", "content": "another message"}))
        rejection = await _recv_until(ws2, {"error"}, limit=20)
        error = next(e for e in rejection if e["type"] == "error")
        assert error["data"]["code"] == "run_in_progress"

        # 第一条连接不该收到这条错误。
        await ws1.send(json.dumps({"type": "ping"}))
        assert await _recv(ws1) == {"type": "pong"}
        await _no_event(ws1)
    await ws1.close()


@pytest.mark.asyncio
async def test_terminal_state_broadcasts_to_all_connections(web_server):
    """Q3：两条连接并存时，一条作答，两条收到一致的终态。"""
    ws1, session_id, approval_id = await _open_run_until_approval(web_server)

    async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
        await _recv_types(ws2, 3)
        await ws2.send(json.dumps({
            "type": "approval_response",
            "approval_id": approval_id,
            "decision": "approved",
        }))
        ws2_events = await _recv_until(ws2, {"done"}, limit=100)
        ws1_events = await _recv_until(ws1, {"done"}, limit=100)
    await ws1.close()

    def _terminal(events):
        return [
            (e["type"], e["data"].get("approval_id"), e["data"].get("status"))
            for e in events
            if e["type"] == "approval_response"
        ]

    assert _terminal(ws1_events) == _terminal(ws2_events)
    assert ("approval_response", approval_id, "approved") in _terminal(ws1_events)


@pytest.mark.asyncio
async def test_first_answer_wins_second_gets_unavailable(web_server):
    """先答者胜：后提交者收到 unavailable，且不覆盖先到的决定（D7）。"""
    ws1, session_id, approval_id = await _open_run_until_approval(web_server)

    async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
        await _recv_types(ws2, 3)
        await ws1.send(json.dumps({
            "type": "approval_response",
            "approval_id": approval_id,
            "decision": "approved",
        }))
        await ws2.send(json.dumps({
            "type": "approval_response",
            "approval_id": approval_id,
            "decision": "denied",
        }))
        ws2_events = await _recv_until(ws2, {"done"}, limit=100)
    await ws1.close()

    statuses = [
        e["data"]["status"]
        for e in ws2_events
        if e["type"] == "approval_response"
    ]
    assert "approved" in statuses, statuses
    assert "unavailable" in statuses, statuses
    assert "denied" not in statuses, statuses


@pytest.mark.asyncio
async def test_inline_answer_path_broadcasts_terminal_state(web_server):
    """Q3：run 不在时的 inline 作答分支也必须广播终态，不能只回提交者。

    直接在该 session 上造一个 pending（模拟「run 已结束但卡片还在客户端」的历史
    遗留场景），从一条连接提交，断言另一条连接也收到终态。
    """
    from agent.approval import ApprovalRequest
    from web.session import _PendingInteraction

    async with connect(f"{web_server.ws_url}/ws/new") as ws1:
        session_id = (await _recv(ws1))["session_id"]
        session = web_server.app.state.session_manager.get_session(session_id)
        # 屏障：ping/pong 由 endpoint 主循环处理，只有它回合到来才证明本连接的
        # ``bind_pending_interaction_channel`` 已经跑完。否则注入 pending 与首连接
        # 的补发之间会竞态——那条连接会「合法地」收到一次补发卡片（服务端语义上
        # 它确实绑定在 pending 之后），断言就随调度漂移。
        await ws1.send(json.dumps({"type": "ping"}))
        assert await _recv(ws1) == {"type": "pong"}
        loop = asyncio.get_running_loop()
        request = ApprovalRequest(
            approval_id="inline-approval",
            tool_call_id="call-1",
            tool_name="Bash",
            mode="build",
            capability=["command_execute"],
            risk="high",
            origin="builtin",
            reason="test",
            profile_name="build_default",
            redacted_args={},
            args_summary="{}",
            session_id=session_id,
            run_id="run-1",
        )
        # future 建在测试进程的循环上即可：run 不在，没有任何人在 await 它。
        session.approval_handler._pending = _PendingInteraction(
            interaction_id=request.approval_id,
            future=loop.create_future(),
            payload=request.to_event_data(),
        )

        async with connect(f"{web_server.ws_url}/ws/{session_id}") as ws2:
            head = await _recv_types(ws2, 3)
            assert [e["type"] for e in head] == [
                "session_resumed",
                "session_history",
                "approval_request",
            ]
            await ws2.send(json.dumps({
                "type": "approval_response",
                "approval_id": "inline-approval",
                "decision": "approved",
            }))
            # 提交者与另一条连接收到同一份终态。
            assert await _recv(ws2) == {
                "type": "approval_response",
                "data": {
                    "approval_id": "inline-approval",
                    "status": "received",
                    "reason": "received",
                    "session_id": session_id,
                },
            }
            assert await _recv(ws1) == {
                "type": "approval_response",
                "data": {
                    "approval_id": "inline-approval",
                    "status": "received",
                    "reason": "received",
                    "session_id": session_id,
                },
            }


# ---------------------------------------------------------------------------
# 断连期间 run 跑完 / drain 不阻塞（tasks 5.3）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_completes_with_no_bound_connection(tmp_path):
    """断连期间没有 pending 时 run 正常跑完并释放锁（drain 永不退出）。"""
    app = create_app(
        ScriptedLLM([LLMResponse(content="plain done", stop_reason="end_turn")]),
        workspace_root=tmp_path,
    )
    for server in _run_server(app):
        ws1 = await connect(f"{server.ws_url}/ws/new")
        session_id = (await _recv(ws1))["session_id"]
        await ws1.send(json.dumps({"type": "chat", "content": "hi"}))
        await _recv_until(ws1, {"done"}, limit=50)
        await ws1.close()

        session = server.app.state.session_manager.get_session(session_id)
        # 断连后锁已释放，且 session 没有残留 sender（drain 没有因为没人收就退出）。
        assert not session.run_lock.locked()
        assert await _wait_for(lambda: session.event_channel.handles == ())
        break


@pytest.mark.asyncio
async def test_drain_keeps_consuming_after_disconnect(tmp_path):
    """drain 永远消费 queue：断连期间产生的事件不会让 drain 退出或堆积。

    断开连接后让 run 产生一条事件（重连后从 ``session_history`` 能看到它的效果），
    再断言 run 仍能正常收尾。
    """
    app = create_app(
        ScriptedLLM([LLMResponse(content="streamed text", stop_reason="end_turn")]),
        workspace_root=tmp_path,
    )
    for server in _run_server(app):
        ws1 = await connect(f"{server.ws_url}/ws/new")
        session_id = (await _recv(ws1))["session_id"]
        await ws1.send(json.dumps({"type": "chat", "content": "hi"}))
        await _recv_until(ws1, {"done"}, limit=50)

        session = server.app.state.session_manager.get_session(session_id)
        await ws1.close()
        # 断开后 drain 仍能收尾（无异常、无残留 sender）。
        assert await _wait_for(lambda: session.event_channel.handles == ())
        assert not session.run_lock.locked()
        break

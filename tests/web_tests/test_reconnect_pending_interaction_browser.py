# tests/web_tests/test_reconnect_pending_interaction_browser.py
"""Playwright 行为断言：重连补发 pending 卡片与前端幂等（change tasks 4.x/5.5）。

为什么优先行为断言而不是 chat.js 源码字符串断言：源码断言对重构脆弱（改个函数名
就红），且历史上有过「只在 CI 挂」的着色类陷阱。这里用真实浏览器 + 真实 WebSocket，
断言用户能看到、能点到的东西。

断连用 ``window.AsterwyndChatTest.dropConnection()`` 关闭当前 tab 的 WebSocket 制造，
之后完全走生产路径：客户端 ``onclose`` → 2s 退避 → 重连同一 session；服务端 detach
旧连接、补发仍 pending 的卡片。注意 ``BrowserContext.set_offline`` 只影响新建连接，
不会拆掉已建立的 WebSocket（实测断网后状态灯仍是 connected），所以不能用它来断连。

另外两条纯前端的断言用 ``window.AsterwyndChatTest.dispatch`` 直接派发事件——「同一 id
的卡片事件重复到达」在真实链路里必然伴随 ``renderHistory`` 清空注册表，无法单独复现。

CI 无浏览器时自动 skip（与 ``test_multi_session_browser.py`` 同口径）。
"""
import asyncio
import socket
import threading
import time
import urllib.request

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.llm import LLMResponse, LLMStreamEvent, ToolCallDelta
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app

INPUT_SELECTOR = ".tab-pane.active .user-input"
SEND_SELECTOR = ".tab-pane.active .send-btn"


def _approval_script() -> list:
    """第一次调用请求执行 Bash（高风险 → Web 审批），第二次收尾。"""
    return [
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Bash", arguments='{"cmd": "printf reconnect"}')],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="done after approval", stop_reason="end_turn"),
    ]


def _question_script() -> list:
    return [
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
    ]


class GatedStreamLLM(ScriptedLLM):
    """流式 LLM：先用一个 delta 打开窗口，阻塞到测试放行后再吐第二个 delta。

    让「run 正在流式输出时断连重连」成为可复现状态，而不是抢时序。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, stream=True, **kwargs)
        self.first_delta_sent = threading.Event()
        self.release = threading.Event()

    async def stream_chat(self, messages, tools=None, model="gpt-4"):
        yield LLMStreamEvent(type="assistant_delta", delta="断连前的前半段", content="断连前的前半段")
        self.first_delta_sent.set()
        await asyncio.get_running_loop().run_in_executor(None, self.release.wait)
        yield LLMStreamEvent(
            type="assistant_delta",
            delta="重连后的增量",
            content="断连前的前半段重连后的增量",
        )
        final = LLMResponse(content="断连前的前半段重连后的增量", stop_reason="end_turn")
        yield LLMStreamEvent(
            type="complete",
            content=final.content,
            stop_reason=final.stop_reason,
            response=final,
        )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(app, port: int):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/api/debug-status", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("web server failed to start")
    return server, thread, base_url


@pytest.fixture
async def browser_context():
    from playwright.async_api import Error as PlaywrightError, async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"playwright chromium unavailable: {exc}")
        context = await browser.new_context()
        yield context
        await context.close()
        await browser.close()


@pytest.fixture
async def browser_page(browser_context):
    page = await browser_context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    yield page
    if errors:
        pytest.fail(f"Browser JS errors: {errors}")


@pytest.fixture
def approval_web_server(tmp_path):
    app = create_app(ScriptedLLM(_approval_script()), workspace_root=tmp_path)
    port = _free_port()
    server, thread, base_url = _start_server(app, port)
    try:
        yield {"url": base_url, "app": app, "port": port}
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def _open_new_session(page, base_url: str) -> None:
    await page.goto(base_url)
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)


async def _wait_connection_status(page, values: tuple[str, ...], timeout: int = 25000) -> None:
    allowed = "[" + ",".join(f"'{v}'" for v in values) + "]"
    await page.wait_for_function(
        f"{allowed}.includes(document.querySelector('#status').textContent)",
        timeout=timeout,
    )


async def _wait_connected(page, timeout: int = 25000) -> None:
    await _wait_connection_status(page, ("connected",), timeout=timeout)


async def _drop_and_reconnect(page) -> None:
    """断开当前连接，等状态灯反映断开，再等到自动重连完成。"""
    await page.evaluate("() => window.AsterwyndChatTest.dropConnection()")
    await _wait_connection_status(page, ("disconnected", "error"))
    await _wait_connected(page)


# ---------------------------------------------------------------------------
# 重连补发（issue #195 的验收路径）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_replays_approval_card_and_it_is_actionable(
    browser_page, browser_context, approval_web_server
):
    """切后台断连 → 重连后卡片重新出现、只有一张、且能提交并跑完。"""
    page = browser_page
    await _open_new_session(page, approval_web_server["url"])
    await page.fill(INPUT_SELECTOR, "run bash")
    await page.click(SEND_SELECTOR)
    await page.wait_for_selector(".tab-pane.active .approval-card", timeout=20000)
    session_tab = await page.get_attribute(".session-tab", "data-tab-id")
    await page.click("#hub-tab")  # 切到 hub 视图，模拟移动端切走页面

    await _drop_and_reconnect(page)

    # 用户切回该会话：重连补发的卡片就在那里。
    await page.click(f'.session-tab[data-tab-id="{session_tab}"]')
    await page.wait_for_selector(
        f'.tab-pane[data-tab-id="{session_tab}"].active .approval-card', timeout=20000
    )
    count = await page.eval_on_selector_all(
        f'.tab-pane[data-tab-id="{session_tab}"] .approval-card', "els => els.length"
    )
    assert count == 1, "重连补发产生了重复卡片（幂等守卫失效）"

    # 仍可作答，决定被接受、run 跑完。
    await page.click(".tab-pane.active .approval-approve")
    await page.wait_for_selector(".tab-pane.active .message.assistant", timeout=20000)
    assert await page.inner_text(".tab-pane.active .approval-status") == "approved"


@pytest.mark.asyncio
async def test_reconnect_replays_question_card_and_it_is_actionable(
    browser_page, browser_context, tmp_path
):
    """提问卡片同样在重连后补发并可作答。"""
    page = browser_page
    app = create_app(ScriptedLLM(_question_script()), workspace_root=tmp_path)
    port = _free_port()
    server, thread, base_url = _start_server(app, port)
    try:
        await _open_new_session(page, base_url)
        await page.fill(INPUT_SELECTOR, "ask me")
        await page.click(SEND_SELECTOR)
        await page.wait_for_selector(".tab-pane.active .question-card", timeout=20000)

        await _drop_and_reconnect(page)

        await page.wait_for_selector(".tab-pane.active .question-card", timeout=20000)
        ready = await page.eval_on_selector_all(
            ".tab-pane.active .question-card", "els => els.length"
        )
        assert ready == 1, "重连补发产生了重复提问卡片"

        # 选第一个选项并提交 → run 继续并跑完。
        await page.click(".tab-pane.active .question-option input")
        await page.click(".tab-pane.active .question-submit")
        await page.wait_for_selector(".tab-pane.active .message.assistant", timeout=20000)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_streaming_delta_after_reconnect_lands_in_live_dom(
    browser_page, browser_context, tmp_path
):
    """M12：``session_history`` 重绘后 ``currentAssistantMsg`` 必须被重置。

    run 正在流式输出时断连重连：``session_history`` 清空消息区，若游标仍指向已
    脱离文档的僵尸节点，重连后到达的 ``assistant_delta`` 会写进那个节点、用户什么
    也看不到。断言增量文本出现在当前文档里。
    """
    page = browser_page
    llm = GatedStreamLLM([])
    app = create_app(llm, workspace_root=tmp_path)
    port = _free_port()
    server, thread, base_url = _start_server(app, port)
    try:
        await _open_new_session(page, base_url)
        await page.fill(INPUT_SELECTOR, "讲一段话")
        await page.click(SEND_SELECTOR)
        await page.wait_for_selector(".tab-pane.active .message.assistant", timeout=20000)
        assert "断连前的前半段" in await page.inner_text(".tab-pane.active .tab-messages")

        assert await asyncio.get_running_loop().run_in_executor(
            None, llm.first_delta_sent.wait, 10
        ), "LLM 没有吐出第一个 delta"

        await _drop_and_reconnect(page)

        # 放行剩下的流式内容：必须先于重连后的 session_history 到达顺序无关——
        # 关键是它落在**重绘之后**的 DOM 上。
        await asyncio.get_running_loop().run_in_executor(None, llm.release.set)
        await page.wait_for_function(
            "document.querySelector('.tab-pane.active .tab-messages').textContent"
            ".includes('重连后的增量')",
            timeout=20000,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# ws 未就绪时的可见反馈（D5/M5）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_submit_when_ws_down_shows_feedback(
    browser_page, browser_context, approval_web_server
):
    """断连状态下点批准：给出可见反馈、不显示假的 'sent'、卡片保持可提交。"""
    page = browser_page
    await _open_new_session(page, approval_web_server["url"])
    await page.fill(INPUT_SELECTOR, "run bash")
    await page.click(SEND_SELECTOR)
    await page.wait_for_selector(".tab-pane.active .approval-card", timeout=20000)

    await page.evaluate("() => window.AsterwyndChatTest.dropConnection()")
    await _wait_connection_status(page, ("disconnected", "error"))
    await page.click(".tab-pane.active .approval-approve")

    status_text = await page.inner_text(".tab-pane.active .approval-status")
    assert status_text == "未连接，请等待重连后重试", status_text
    disabled = await page.eval_on_selector(
        ".tab-pane.active .approval-approve", "el => el.disabled"
    )
    assert disabled is False, "连接未就绪时卡片被禁用，用户重连后无法再提交"


@pytest.mark.asyncio
async def test_question_submit_when_ws_down_shows_feedback(
    browser_page, browser_context, tmp_path
):
    """断连状态下提交答案：给出可见反馈且卡片保持可提交（不静默丢弃）。"""
    page = browser_page
    app = create_app(ScriptedLLM(_question_script()), workspace_root=tmp_path)
    port = _free_port()
    server, thread, base_url = _start_server(app, port)
    try:
        await _open_new_session(page, base_url)
        await page.fill(INPUT_SELECTOR, "ask me")
        await page.click(SEND_SELECTOR)
        await page.wait_for_selector(".tab-pane.active .question-card", timeout=20000)

        await page.evaluate("() => window.AsterwyndChatTest.dropConnection()")
        await _wait_connection_status(page, ("disconnected", "error"))
        await page.click(".tab-pane.active .question-option input")
        await page.click(".tab-pane.active .question-submit")

        hint = await page.inner_text(".tab-pane.active .question-hint")
        assert "未连接" in hint, hint
        disabled = await page.eval_on_selector(
            ".tab-pane.active .question-submit", "el => el.disabled"
        )
        assert disabled is False, "连接未就绪时提交按钮被禁用，用户重连后无法再提交"
        label = await page.inner_text(".tab-pane.active .question-submit")
        assert label == "Submit", "连接未就绪却显示了假的 'Submitted'"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# 卡片幂等（D5）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_card_events_render_single_card(browser_page, approval_web_server):
    """同一 id 的卡片事件重复到达只渲染一张（幂等守卫）。

    真实链路里「同 id 重复」必然伴随 ``renderHistory`` 清空注册表（重连补发），
    因此这里显式派发两次同样的事件来单独验证守卫本身。
    """
    page = browser_page
    await _open_new_session(page, approval_web_server["url"])
    await _wait_connected(page)

    await page.evaluate("""
      () => {
        const dispatch = window.AsterwyndChatTest.dispatch;
        const approval = { approval_id: 'dup-1', tool_name: 'Bash', risk: 'high' };
        dispatch({ type: 'approval_request', data: approval });
        dispatch({ type: 'approval_request', data: approval });
        const question = { question_id: 'dup-2', title: 't', body: 'b', options: [] };
        dispatch({ type: 'user_question', data: question });
        dispatch({ type: 'user_question', data: question });
      }
    """)

    assert await page.eval_on_selector_all(
        ".tab-pane.active .approval-card", "els => els.length"
    ) == 1
    assert await page.eval_on_selector_all(
        ".tab-pane.active .question-card", "els => els.length"
    ) == 1


@pytest.mark.asyncio
async def test_session_history_clears_card_registry(browser_page, approval_web_server):
    """清空消息区（``session_history``）必须清卡片注册表，否则补发卡片被静默跳过。

    注入一张卡片 → 触发 ``session_history``（DOM 清空）→ 再用同一 id 注入卡片：
    有清注册表时会重新渲染出一张；没清就会命中僵尸条目、什么都不显示。
    """
    page = browser_page
    await _open_new_session(page, approval_web_server["url"])
    await _wait_connected(page)

    await page.evaluate("""
      () => {
        const dispatch = window.AsterwyndChatTest.dispatch;
        const approval = { approval_id: 'replay-1', tool_name: 'Bash', risk: 'high' };
        dispatch({ type: 'approval_request', data: approval });
        dispatch({ type: 'session_history', data: { messages: [] } });
        dispatch({ type: 'approval_request', data: approval });
      }
    """)

    assert await page.eval_on_selector_all(
        ".tab-pane.active .approval-card", "els => els.length"
    ) == 1

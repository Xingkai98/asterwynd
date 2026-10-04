# tests/web_tests/test_transcript_view_browser.py
"""Playwright 行为断言：harness 式 transcript（change ``harness-style-web-transcript``）。

验收 L0–L4 的浏览器侧证据：工具执行**默认只占一行**、点开才见参数与结果、失败在折叠
行上就可见、重连历史的 ``role: "tool"`` 渲染成带真名的折叠行而不是 user 泡泡。

事件用 ``window.AsterwyndChatTest.dispatch`` 直接派发（与
``test_reconnect_pending_interaction_browser.py`` 同一条测试接缝）：真实链路里要凑出
「20 次工具调用、每次 5000 字符结果」得跑真模型，而这里断言的是**渲染契约**，
不是 LLM 行为。断言的落点是用户能看到、能点到的东西（可见行数、可见文本长度、
展开后的文本），不是 chat.js 的源码字符串——源码断言对重构脆弱。

CI 无浏览器时自动 skip（与 ``test_multi_session_browser.py`` 同口径）。
"""
import asyncio
import socket
import threading
import time
import urllib.request

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.llm import LLMResponse
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app

PANE = ".tab-pane.active"
MESSAGES = f"{PANE} .tab-messages"
INPUT_SELECTOR = f"{PANE} .user-input"

# 折叠行的可见文本预算。实测 20 行 ≈ 600 字符（每行 = caret + 标题 + 摘要 + meta），
# 预算取 2 倍余量。**不能放松**：把摘要换成「结果前 150 字符」时 20×150+600=3600，
# 4000 的预算会让这种刷屏回归整片绿掉（grill Q5）。除总量外还有一条**结构断言**
# （每个摘要 ≤ 90 字符 + 结果片段不得出现在可见文本里），因为总量断言定位不到是哪
# 一行漏了。
VISIBLE_TEXT_BUDGET = 1200
SUMMARY_CHAR_LIMIT = 90
RESULT_SIZE = 5000
TOOL_COUNT = 20

# Bash 在 chat 的 WS 路径上的**真实**结果形态：`SandboxResult.to_json()` 单行 JSON
# （`agent/tools/builtin/bash.py` + `agent/tools/sandbox/base.py`）。`[Exit N] …` 是
# `SandboxResult.__str__` 的格式，线上不产生；用假形态写验收会让测试绿而生产样貌不同
# （grill Q2）。
BASH_FAILED_JSON = (
    '{"exit_code": 1, "stdout": "1 failed, 12 passed", "stderr": "", '
    '"duration_ms": 7345.2, "timed_out": false, "oom_killed": false, "degraded": false}'
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
def transcript_web_server(tmp_path):
    # 本文件不发消息，只借一个真实 WebSocket 会话把 tab 打开到可渲染状态。
    app = create_app(ScriptedLLM([LLMResponse(content="unused", stop_reason="end_turn")]),
                     workspace_root=tmp_path)
    port = _free_port()
    server, thread, base_url = _start_server(app, port)
    try:
        yield {"url": base_url, "app": app, "port": port}
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def _open_ready_session(page, base_url: str) -> None:
    await page.goto(base_url)
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    # 等异步 init() 落定：后到的 showHub() 会把被测视图的 active 摘掉。
    await page.wait_for_function("() => window.AsterwyndChatTest.initDone === true")


async def _dispatch(page, event: dict) -> None:
    await page.evaluate("(ev) => window.AsterwyndChatTest.dispatch(ev)", event)


def _tool_call(name: str, arguments: dict, call_id: str = "c1") -> dict:
    return {"type": "tool_call", "data": {"name": name, "arguments": arguments, "approval": None},
            "tool_call_id": call_id}


def _tool_result(name: str, result: str, collapsed: bool = True, preview_chars: int = 1200,
                 line_count: int = 1, call_id: str | None = None) -> dict:
    data = {
        "name": name,
        "result": result,
        "display": {
            "collapsed": collapsed,
            "preview": result[:preview_chars],
            "char_count": len(result),
            "line_count": line_count,
        },
    }
    if call_id:
        data["tool_call_id"] = call_id
    return {"type": "tool_result", "data": data}


def _preview_only_result(name: str, preview: str, char_count: int, line_count: int,
                         call_id: str) -> dict:
    """`tool-result-lifecycle` D12 之后的真实形态：**事件不带正文**，只有 preview + id。

    合并 origin/master 后这是 `tool_result` 的默认形态——折叠行必须只靠 preview 就能
    给出正确的判定与摘要，展开时再按 id 回取全文。
    """
    return {
        "type": "tool_result",
        "data": {
            "name": name,
            "tool_call_id": call_id,
            "display": {
                "collapsed": True,
                "preview": preview,
                "char_count": char_count,
                "line_count": line_count,
            },
        },
    }


# --- L0：默认一行、折叠态零结果正文 -----------------------------------------


@pytest.mark.asyncio
async def test_tool_rows_collapse_to_one_line_by_default(browser_page, transcript_web_server):
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])

    await page.evaluate(
        """({count, size}) => {
             const big = 'x'.repeat(size);
             for (let i = 0; i < count; i += 1) {
               window.AsterwyndChatTest.dispatch({
                 type: 'tool_call',
                 data: {name: 'Read', arguments: {path: 'src/file_' + i + '.py'}, approval: null},
               });
               window.AsterwyndChatTest.dispatch({
                 type: 'tool_result',
                 data: {
                   name: 'Read',
                   result: big,
                   display: {collapsed: true, preview: big.slice(0, 1200),
                             char_count: size, line_count: 1},
                 },
               });
             }
           }""",
        {"count": TOOL_COUNT, "size": RESULT_SIZE},
    )

    rows = await page.eval_on_selector_all(f"{MESSAGES} .tool-row", "els => els.length")
    assert rows == TOOL_COUNT, f"每次工具执行应恰好一行，实际 {rows}"

    bodies = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-body", "els => els.filter(e => e.hidden).length")
    assert bodies == TOOL_COUNT, f"折叠态 body 必须全部 hidden，实际 {bodies}/{TOOL_COUNT}"

    visible = await page.inner_text(MESSAGES)
    assert len(visible) < VISIBLE_TEXT_BUDGET, (
        f"折叠态可见文本 {len(visible)} 字符，超过预算 {VISIBLE_TEXT_BUDGET}——"
        "工具结果正文漏进了折叠行"
    )
    # 结构断言：逐行定位，避免总量断言掩盖「某一行泄漏了正文」。
    summaries = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-summary", "els => els.map(e => e.textContent)")
    assert len(summaries) == TOOL_COUNT
    for index, summary in enumerate(summaries):
        assert len(summary) <= SUMMARY_CHAR_LIMIT, f"第 {index} 行摘要过长：{summary[:200]}"
        assert "x" * 50 not in summary, f"第 {index} 行摘要里出现了结果正文"
    assert "x" * 200 not in visible


@pytest.mark.asyncio
async def test_tool_row_shows_summary_and_size_metadata(browser_page, transcript_web_server):
    """折叠行本身就是定位符：工具标题 + 参数摘要 + 规模元数据。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "web/static/chat.js"}))
    await _dispatch(page, _tool_result("Read", "line one\nline two"))

    heads = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-head", "els => els.map(e => e.innerText.replace(/\\s+/g, ' '))")
    assert len(heads) == 1
    assert "Read" in heads[0]
    assert "web/static/chat.js" in heads[0]
    assert "字符" in heads[0]


# --- 配对顺序（proposal R1 的回归承诺）--------------------------------------


@pytest.mark.asyncio
async def test_calls_and_results_pair_in_arrival_order(browser_page, transcript_web_server):
    """同一轮里多个同名调用：第 i 个结果必须落在第 i 行上。

    取「最近」而非「最早」未配对项会让三行全部错位（第 1 个结果贴到最后一行）。
    这条断言就是锁住方向的（grill Q4：原设计声称有此回归，实际没有）。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    for index in range(3):
        await _dispatch(page, _tool_call("Read", {"path": f"file_{index}.py"}))
    for index in range(3):
        await _dispatch(page, _tool_result("Read", f"content-of-{index}"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 3
    for index in range(3):
        summary = await rows.nth(index).locator(".tool-row-summary").inner_text()
        assert f"file_{index}.py" in summary, f"第 {index} 行的摘要错位：{summary}"
        await rows.nth(index).locator(".tool-row-head").click()
        body = await rows.nth(index).locator(".tool-row-body").inner_text()
        assert f"content-of-{index}" in body, f"第 {index} 行的结果错位：{body[:200]}"


@pytest.mark.asyncio
async def test_result_without_pending_row_creates_its_own_row(browser_page, transcript_web_server):
    """没有配对调用的结果（重连补发等）自己建行，绝不能被丢掉。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_result("Bash", "orphan output"))

    rows = await page.eval_on_selector_all(f"{MESSAGES} .tool-row", "els => els.length")
    assert rows == 1
    summary = await page.inner_text(f"{MESSAGES} .tool-row-summary")
    assert "orphan output" in summary


@pytest.mark.asyncio
async def test_pending_rows_settle_when_the_run_ends(browser_page, transcript_web_server):
    """run 结束时未等到结果的行不能继续显示「运行中」（grill Q4/R-E）。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "sleep 100"}))
    await _dispatch(page, {"type": "done", "data": {"content": "bye", "stop_reason": "end_turn"}})

    row = page.locator(f"{MESSAGES} .tool-row")
    assert await row.get_attribute("data-state") == "error"
    assert "未返回结果" in await row.locator(".tool-row-meta").inner_text()
    # 队列必须**同时**被清空，否则下一轮同名调用的结果会落在这条僵尸行上（见下一条用例）。
    depth = await page.evaluate("() => window.AsterwyndChatTest.pendingToolRowCount()")
    assert depth == 0, f"run 结束后未配对队列必须为空，实际残留 {depth} 条"


@pytest.mark.asyncio
async def test_clear_command_drops_pending_tool_rows(browser_page, transcript_web_server):
    """`/clear` 清空消息区时 MUST 同时清空未配对队列（spec「收尾」条款）。

    不清的后果实测是「清空前的行被重新挂回来」：清空后到达的 `tool_result` 会取走那条
    已脱离文档的僵尸行，`addToolResultMessage` 再把它 append 回消息区——用户看到一条
    带着**旧命令**摘要的行，而它承载的是新结果（review round 4 Issue 1，M3 变异存活）。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "pre-clear-command"}))
    await _dispatch(page, {
        "type": "command_result",
        "data": {"message": "cleared", "metadata": {"command": "clear"}, "continue_session": True},
    })

    depth = await page.evaluate("() => window.AsterwyndChatTest.pendingToolRowCount()")
    assert depth == 0, f"/clear 后未配对队列必须为空，实际残留 {depth} 条"
    assert await page.locator(f"{MESSAGES} .tool-row").count() == 0, "清空后不应有残留行"

    await _dispatch(page, _tool_result("Bash", "post-clear-output"))
    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 1
    summary = await rows.nth(0).locator(".tool-row-summary").inner_text()
    assert summary == "post-clear-output", (
        f"清空前的行被重新挂回来了（摘要仍是旧命令）：{summary!r}"
    )


@pytest.mark.asyncio
async def test_history_redraw_drops_pending_tool_rows(browser_page, transcript_web_server):
    """`session_history` 整体重绘时同样 MUST 清空未配对队列（同 spec 条款、另一条路径）。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "pre-history-command"}))
    await _dispatch(page, {"type": "session_history",
                           "data": {"session_id": "s1", "messages": []}})

    depth = await page.evaluate("() => window.AsterwyndChatTest.pendingToolRowCount()")
    assert depth == 0, f"重绘后未配对队列必须为空，实际残留 {depth} 条"

    await _dispatch(page, _tool_result("Bash", "post-history-output"))
    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 1
    summary = await rows.nth(0).locator(".tool-row-summary").inner_text()
    assert summary == "post-history-output", (
        f"重绘前的行被重新挂回来了（摘要仍是旧命令）：{summary!r}"
    )


@pytest.mark.asyncio
async def test_next_run_result_does_not_land_on_a_zombie_row(
    browser_page, transcript_web_server
):
    """上一轮未配对的僵尸行 MUST NOT 认领下一轮的结果。

    覆盖缺口来自 review Issue 1：只断言「僵尸行被标成 error」不够——如果队列没被清空，
    下一轮同名调用的 `tool_result` 会取走那条僵尸行，结果是「老行显示新结果（且看起来
    可信）+ 新行永远停在运行中」，全程没有任何错误信号。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "run-1-stuck"}))
    await _dispatch(page, {"type": "done", "data": {"content": "", "stop_reason": "end_turn"}})
    await _dispatch(page, _tool_call("Bash", {"cmd": "run-2-fresh"}))
    await _dispatch(page, _tool_result("Bash", "output-of-run-2"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 2

    first_state = await rows.nth(0).get_attribute("data-state")
    first_meta = await rows.nth(0).locator(".tool-row-meta").inner_text()
    first_summary = await rows.nth(0).locator(".tool-row-summary").inner_text()
    assert first_state == "error", "第一轮的僵尸行不得被下一轮结果改成成功态"
    assert "未返回结果" in first_meta
    assert first_summary == "run-1-stuck", "僵尸行的摘要不得被改成下一轮的参数"

    second_state = await rows.nth(1).get_attribute("data-state")
    assert second_state == "ok", "第二轮自己的行必须收到结果"
    await rows.nth(1).locator(".tool-row-head").click()
    body = await rows.nth(1).locator(".tool-row-body").inner_text()
    assert "output-of-run-2" in body

    # 僵尸行的展开体里不得出现下一轮的结果（内容张冠李戴的另一种表现）。
    await rows.nth(0).locator(".tool-row-head").click()
    zombie_body = await rows.nth(0).locator(".tool-row-body").inner_text()
    assert "output-of-run-2" not in zombie_body


# --- L1：展开可用 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_row_expands_on_click_and_collapses_again(browser_page, transcript_web_server):
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "uv run pytest -q"}))
    await _dispatch(page, _tool_result("Bash", "41 passed in 7.73s"))

    body = page.locator(f"{MESSAGES} .tool-row-body")
    assert await body.is_hidden(), "默认必须折叠"

    await page.click(f"{MESSAGES} .tool-row-head")
    assert await body.is_visible(), "点击头部后应展开"
    expanded = await body.inner_text()
    assert "uv run pytest -q" in expanded, "展开后应看到原始参数"
    assert "41 passed" in expanded, "展开后应看到完整结果"
    assert await page.get_attribute(f"{MESSAGES} .tool-row-head", "aria-expanded") == "true"

    await page.click(f"{MESSAGES} .tool-row-head")
    assert await body.is_hidden(), "再次点击应收起"
    assert await page.get_attribute(f"{MESSAGES} .tool-row-head", "aria-expanded") == "false"


@pytest.mark.asyncio
async def test_click_inside_expanded_body_does_not_collapse(browser_page, transcript_web_server):
    """展开体是头部按钮的**兄弟节点**：在正文里点选文本不应收起整行。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "echo hello"}))
    await _dispatch(page, _tool_result("Bash", "hello world"))
    await page.click(f"{MESSAGES} .tool-row-head")

    await page.click(f"{MESSAGES} .tool-row-body .tool-row-result")
    assert await page.locator(f"{MESSAGES} .tool-row-body").is_visible(), (
        "在展开体内部点击不应触发折叠切换"
    )


@pytest.mark.asyncio
async def test_expanded_body_shows_pretty_printed_arguments(browser_page, transcript_web_server):
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Edit", {"path": "a.py", "old_string": "x", "new_string": "y"}))
    await _dispatch(page, _tool_result("Edit", "edited"))
    await page.click(f"{MESSAGES} .tool-row-head")

    args_text = await page.inner_text(f"{MESSAGES} .tool-row-args")
    assert '"path": "a.py"' in args_text, f"参数应以缩进 JSON 展示，实际：{args_text}"


@pytest.mark.asyncio
async def test_no_note_when_arguments_are_not_truncated(browser_page, transcript_web_server):
    """未截断时不得出现「参数已截断」提示。

    截断态的**可见**断言在抽屉侧：`test_workflow_graph_browser.py` 的
    `test_convo_tab_survives_malformed_tool_arguments` 用 `inner_text` 断言提示渲染在
    头部行（review MEDIUM-3：原先只有一条 `text_content` 断言，而它连 hidden 子树一起
    取，看不出可见性——用例名与断言相反）。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, {
        "type": "session_history",
        "data": {
            "session_id": "s1",
            "messages": [
                {"role": "assistant", "content": "", "reasoning": None,
                 "tool_calls": [{"id": "t1", "name": "Read"}]},
                {"role": "tool", "content": "content", "reasoning": None, "tool_call_id": "t1"},
            ],
        },
    })
    unknown = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-note", "els => els.filter(e => !e.hidden).length")
    assert unknown == 0, "未截断时不应出现提示"


@pytest.mark.asyncio
async def test_history_row_summary_falls_back_to_result_first_line(
    browser_page, transcript_web_server
):
    """历史投影只带 id/name（不含 arguments），所以摘要必须降级为结果首行。

    否则重连后的工具行只剩一个工具名 + 空摘要（review MEDIUM-2 实测形态）。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, {
        "type": "session_history",
        "data": {
            "session_id": "s1",
            "messages": [
                {"role": "assistant", "content": "", "reasoning": None,
                 "tool_calls": [{"id": "t1", "name": "Bash"}]},
                {"role": "tool", "content": "1 failed, 12 passed\nsecond line",
                 "reasoning": None, "tool_call_id": "t1"},
            ],
        },
    })
    title = await page.inner_text(f"{MESSAGES} .tool-row-title")
    summary = await page.inner_text(f"{MESSAGES} .tool-row-summary")
    assert title == "Bash"
    assert summary == "1 failed, 12 passed", f"摘要应降级为结果首行，实际：{summary!r}"


@pytest.mark.asyncio
async def test_tool_row_height_is_fixed_regardless_of_payload_size(
    browser_page, transcript_web_server
):
    """行高 SHALL 不随参数/结果长度变化（spec「一行」条款的直接判据）。

    只断言行数/文本抓不到「有人把固定高度删掉、让长参数把行撑成多行」这类回归。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "a.py"}))
    await _dispatch(page, _tool_result("Read", "tiny"))
    await _dispatch(page, _tool_call("Bash", {"cmd": "echo " + "x" * 4000}))
    await _dispatch(page, _tool_result("Bash", "x" * 4000 + "\n".join([""] * 400)))

    heads = page.locator(f"{MESSAGES} .tool-row-head")
    assert await heads.count() == 2
    short_box = await heads.nth(0).bounding_box()
    long_box = await heads.nth(1).bounding_box()
    assert short_box and long_box
    assert abs(short_box["height"] - long_box["height"]) < 1, (
        f"行高随载荷变化：{short_box['height']} vs {long_box['height']}")
    assert long_box["height"] <= 26, f"折叠行应恒为单行（24px），实际 {long_box['height']}"


@pytest.mark.asyncio
async def test_tool_result_is_rendered_as_plain_text(browser_page, transcript_web_server):
    """结果里的 HTML SHALL 以纯文本展示，不得被解析成元素（spec 的 XSS 条款）。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    payload = '<img src=x onerror="window.__pwned=1"><b>bold</b>'
    await _dispatch(page, _tool_call("Bash", {"cmd": "echo html"}))
    await _dispatch(page, _tool_result("Bash", payload))
    await page.click(f"{MESSAGES} .tool-row-head")

    injected = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-body img, {MESSAGES} .tool-row-body b", "els => els.length")
    assert injected == 0, "工具结果里的 HTML 被当成标记解析了"
    pwned = await page.evaluate("() => window.__pwned === 1")
    assert pwned is False, "工具结果里的 onerror 被执行了"
    body = await page.inner_text(f"{MESSAGES} .tool-row-body")
    assert payload in body, f"结果应以纯文本原样展示，实际：{body[:200]}"


@pytest.mark.asyncio
async def test_transcript_uses_a_single_document_column(browser_page, transcript_web_server):
    """对话区是单列文档流：user 轮不是右对齐气泡，assistant 正文无气泡底色。

    只数 `.message.user` 个数抓不到「有人把气泡样式改回来」——这条断言直接看计算样式
    与几何位置。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, {"type": "session_history", "data": {
        "session_id": "s1",
        "messages": [
            {"role": "user", "content": "用户的一轮", "reasoning": None},
            {"role": "assistant", "content": "assistant 的正文", "reasoning": None},
        ],
    }})

    user_align = await page.eval_on_selector(
        f"{MESSAGES} .message.user", "el => getComputedStyle(el).alignSelf")
    assistant_bg = await page.eval_on_selector(
        f"{MESSAGES} .message.assistant", "el => getComputedStyle(el).backgroundColor")
    assistant_align = await page.eval_on_selector(
        f"{MESSAGES} .message.assistant", "el => getComputedStyle(el).alignSelf")
    # 右对齐气泡的判据：align-self 为 flex-end + 有底色。
    assert user_align != "flex-end", f"用户轮回到了右对齐气泡（align-self={user_align}）"
    assert assistant_align != "flex-end"
    assert assistant_bg in ("rgba(0, 0, 0, 0)", "transparent"), (
        f"assistant 正文不应有气泡底色，实际 {assistant_bg}")

    user_box = await page.locator(f"{MESSAGES} .message.user").bounding_box()
    assistant_box = await page.locator(f"{MESSAGES} .message.assistant").bounding_box()
    assert user_box and assistant_box
    # 同一列：两者的左边界对齐（不居中、不左右分列）。
    assert abs(user_box["x"] - assistant_box["x"]) < 2, (
        f"用户轮与 assistant 正文不在同一列：{user_box['x']} vs {assistant_box['x']}")


@pytest.mark.asyncio
async def test_reasoning_row_is_single_line_when_collapsed(browser_page, transcript_web_server):
    """思维链折叠区 SHALL 与工具行同款单行（spec「折叠态一行」条款）。

    只断言 `.message-reasoning-content` 的 hidden 抓不到「有人把整块带框容器改回来」——
    这条直接量高度：折叠态整块高度 == 标题行高度（24px），不随思维链长度变化。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, {"type": "assistant_delta", "data": {"delta": "回答正文"}})
    await _dispatch(page, {"type": "reasoning_delta",
                           "data": {"delta": "先看文件A。" * 400}})

    assert await page.locator(f"{MESSAGES} .message-reasoning-content").is_hidden()
    block = await page.locator(f"{MESSAGES} .message-reasoning").bounding_box()
    toggle = await page.locator(f"{MESSAGES} .message-reasoning-toggle").bounding_box()
    assert block and toggle
    assert toggle["height"] <= 26, f"思维链标题行应为单行 24px，实际 {toggle['height']}"
    assert block["height"] - toggle["height"] < 2, (
        f"折叠态整块高度应等于标题行高度（{toggle['height']}），实际 {block['height']}"
    )


# --- L4：失败在折叠行上可见，且不自动展开 -----------------------------------


@pytest.mark.asyncio
async def test_failed_structured_bash_result_keeps_command_while_collapsed(
    browser_page, transcript_web_server
):
    """Bash 失败：折叠行**保留命令**，失败信号进行尾 meta（grill Q2/R-B）。

    把结果首行（= 整个 JSON 信封）顶到摘要上，用户会看到
    ``▸ Bash · {"exit_code": 1, "stdout": …``——命令消失了，等于把定位符删掉。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "uv run pytest -q"}))
    await _dispatch(page, _tool_result("Bash", BASH_FAILED_JSON))

    row = page.locator(f"{MESSAGES} .tool-row")
    assert await row.get_attribute("data-state") == "error"
    assert await page.locator(f"{MESSAGES} .tool-row-body").is_hidden(), (
        "失败不得自动展开——那是最吵的场景"
    )
    summary = await row.locator(".tool-row-summary").inner_text()
    assert "uv run pytest -q" in summary, f"失败行应保留命令，实际：{summary}"
    assert "exit_code" not in summary, "JSON 信封不得顶到折叠摘要上"
    meta = await row.locator(".tool-row-meta").inner_text()
    assert "exit 1" in meta, f"行尾应给出退出码，实际：{meta}"


@pytest.mark.asyncio
async def test_failed_text_result_shows_first_line_while_collapsed(
    browser_page, transcript_web_server
):
    """可读的失败首行（审批被拒）顶到折叠摘要上——这是最常见的失败形态。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "rm -rf build"}))
    await _dispatch(page, _tool_result(
        "Bash",
        "[Approval denied: tool Bash was not approved in build mode: user said no]\n" + "y" * 4000,
    ))

    row = page.locator(f"{MESSAGES} .tool-row")
    assert await row.get_attribute("data-state") == "error"
    assert await page.locator(f"{MESSAGES} .tool-row-body").is_hidden()
    summary = await row.locator(".tool-row-summary").inner_text()
    assert "[Approval denied" in summary, f"折叠行应显示失败首行，实际：{summary}"
    assert "y" * 200 not in summary


@pytest.mark.asyncio
async def test_successful_result_keeps_argument_summary(browser_page, transcript_web_server):
    """成功结果不顶掉参数摘要——否则折叠行只剩「成功了」这种无信息量的文案。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Grep", {"pattern": "def main", "path": "agent/"}))
    await _dispatch(page, _tool_result("Grep", "agent/main.py:12:def main():"))

    summary = await page.inner_text(f"{MESSAGES} .tool-row-summary")
    assert "def main" in summary
    assert "agent/" in summary


# --- L3：重连历史保真 -------------------------------------------------------


@pytest.mark.asyncio
async def test_history_tool_messages_render_as_collapsed_rows(browser_page, transcript_web_server):
    """``role: "tool"`` 的历史消息 MUST 渲染成折叠行，而不是 user 泡泡。

    旧实现（``chat.js`` 把非 assistant 一律折成 user）会在重连后把所有工具结果铺成
    巨大的 user 泡泡——本 change 的 G3。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, {
        "type": "session_history",
        "data": {
            "session_id": "s1",
            "messages": [
                {"role": "user", "content": "读一下 AGENTS.md", "reasoning": None},
                {"role": "assistant", "content": "好的。", "reasoning": None,
                 "tool_calls": [{"id": "t1", "name": "Read"}]},
                {"role": "tool", "content": "z" * 5000, "reasoning": None, "tool_call_id": "t1"},
                {"role": "tool", "content": "second tool output", "reasoning": None},
            ],
        },
    })

    user_messages = await page.eval_on_selector_all(
        f"{MESSAGES} .message.user", "els => els.length")
    assert user_messages == 1, f"工具结果不得渲染成 user 泡泡（user 消息数 {user_messages}）"

    rows = await page.eval_on_selector_all(f"{MESSAGES} .tool-row", "els => els.length")
    assert rows == 2, f"两条历史工具结果应各占一行，实际 {rows}"

    bodies = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-body", "els => els.filter(e => e.hidden).length")
    assert bodies == 2, "历史工具行默认折叠"

    visible = await page.inner_text(MESSAGES)
    assert "z" * 200 not in visible, "历史工具结果正文不得铺进可见文本"

    # 工具名从 assistant 消息的 tool_calls 按 tool_call_id 反查回来（grill Q6）：
    # 12 行一模一样的「工具结果」是无法分辨的。
    titles = await page.eval_on_selector_all(
        f"{MESSAGES} .tool-row-title", "els => els.map(e => e.textContent)")
    assert titles[0] == "Read", f"有 id 的历史行应显示真工具名，实际：{titles}"
    assert titles[1] == "工具结果", f"无 id 的历史行退化为通用标题，实际：{titles}"


# --- 合并 origin/master 之后：事件只带 preview，展开时按 id 回取全文 ---------------
# `tool-result-lifecycle`（D12）把 `tool_result` 事件改成「preview + tool_call_id」，
# 正文改为展开时按需回取。折叠行必须只靠 preview 就给出正确判定（失败首行、结构化
# exit_code），否则长结果（正是最该显示失败的场景）会静默退化成「成功 + 空摘要」。


@pytest.mark.asyncio
async def test_preview_only_result_still_flags_the_failure(browser_page, transcript_web_server):
    """事件不带正文时，折叠行仍要报出失败（预览被截断的 Bash JSON 也要认出来）。"""
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])

    # 真实形态：`SandboxResult.to_json()` 的单行 JSON 被 1200 字符预览切在半截，
    # 整段 JSON.parse 必然失败——必须靠信封头部的 exit_code 字段兜住。
    long_stdout = "x" * 4000
    preview = '{"exit_code": 1, "stdout": "' + long_stdout[:900]
    await _dispatch(page, _tool_call("Bash", {"cmd": "uv run pytest -q"}, call_id="c9"))
    await _dispatch(page, _preview_only_result(
        "Bash", preview, char_count=len(preview) + 4000, line_count=1, call_id="c9"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 1
    assert await rows.nth(0).get_attribute("data-state") == "error", (
        "预览被截断的 JSON 信封仍须判为失败（否则失败静默消失）"
    )
    head = await rows.nth(0).locator(".tool-row-head").inner_text()
    assert "exit 1" in head, f"行尾应给出退出码，实际：{head!r}"
    assert "uv run pytest -q" in head, f"结构化失败要保留命令摘要，实际：{head!r}"


@pytest.mark.asyncio
async def test_short_result_without_a_result_field_is_rendered_and_judged(
    browser_page, transcript_web_server
):
    """**真实事件不带 `result`**（审阅 R6-M1）：短结果发 `collapsed:false` + preview=全文。

    只在 `collapsed` 为真时回落 preview 的话，所有短结果都会拿空串当文本依据 ⇒ 展开体
    空白、`[Approval denied…]` 这类失败被显示成**成功**。测试里显式构造「没有 result
    字段」的事件形态（而不是像其它用例那样自己塞一份 result）。
    """
    page = browser_page
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Bash", {"cmd": "rm -rf /tmp/x"}, call_id="c1"))
    await _dispatch(page, {
        "type": "tool_result",
        "data": {
            "name": "Bash",
            "tool_call_id": "c1",
            "display": {
                "collapsed": False,
                "preview": "[Approval denied: user rejected the request]",
                "char_count": 42,
                "line_count": 1,
            },
        },
    })

    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.nth(0).get_attribute("data-state") == "error", (
        "没有 result 字段的失败结果必须仍判为失败（否则失败静默消失）"
    )
    head = await rows.nth(0).locator(".tool-row-head").inner_text()
    assert "Approval denied" in head, f"失败首行应顶到摘要，实际：{head!r}"

    # 短结果的 preview 就是全文：展开应直接看到它，且**不需要**任何回取请求。
    await rows.nth(0).locator(".tool-row-head").click()
    body_text = await rows.nth(0).locator(".tool-row-result").inner_text()
    assert "Approval denied" in body_text, f"展开体不得为空，实际：{body_text!r}"
    assert "尚未取回全文" not in body_text, "preview 即全文时不该标成「未取回」"


@pytest.mark.asyncio
async def test_spilled_history_row_fetches_the_full_text_on_expand(
    browser_page, transcript_web_server
):
    """历史里的 spill 预览（`…[truncated; full result in result_ref: …]`）不是全文。

    历史投影给的是「预览 + 落盘 ref」形态，`result` 非空但**不是**全文（审阅 R6-M3）：
    必须判成 preview-only，展开按 id 回取，且 meta 不得把预览的长度说成结果的规模。
    """
    page = browser_page
    full = "@@SPILLED-FULL@@ " + "z" * 200
    calls: list[str] = []

    async def _result_route(route):
        calls.append(route.request.url)
        await route.fulfill(json={"tool_call_id": "c3", "missing": False, "content": full})

    await page.route("**/tool-result/*", _result_route)
    await _open_ready_session(page, transcript_web_server["url"])
    spilled = ("line one\nline two\n…[truncated; full result in result_ref: "
               "artifact://sha256/abc]")
    await _dispatch(page, {
        "type": "session_history",
        "data": {
            "session_id": "s1",
            "messages": [
                {"role": "assistant", "content": "", "tool_call_id": None,
                 "tool_calls": [{"id": "c3", "name": "Read"}]},
                {"role": "tool", "content": spilled, "tool_call_id": "c3",
                 "tool_calls": None},
            ],
        },
    })

    rows = page.locator(f"{MESSAGES} .tool-row")
    assert await rows.count() == 1
    head = await rows.nth(0).locator(".tool-row-head").inner_text()
    assert "预览" in head, f"只有预览时 meta 必须如实标注，实际：{head!r}"

    await rows.nth(0).locator(".tool-row-head").click()
    await page.wait_for_function(
        "() => document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('@@SPILLED-FULL@@')",
        timeout=5000,
    )
    assert calls and "/tool-result/c3" in calls[0], f"spill 预览应按 id 回取全文：{calls}"


@pytest.mark.asyncio
async def test_collapsing_releases_the_fetched_full_text(browser_page, transcript_web_server):
    """收起时释放已取回的全文（合并规格 `web-ui` 的 SHALL），再展开重新回取。"""
    page = browser_page
    full = "@@RELEASE-ME@@ " + "q" * 100
    calls: list[str] = []

    async def _result_route(route):
        calls.append(route.request.url)
        await route.fulfill(json={"tool_call_id": "c4", "missing": False, "content": full})

    await page.route("**/tool-result/*", _result_route)
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "big.txt"}, call_id="c4"))
    await _dispatch(page, _preview_only_result(
        "Read", "preview\nlines", char_count=20_000, line_count=500, call_id="c4"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    head = rows.nth(0).locator(".tool-row-head")
    await head.click()
    await page.wait_for_function(
        "() => document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('@@RELEASE-ME@@')",
        timeout=5000,
    )
    assert len(calls) == 1

    # 收起 → 全文必须从 DOM 里消失（内存里也不留 cachedFull）。
    await head.click()
    await page.wait_for_function(
        "() => !document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('@@RELEASE-ME@@')",
        timeout=5000,
    )
    assert await rows.nth(0).locator(".tool-row-body").is_hidden()

    # 再展开 → 重新回取（第二次请求）。
    await head.click()
    await page.wait_for_function(
        "() => document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('@@RELEASE-ME@@')",
        timeout=5000,
    )
    assert len(calls) == 2, f"收起后应释放、再展开应重新取：{calls}"


@pytest.mark.asyncio
async def test_collapsing_while_the_fetch_is_in_flight_still_releases(
    browser_page, transcript_web_server
):
    """回取在途时收起，全文也不得留在隐藏的展开体里（审阅 R7-N1）。

    那一刻 `releaseFullText` 会因 `__fullTextLoaded` 尚未置位而早退，于是 `.then` 到货后
    把长正文写进**已收起**的 body——释放整条契约被跳过（探针实测 DOM 里留下 213 字符）。
    """
    page = browser_page
    full = "@@LATE-FULL@@ " + "L" * 300

    async def _slow_result_route(route):
        await asyncio.sleep(0.6)          # 让「展开 → 立刻收起」发生在回取在途时
        await route.fulfill(json={"tool_call_id": "c5", "missing": False, "content": full})

    await page.route("**/tool-result/*", _slow_result_route)
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "big.txt"}, call_id="c5"))
    await _dispatch(page, _preview_only_result(
        "Read", "preview only", char_count=30_000, line_count=800, call_id="c5"))

    head = page.locator(f"{MESSAGES} .tool-row").nth(0).locator(".tool-row-head")
    await head.click()                     # 展开（回取开始）
    await head.click()                     # 立刻收起
    await page.wait_for_timeout(1500)      # 等回取到货

    body_text = await page.locator(f"{MESSAGES} .tool-row-result").nth(0).inner_text()
    assert "@@LATE-FULL@@" not in body_text, (
        f"回取在途时收起，全文仍被写进隐藏的展开体：{body_text[:80]!r}"
    )


@pytest.mark.asyncio
async def test_expanding_a_preview_only_row_fetches_the_full_text(
    browser_page, transcript_web_server
):
    """展开时按 `tool_call_id` 回取全文；取不到则如实写「全文不可用」。"""
    page = browser_page
    full = "@@FULL-TEXT@@ " + "y" * 300
    calls: list[str] = []

    async def _result_route(route):
        calls.append(route.request.url)
        await route.fulfill(json={"tool_call_id": "c7", "missing": False, "content": full})

    await page.route("**/tool-result/*", _result_route)
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "README.md"}, call_id="c7"))
    await _dispatch(page, _preview_only_result(
        "Read", "hello\nworld", char_count=99_000, line_count=1200, call_id="c7"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    head = await rows.nth(0).locator(".tool-row-head").inner_text()
    assert "99.0k" in head or "99k" in head, f"meta 取 display.char_count，实际：{head!r}"
    body = rows.nth(0).locator(".tool-row-body")
    assert await body.is_hidden(), "默认必须折叠"

    await rows.nth(0).locator(".tool-row-head").click()
    await page.wait_for_function(
        "() => document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('@@FULL-TEXT@@')",
        timeout=5000,
    )
    assert calls and "/tool-result/c7" in calls[0], f"应按 id 回取全文，实际请求：{calls}"


@pytest.mark.asyncio
async def test_expanding_when_the_full_text_is_gone_says_so(
    browser_page, transcript_web_server
):
    """服务端答 `missing` 时如实写「全文不可用」，**不拿预览冒充全文**。"""
    page = browser_page

    async def _result_route(route):
        await route.fulfill(json={"tool_call_id": "c8", "missing": True,
                                  "reason": "message_evicted"})

    await page.route("**/tool-result/*", _result_route)
    await _open_ready_session(page, transcript_web_server["url"])
    await _dispatch(page, _tool_call("Read", {"path": "big.txt"}, call_id="c8"))
    await _dispatch(page, _preview_only_result(
        "Read", "preview-only", char_count=50_000, line_count=900, call_id="c8"))

    rows = page.locator(f"{MESSAGES} .tool-row")
    await rows.nth(0).locator(".tool-row-head").click()
    await page.wait_for_function(
        "() => document.querySelector('.tool-row-body .tool-row-result')"
        ".textContent.includes('全文不可用')",
        timeout=5000,
    )
    result_text = await rows.nth(0).locator(".tool-row-result").inner_text()
    assert "preview-only" not in result_text, (
        f"取不到全文时不得用预览冒充全文，实际：{result_text!r}"
    )

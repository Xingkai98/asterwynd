# tests/web_tests/test_multi_session_browser.py
"""Playwright browser tests for the multi-session hub (issue #117).

Covers: hub session list + open tab, multi-tab isolation, refresh restore,
delete closes tab. Uses a tmp_path workspace with a pre-seeded session store.
"""
import socket
import threading
import time
import urllib.request

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.llm import LLMResponse
from agent.message import Message
from agent.run_config import AgentMode
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app

INPUT_SELECTOR = ".tab-pane.active .user-input"
SEND_SELECTOR = ".tab-pane.active .send-btn"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _seed_session(workspace_root, session_id: str, content: str = "历史消息"):
    store = SessionStore(str(workspace_root / ".asterwynd" / "sessions"))
    store.save(SessionSnapshot(
        schema_version=CURRENT_SCHEMA_VERSION,
        session_id=session_id,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        messages=[Message(role="user", content=content)],
        mode=AgentMode.BUILD,
        todos=[],
        active_skills=[],
        run_id="run-1",
        iteration=0,
        user_system_prompt="",
        runtime_fingerprint={},
    ))
    return store


@pytest.fixture
async def page():
    from playwright.async_api import Error as PlaywrightError, async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"playwright chromium unavailable: {exc}")
        context = await browser.new_context()
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        yield page
        if errors:
            pytest.fail(f"Browser JS errors: {errors}")
        await context.close()
        await browser.close()


@pytest.fixture
def seeded_web_server(tmp_path):
    """Web UI with tmp_path workspace, pre-seeded session aaaa11111111."""
    import uvicorn

    _seed_session(tmp_path, "aaaa11111111", "历史消息")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    llm = ScriptedLLM([LLMResponse(content="Fake browser response", stop_reason="end_turn")])
    app = create_app(llm, workspace_root=tmp_path)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
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
        pytest.fail("seeded web server failed to start")
    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.asyncio
async def test_hub_lists_session_and_opens_tab(page, seeded_web_server):
    """hub 列出预置会话；点打开进入 tab 并展示历史。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.wait_for_selector(".hub-session-row")

    rows = await page.query_selector_all(".hub-session-row")
    assert len(rows) == 1
    row_text = await rows[0].inner_text()
    assert "aaaa11111111" in row_text
    assert "历史消息" not in row_text  # 列表不显示消息内容

    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.wait_for_selector(".tab-pane.active .message.user")
    texts = await page.inner_text(".tab-pane.active .tab-messages")
    assert "历史消息" in texts


@pytest.mark.asyncio
async def test_multi_tab_independent_messages(page, seeded_web_server):
    """两个 tab 各自独立消息容器，切换 tab 后互不串扰。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    # 打开预置会话 tab
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    # 回 hub 新建第二个会话
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 2"
    )

    # 在新建（active）tab 发消息
    await page.fill(INPUT_SELECTOR, "第二条消息")
    await page.click(SEND_SELECTOR)
    await page.wait_for_selector(".tab-pane.active .message.assistant")

    # 切到第一个 tab：不应有第二条消息，历史仍在
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    texts1 = await page.inner_text('.tab-pane[data-tab-id="aaaa11111111"] .tab-messages')
    assert "历史消息" in texts1
    assert "第二条消息" not in texts1

    # 切到第二个 tab：有第二条消息与 fake 回复
    second_tab = '.session-tab:not([data-tab-id="aaaa11111111"])'
    await page.click(second_tab)
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active').dataset.tabId !== 'aaaa11111111'"
    )
    texts2 = await page.inner_text(".tab-pane.active .tab-messages")
    assert "第二条消息" in texts2
    assert "Fake browser response" in texts2


@pytest.mark.asyncio
async def test_refresh_returns_to_recent_session(page, seeded_web_server):
    """刷新后回到最近使用的会话（localStorage 记忆 session id + workspace）。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.wait_for_function(
        "localStorage.getItem('asterwynd.session_id') === 'aaaa11111111'"
    )

    await page.reload()
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.wait_for_selector(".tab-pane.active .message.user")
    texts = await page.inner_text(".tab-pane.active .tab-messages")
    assert "历史消息" in texts


@pytest.mark.asyncio
async def test_delete_session_closes_tab(page, seeded_web_server):
    """hub 删除会话后，已打开的同 id tab 被关闭。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')

    # 回 hub 删除
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active")
    page.on("dialog", lambda dialog: dialog.accept())
    await page.click(".hub-session-delete")

    # tab 关闭，无会话 tab 残留
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 0"
    )
    await page.wait_for_selector(".hub-empty")


@pytest.mark.asyncio
async def test_new_session_respects_mode(page, seeded_web_server):
    """新建会话表单可选 mode/workspace，打开后进入对应模式。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    # 等 hub 填充完成（workspaces/新会话表单就绪）再操作
    await page.wait_for_function(
        "document.querySelector('#hub-new-workspace').options.length > 0"
    )
    await page.select_option("#hub-new-mode", "read_only")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    await page.wait_for_function(
        "document.querySelector('#mode-value').textContent === 'read_only'"
    )


# ─── per-tab 隔离（design review I5/I13）───────────────────────────────


@pytest.mark.asyncio
async def test_multi_tab_slash_suggestion_isolation(page, seeded_web_server):
    """两个 tab 的 slash 匹配状态互不串扰：tab1 输 /s 出建议，切到 tab2 无建议。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 2"
    )

    # tab2（active）输 /s：建议只出现在 tab2
    await page.fill(INPUT_SELECTOR, "/s")
    await page.wait_for_selector(".tab-pane.active .slash-suggestions:not([hidden])")

    # 切到 tab1：无建议（tab1 自己的 slashSuggestionsEl 是独立的，hidden）
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    suggestions_hidden = await page.evaluate(
        "document.querySelector('.tab-pane[data-tab-id=\"aaaa11111111\"] .slash-suggestions').hidden"
    )
    assert suggestions_hidden

    # 切回 tab2：建议仍在
    second_tab = '.session-tab:not([data-tab-id="aaaa11111111"])'
    await page.click(second_tab)
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active .slash-suggestions') && "
        "!document.querySelector('.tab-pane.active .slash-suggestions').hidden"
    )


@pytest.mark.asyncio
async def test_multi_tab_image_preview_isolation(page, seeded_web_server):
    """图片预览只落各自 tab：tab2 传图，tab1 预览区为空。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 2"
    )

    # 构造一个极小 PNG 上传到 tab2（active）的 file input
    import base64
    png_b64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==")
    await page.set_input_files(
        ".tab-pane.active .image-file-input",
        {"name": "tiny.png", "mimeType": "image/png", "buffer": base64.b64decode(png_b64)},
    )
    await page.wait_for_selector(".tab-pane.active .image-preview-item")

    # 切到 tab1：预览区为空
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    preview_count = await page.evaluate(
        "document.querySelectorAll('.tab-pane[data-tab-id=\"aaaa11111111\"] .image-preview-item').length"
    )
    assert preview_count == 0


@pytest.mark.asyncio
async def test_multi_tab_exit_does_not_affect_other_tab_reconnect(page, seeded_web_server):
    """一个 tab 结束（/exit → continue_session=false）不影响另一 tab reconnect。"""
    await page.goto(seeded_web_server)
    await page.wait_for_selector("#hub-view.active")
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active")
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR)
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 2"
    )
    # tab2（active）执行 /exit → 该 tab 会话结束
    await page.fill(INPUT_SELECTOR, "/exit")
    await page.click(SEND_SELECTOR)
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active .message.system') !== null"
    )
    # tab2 WS 关闭（server 端 continue_session=false 会 close）——tab2 是 active，
    # 其 shouldReconnect=false，状态灯应显示 ended 而非 connected。
    await page.wait_for_function(
        "['ended', 'disconnected'].includes(document.querySelector('#status').textContent)"
    )

    # 切到 tab1：仍可正常发送并收到回复（reconnect 未被全局禁用）
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
    await page.wait_for_function(
        "document.querySelector('#status').textContent === 'connected'"
    )
    await page.fill('.tab-pane[data-tab-id="aaaa11111111"] .user-input', "还在吗")
    await page.click('.tab-pane[data-tab-id="aaaa11111111"] .send-btn')
    await page.wait_for_selector(
        '.tab-pane[data-tab-id="aaaa11111111"] .message.assistant',
        timeout=15000,
    )


@pytest.mark.asyncio
async def test_multi_tab_approval_isolation(page, tmp_path):
    """审批卡片只落各自 tab：tab1 触发 Bash 审批，tab2 无卡片。"""
    import uvicorn
    from agent.llm import ToolCallDelta

    _seed_session(tmp_path, "aaaa11111111", "历史消息")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Bash", arguments='{"cmd": "printf isolation"}')],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="done after tool", stop_reason="end_turn"),
    ])
    app = create_app(llm, workspace_root=tmp_path)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="off",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/api/debug-status", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    try:
        await page.goto(base_url)
        await page.wait_for_selector("#hub-view.active")
        await page.click(".hub-session-open")
        await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active')
        # tab2 新建并激活
        await page.click("#hub-tab")
        await page.wait_for_selector("#hub-view.active")
        await page.click("#hub-new-btn")
        await page.wait_for_selector(INPUT_SELECTOR)
        await page.wait_for_function(
            "document.querySelectorAll('.session-tab').length === 2"
        )
        # 在 tab2（active）发消息触发 Bash 工具 → approval_request
        await page.fill(INPUT_SELECTOR, "run bash")
        await page.click(SEND_SELECTOR)
        # tab2 出现审批卡片
        await page.wait_for_selector(".tab-pane.active .approval-card", timeout=15000)
        # tab1 无审批卡片
        count = await page.evaluate(
            "document.querySelectorAll('.tab-pane[data-tab-id=\"aaaa11111111\"] .approval-card').length"
        )
        assert count == 0
        # 处理 tab2 审批后收到 assistant 回复
        await page.click(".tab-pane.active .approval-approve")
        await page.wait_for_selector(".tab-pane.active .message.assistant", timeout=15000)
    finally:
        server.should_exit = True
        thread.join(timeout=5)

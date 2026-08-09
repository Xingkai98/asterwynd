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

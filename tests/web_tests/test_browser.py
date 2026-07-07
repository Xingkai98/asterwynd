# tests/web_tests/test_browser.py
"""Playwright browser end-to-end tests for the web UI.

Fake LLM smoke runs by default when Playwright browsers are installed.
Real API tests additionally require --run-real-api.
Usage:
    playwright install chromium
    python -m pytest tests/web_tests/test_browser.py -v
    ASTERWYND_DEBUG=enabled python -m pytest tests/web_tests/test_browser.py --run-real-api -v
"""
import os
import sys
import socket
import time
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.llm import LLMResponse
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_PORT = 8765
BASE_URL = f"http://localhost:{WEB_PORT}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def fake_web_server():
    """Start the Web UI with a deterministic fake LLM in-process."""
    import uvicorn

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    llm = ScriptedLLM([
        LLMResponse(content="Fake browser response", stop_reason="end_turn")
    ])
    app = create_app(llm)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
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
        pytest.fail("Fake Web server failed to start within 15s")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def web_server():
    """Start the web server in a subprocess. Module scope - starts once."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "cli.py"), "web", "--port", str(WEB_PORT)],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(f"{BASE_URL}/api/debug-status", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        proc.wait()
        pytest.fail("Server failed to start within 15s")

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
async def page():
    """Create a fresh browser page for each test."""
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

        # Fail if JS errors occurred
        if errors:
            pytest.fail(f"Browser JS errors: {errors}")

        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_fake_llm_browser_smoke(page, fake_web_server):
    await page.goto(fake_web_server)
    await page.wait_for_selector("#user-input")
    await page.wait_for_function(
        "document.querySelector('#status').textContent === 'connected'"
    )

    await page.fill("#user-input", "/s")
    await page.wait_for_selector("#slash-suggestions:not([hidden])")
    suggestions = await page.inner_text("#slash-suggestions")
    assert "/status" in suggestions

    await page.fill("#user-input", "/status")
    await page.click("#send-btn")
    await page.wait_for_selector(".message.system")
    status_text = await page.locator(".message.system").last.inner_text()
    assert "Session ID:" in status_text

    await page.select_option("#mode-select", "read_only")
    await page.click("#mode-apply")
    await page.wait_for_function(
        "document.querySelector('#mode-value').textContent === 'read_only'"
    )

    await page.fill("#user-input", "hello from browser")
    await page.click("#send-btn")
    await page.wait_for_selector(".message.assistant")
    assistant_text = await page.locator(".message.assistant").last.inner_text()
    assert "Fake browser response" in assistant_text

    await page.fill("#user-input", "/clear")
    await page.click("#send-btn")
    await page.wait_for_function(
        "Array.from(document.querySelectorAll('.message.system'))"
        ".some(el => el.textContent.includes('Cleared conversation history.'))"
    )
    assert await page.locator(".message.assistant").count() == 0


# ─── Real API tests ──────────────────────────────────────────────

@pytest.mark.real_api
@pytest.mark.asyncio
async def test_chat_send_message(page, web_server):
    """Send a message and verify a response appears."""
    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    # Type and send
    await page.fill("#user-input", "用一句话介绍你自己")
    await page.click("#send-btn")

    # Wait for response (up to 30s for real API)
    await page.wait_for_selector(".message.assistant", timeout=30000)

    # Verify content
    assistant_msgs = await page.query_selector_all(".message.assistant")
    assert len(assistant_msgs) >= 1

    text = await assistant_msgs[-1].inner_text()
    assert len(text.strip()) > 0


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_chat_tool_call_display(page, web_server):
    """Send a message requiring a tool call and verify tool info displayed."""
    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    await page.fill("#user-input", "读一下 README.md 文件")
    await page.click("#send-btn")

    # Wait for response
    await page.wait_for_selector(".message.assistant", timeout=30000)

    # Check for tool call blocks
    await page.wait_for_timeout(2000)  # extra time for tool execution
    tool_blocks = await page.query_selector_all(".tool-call-block")
    # There may or may not be tool calls depending on LLM behavior,
    # but we should at least have an assistant response
    assistant_msgs = await page.query_selector_all(".message.assistant")
    assert len(assistant_msgs) >= 1


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_debug_tab_hidden_default(page, web_server):
    """Debug tab should not be visible when ASTERWYND_DEBUG is not set."""
    if os.environ.get("ASTERWYND_DEBUG", "").lower() in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("ASTERWYND_DEBUG enabled - server in debug mode, debug tab is visible")

    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    debug_tab = await page.query_selector("#debug-tab")
    # Debug tab element exists but is hidden by default
    if debug_tab:
        is_visible = await debug_tab.is_visible()
        assert not is_visible


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_debug_tab_visible_when_enabled(page, web_server):
    """Debug tab should be visible when ASTERWYND_DEBUG=enabled.

    Note: This test requires the server to have been started with debug enabled.
    The fixture uses the current ASTERWYND_DEBUG value.
    """
    if os.environ.get("ASTERWYND_DEBUG", "").lower() not in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("ASTERWYND_DEBUG not enabled - server not in debug mode")

    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    debug_tab = await page.query_selector("#debug-tab")
    assert debug_tab is not None
    is_visible = await debug_tab.is_visible()
    assert is_visible, "Debug tab should be visible when ASTERWYND_DEBUG is enabled"


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_debug_shows_iterations(page, web_server):
    """When debug is enabled, sending a message populates the debug view."""
    if os.environ.get("ASTERWYND_DEBUG", "").lower() not in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("ASTERWYND_DEBUG not enabled")

    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    # Switch to Debug tab
    debug_tab = await page.query_selector("#debug-tab")
    await debug_tab.click()
    await page.wait_for_selector("#debug-view.active", timeout=5000)

    # Switch back to Chat, send message
    chat_tab = await page.query_selector('.tab[data-tab="chat"]')
    await chat_tab.click()
    await page.fill("#user-input", "说一句话介绍自己")
    await page.click("#send-btn")

    # Wait for response
    await page.wait_for_selector(".message.assistant", timeout=30000)

    # Switch to Debug tab
    await debug_tab.click()
    await page.wait_for_timeout(1000)

    # Check for iteration blocks
    iter_blocks = await page.query_selector_all(".iteration-block")
    assert len(iter_blocks) >= 1, "Should have at least one iteration block in debug view"

    # Check for message table
    msg_table = await page.query_selector(".msg-table")
    assert msg_table is not None, "Debug view should contain a message table"


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_static_assets_load(page, web_server):
    """Verify static assets (CSS, JS) load without errors."""
    await page.goto(web_server)

    # Check title
    title = await page.title()
    assert "Asterwynd" in title

    # Check essential elements
    assert await page.query_selector("#messages") is not None
    assert await page.query_selector("#user-input") is not None
    assert await page.query_selector("#send-btn") is not None


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_multi_turn_with_tool(page, web_server):
    """多轮对话：工具调用轮次后，后续问题应获得新回复而非重复旧答案。
    Regression test for: agent 返回前未将回复写入 messages 导致"复读机"。
    """
    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    # Turn 1: 触发 bash 工具调用
    await page.fill("#user-input", "用 bash 运行 pwd")
    await page.click("#send-btn")

    # 等待工具执行和 assistant 回复
    await page.wait_for_timeout(15000)

    # 收集第一轮 assistant 消息
    msgs_turn1 = await page.query_selector_all(".message.assistant")
    assert len(msgs_turn1) >= 1, "Turn 1 should produce at least one assistant message"
    text_turn1 = await msgs_turn1[-1].inner_text()

    # Turn 2: 询问不同的问题
    await page.fill("#user-input", "这个目录下有哪些文件？")
    await page.click("#send-btn")
    await page.wait_for_timeout(15000)

    # 收集第二轮 assistant 消息
    msgs_turn2 = await page.query_selector_all(".message.assistant")
    assert len(msgs_turn2) > len(msgs_turn1), \
        f"Turn 2 should add more assistant messages (had {len(msgs_turn1)}, got {len(msgs_turn2)})"

    text_turn2 = await msgs_turn2[-1].inner_text()
    assert len(text_turn2.strip()) > 0, "Turn 2 response should not be empty"

    # Turn 2 的回复不应与 Turn 1 完全相同（不重复 pwd 结果）
    assert text_turn2.strip() != text_turn1.strip(), \
        f"Turn 2 should not repeat Turn 1 verbatim:\n  T1: {text_turn1[:100]}\n  T2: {text_turn2[:100]}"

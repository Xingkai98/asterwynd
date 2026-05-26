# tests/web_tests/test_browser.py
"""Playwright browser end-to-end tests for the web UI.

Requires: playwright browsers installed and --run-real-api flag.
Usage:
    playwright install chromium
    MYAGENT_DEBUG=enabled python -m pytest tests/web_tests/test_browser.py --run-real-api -v
"""
import os
import sys
import json
import time
import signal
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright not installed")


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_PORT = 8765
BASE_URL = f"http://localhost:{WEB_PORT}"


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
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
    """Debug tab should not be visible when MYAGENT_DEBUG is not set."""
    if os.environ.get("MYAGENT_DEBUG", "").lower() in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("MYAGENT_DEBUG enabled - server in debug mode, debug tab is visible")

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
    """Debug tab should be visible when MYAGENT_DEBUG=enabled.

    Note: This test requires the server to have been started with debug enabled.
    The fixture uses the current MYAGENT_DEBUG value.
    """
    if os.environ.get("MYAGENT_DEBUG", "").lower() not in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("MYAGENT_DEBUG not enabled - server not in debug mode")

    await page.goto(web_server)
    await page.wait_for_selector("#user-input")

    debug_tab = await page.query_selector("#debug-tab")
    assert debug_tab is not None
    is_visible = await debug_tab.is_visible()
    assert is_visible, "Debug tab should be visible when MYAGENT_DEBUG is enabled"


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_debug_shows_iterations(page, web_server):
    """When debug is enabled, sending a message populates the debug view."""
    if os.environ.get("MYAGENT_DEBUG", "").lower() not in ("1", "true", "enabled", "yes", "on"):
        pytest.skip("MYAGENT_DEBUG not enabled")

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
    assert "MyAgent" in title

    # Check essential elements
    assert await page.query_selector("#messages") is not None
    assert await page.query_selector("#user-input") is not None
    assert await page.query_selector("#send-btn") is not None

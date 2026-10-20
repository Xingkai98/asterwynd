# tests/web_tests/test_group_status_browser.py
"""群聊成员状态栏的浏览器 smoke（change web-agent-group-member-status）。

覆盖 Q1=A 的 390px 形态（56px 横向条、约 3 人可见、可横向滑动、时间线让位）、
桌面 presence、真实房间 WS 事件驱动、反定时器、头部生命周期、公告保留、
独立 aria-live 与脚本加载顺序。
"""
import asyncio
import json
import socket
import threading

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app

BROWSER_TIMEOUT_MS = 15000


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
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        yield page
        await browser.close()
        if errors:
            pytest.fail(f"Browser JS errors: {errors}")


@pytest.fixture
def group_server(tmp_path):
    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    llm = ScriptedLLM(default_response=LLMResponse(content="ok"))
    app = create_app(llm, config=AsterwyndConfig(), workspace_root=tmp_path)
    loops: dict = {}

    @app.on_event("startup")
    async def _capture_loop():
        loops["loop"] = asyncio.get_running_loop()

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        import time

        time.sleep(0.05)
    assert server.started and loops.get("loop") is not None
    yield {"url": f"http://127.0.0.1:{port}", "app": app, "loop": loops["loop"]}
    server.should_exit = True
    thread.join(timeout=5)


async def _api(page, url, method, path, payload=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    response = await page.request.fetch(
        f"{url}{path}",
        method=method,
        data=json.dumps(payload) if payload is not None else None,
        headers=headers,
    )
    assert response.ok, await response.text()
    return await response.json()


async def _create_room(page, url, names, notice=""):
    personas = {}
    for name in names:
        body = await _api(page, url, "POST", "/api/team/personas", {"name": name})
        personas[name] = body["persona"]["id"]
    room = await _api(page, url, "POST", "/api/team/rooms", {
        "name": "状态房间",
        "members": list(personas.values()),
        "admin": personas[names[0]],
        "notice": notice,
    })
    return personas, room["room"]["id"]


async def _push(group_server, room_id, event_type, data):
    payload = {"type": event_type, "data": dict(data, room_id=room_id)}
    future = asyncio.run_coroutine_threadsafe(
        group_server["app"].state.room_bus.broadcast(room_id, payload),
        group_server["loop"],
    )
    await asyncio.wrap_future(future)


async def _open_group(page, group_server, room_id):
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.click("#group-room-list .group-item-name")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '已连接'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_function(
        "() => { const row = document.querySelector('.group-presence-row');"
        " return row && !row.classList.contains('stale'); }",
        timeout=BROWSER_TIMEOUT_MS,
    )


@pytest.mark.asyncio
async def test_group_presence_desktop_events_and_lifecycle(page, group_server):
    await page.set_viewport_size({"width": 1200, "height": 800})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    personas, room_id = await _create_room(
        page, group_server["url"], ["甲", "乙"], notice="先说结论"
    )
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.click("#group-room-list .group-item-name")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '已连接'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_function(
        "() => { const row = document.querySelector('.group-presence-row');"
        " return row && !row.classList.contains('stale'); }",
        timeout=BROWSER_TIMEOUT_MS,
    )

    assert await page.text_content("#group-room-notice") == "先说结论"
    geometry = await page.evaluate(
        """() => {
          const sidebar = document.querySelector('#group-sidebar').getBoundingClientRect();
          const presence = document.querySelector('#group-room-presence').getBoundingClientRect();
          const timeline = document.querySelector('#group-room-timeline').getBoundingClientRect();
          return {
            sidebarRight: sidebar.right,
            presenceLeft: presence.left,
            presenceRight: presence.right,
            timelineLeft: timeline.left,
          };
        }"""
    )
    assert geometry["sidebarRight"] <= geometry["presenceLeft"] + 1, geometry
    assert geometry["presenceRight"] <= geometry["timelineLeft"] + 1, geometry
    initial = await page.eval_on_selector_all(
        ".group-presence-status", "els => els.map(e => e.textContent)"
    )
    assert set(initial) == {"空闲"}

    await _push(group_server, room_id, "member_status", {
        "status_seq": 1,
        "statuses": [{
            "persona_id": personas["甲"],
            "phase": "tool",
            "tools": ["Bash"],
            "tool_count": 1,
        }],
    })
    await page.wait_for_function(
        "() => document.querySelector('.group-presence-row.phase-tool"
        " .group-presence-status')?.textContent.includes('Bash')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert "甲" in await page.text_content("#group-presence-live")

    # 反定时器：没有新事件时状态不变（等待覆盖既有 2s 重连节奏）。
    before = await page.text_content(
        ".group-presence-row.phase-tool .group-presence-status"
    )
    await page.wait_for_timeout(3000)
    after = await page.text_content(
        ".group-presence-row.phase-tool .group-presence-status"
    )
    assert after == before

    # 头部轮次提示：终态写入，新一轮 user_message 清除。
    await _push(group_server, room_id, "round_ended", {
        "termination": "completed", "status_seq": 2, "limit": 10,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent.includes('本轮结束')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await _push(group_server, room_id, "user_message", {
        "text": "新一轮", "seq": 10, "queued": False,
    })
    await page.wait_for_function(
        "() => !document.querySelector('#group-room-status').textContent.includes('本轮结束')",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # 状态更新不打断时间线滚动。
    scroll_before = await page.eval_on_selector("#group-room-timeline", "e => e.scrollTop")
    await _push(group_server, room_id, "member_status", {
        "status_seq": 3,
        "statuses": [{
            "persona_id": personas["甲"],
            "phase": "typing",
            "tools": [],
            "tool_count": 0,
        }],
    })
    await page.wait_for_selector(".group-presence-row.phase-typing")
    assert await page.eval_on_selector("#group-room-timeline", "e => e.scrollTop") == scroll_before


@pytest.mark.asyncio
async def test_group_presence_mobile_q1_strip(page, group_server):
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # 空状态提供抽屉入口；打开/关闭侧栏。
    await page.click("#group-tab")
    await page.wait_for_selector("#group-empty-drawer", state="visible")
    await page.click("#group-empty-drawer")
    await page.wait_for_selector("#group-sidebar.open")
    assert await page.is_visible("#group-sidebar-scrim")
    # 侧栏宽 280px；点遮罩右侧（侧栏之外）才能命中遮罩。
    await page.mouse.click(370, 100)
    await page.wait_for_function(
        "() => !document.querySelector('#group-sidebar').classList.contains('open')"
    )

    personas, room_id = await _create_room(
        page, group_server["url"], ["甲", "乙", "丙", "丁", "戊"]
    )
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.click("#group-empty-drawer")
    await page.wait_for_selector("#group-sidebar.open")
    await page.click("#group-room-list .group-item-name")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '已连接'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_function(
        "() => { const row = document.querySelector('.group-presence-row');"
        " return row && !row.classList.contains('stale'); }",
        timeout=BROWSER_TIMEOUT_MS,
    )

    metrics = await page.evaluate(
        """() => {
          const strip = document.querySelector('#group-room-presence');
          const list = document.querySelector('#group-presence-list');
          const timeline = document.querySelector('#group-room-timeline');
          const row = document.querySelector('.group-presence-row');
          return {
            stripHeight: strip.getBoundingClientRect().height,
            stripClient: strip.clientWidth,
            listScroll: list.scrollWidth,
            visible: Math.floor((strip.clientWidth + 6) / 110),
            rowWidth: row.getBoundingClientRect().width,
            timelineWidth: timeline.getBoundingClientRect().width,
            overflow: document.documentElement.scrollWidth - window.innerWidth,
          };
        }"""
    )
    assert metrics["stripHeight"] <= 60, metrics
    assert metrics["visible"] >= 3, metrics
    assert metrics["listScroll"] > metrics["stripClient"], metrics
    assert metrics["rowWidth"] >= 100, metrics
    assert metrics["timelineWidth"] > 300, metrics
    assert metrics["overflow"] <= 1, metrics

    scroll_before = await page.eval_on_selector("#group-room-timeline", "e => e.scrollTop")
    await _push(group_server, room_id, "member_status", {
        "status_seq": 1,
        "statuses": [{
            "persona_id": personas["甲"],
            "phase": "typing",
            "tools": [],
            "tool_count": 0,
        }],
    })
    await page.wait_for_selector(".group-presence-row.phase-typing")
    assert await page.eval_on_selector("#group-room-timeline", "e => e.scrollTop") == scroll_before
    assert await page.text_content(
        ".group-presence-row.phase-typing .group-presence-status"
    ) == "正在输入"

    # 第 5 名成员变为忙：横向条自动滚入，但不纵向滚动时间线。
    await _push(group_server, room_id, "member_status", {
        "status_seq": 2,
        "statuses": [{
            "persona_id": personas["戊"],
            "phase": "thinking",
            "tools": [],
            "tool_count": 0,
        }],
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-presence').scrollLeft > 0",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert await page.eval_on_selector("#group-room-timeline", "e => e.scrollTop") == scroll_before

    # presence 重绘（时间线事件触发）必须保留横向滚动位置。
    # 给 list.textContent 的 setter 注入一次强制布局：Chromium 对「同步清空后立即重建」
    # 本来就会保留 scrollLeft，不强制布局的话恢复逻辑删掉也会假绿。
    await page.evaluate(
        """() => {
          const list = document.querySelector('#group-presence-list');
          const scroller = document.querySelector('#group-room-presence');
          const desc = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
          Object.defineProperty(list, 'textContent', {
            configurable: true,
            get() { return desc.get.call(this); },
            set(value) {
              desc.set.call(this, value);
              void scroller.scrollWidth;   // 清空后强制布局，scrollLeft 归 0
            },
          });
          scroller.scrollLeft = 40;
        }"""
    )
    await _push(group_server, room_id, "member_post", {
        "persona_id": personas["戊"],
        "speaker": personas["戊"],
        "text": "完成",
        "seq": 999,
        "status_seq": 3,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-timeline').textContent.includes('完成')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert await page.eval_on_selector(
        "#group-room-presence", "e => e.scrollLeft"
    ) == 40

    # reduced-motion 下侧栏过渡关闭，presence 仍可用。
    await page.emulate_media(reduced_motion="reduce")
    duration = await page.eval_on_selector(
        "#group-sidebar", "e => getComputedStyle(e).transitionDuration"
    )
    assert duration == "0s", duration
    await page.wait_for_selector(".group-presence-row")


@pytest.mark.asyncio
async def test_group_status_late_limit_refetch_and_op_clear(page, group_server):
    await page.set_viewport_size({"width": 1200, "height": 800})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    personas, room_id = await _create_room(page, group_server["url"], ["甲", "乙"])
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.click("#group-room-list .group-item-name")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '已连接'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_function(
        "() => { const row = document.querySelector('.group-presence-row');"
        " return row && !row.classList.contains('stale'); }",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # 迟到的 limit 终态（seq 更旧）不改状态，但仍必须重拉时间线。
    app = group_server["app"]
    ws_path = app.state.session_manager.primary_workspace
    app.state.team_service.team_for(ws_path).orchestrator.log_for(room_id).append_system(
        "LIMIT-MARKER"
    )
    await _push(group_server, room_id, "member_status", {
        "status_seq": 5,
        "statuses": [{
            "persona_id": personas["甲"],
            "phase": "thinking",
            "tools": [],
            "tool_count": 0,
        }],
    })
    await page.wait_for_selector(".group-presence-row.phase-thinking")
    await _push(group_server, room_id, "round_ended", {
        "termination": "limit", "status_seq": 1, "limit": 4,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-timeline').textContent.includes('LIMIT-MARKER')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert await page.locator(".group-presence-row.phase-thinking").count() == 1

    # 发送失败（op）提示在下一次成功发送后清除。
    await page.evaluate(
        "() => { const s = window.AsterwyndGroup._state;"
        " if (s.ws) { s.ws.onclose = null; s.ws.close(); s.ws = null; } }"
    )
    await page.evaluate(
        """() => {
          const original = window.fetch;
          window.__origFetch = original;
          window.fetch = (url, opts) => {
            if (String(url).includes('/messages')) {
              return Promise.reject(new Error('boom'));
            }
            return original(url, opts);
          };
        }"""
    )
    await page.fill("#group-room-input", "失败测试")
    await page.click("#group-room-send")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent.includes('发送失败')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.evaluate("() => { window.fetch = window.__origFetch; }")
    await page.fill("#group-room-input", "重试成功")
    await page.click("#group-room-send")
    await page.wait_for_function(
        "() => !document.querySelector('#group-room-status').textContent.includes('发送失败')",
        timeout=BROWSER_TIMEOUT_MS,
    )


@pytest.mark.asyncio
async def test_group_status_disconnect_marks_stale(page, group_server):
    await page.set_viewport_size({"width": 1200, "height": 800})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    personas, room_id = await _create_room(page, group_server["url"], ["甲"])
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.click("#group-room-list .group-item-name")
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '已连接'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.evaluate("() => window.AsterwyndGroup._state.ws.close()")
    await page.wait_for_selector(".group-presence-row.stale", timeout=BROWSER_TIMEOUT_MS)

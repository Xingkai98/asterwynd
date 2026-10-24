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


# ---------------------------------------------------------------- 讨论链
# change group-unlimited-discussion（design Decision 7 / web-ui spec delta）。
# 后端 discussion_* 事件由本 change 的 agent/web 层产生；这里用房间总线模拟真实事件，
# 覆盖前端对事件契约、链身份守卫、停止控件与 390px 头部布局的消费。


_UNLIMITED_LIMITS = {"max_rounds": 200, "max_turns": 600, "max_seconds": 6000}


def _discussion_started(chain_id, members):
    return {
        "chain_id": chain_id,
        "discussion_mode": "unlimited",
        "members": list(members),
        "round_index": 1,
        "limits": dict(_UNLIMITED_LIMITS),
    }


async def _open_room(page, name):
    """按房间名打开（房间 id 是随机串，列表顺序不保证与创建顺序一致）。"""
    await page.wait_for_selector("#group-room-list .group-item-name")
    await page.locator("#group-room-list .group-item-name", has_text=name).click()
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
async def test_group_unlimited_discussion_events_and_stop_button(page, group_server):
    await page.set_viewport_size({"width": 1200, "height": 800})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    personas, room_id = await _create_room(page, group_server["url"], ["甲", "乙"])
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await _open_room(page, "状态房间")
    chain_id = f"{room_id}:1"

    # single 房：没有讨论链，停止控件不显示。
    assert await page.locator("#group-room-stop").is_hidden()

    # discussion_started：头部显示「讨论中（第 1 轮）」，停止控件可见并可发 WS 消息。
    # 拦截 ws.send 记录前端发包（服务端 stop 处理由 web/server 测试覆盖，避免跨层耦合）。
    await page.evaluate(
        """() => {
          window.__wsSends = [];
          const state = window.AsterwyndGroup._state;
          if (state.ws) state.ws.send = (payload) => { window.__wsSends.push(payload); };
        }"""
    )
    await _push(group_server, room_id, "discussion_started",
                _discussion_started(chain_id, personas.values()))
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论中（第 1 轮）'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_selector("#group-room-stop", state="visible")
    assert await page.text_content("#group-room-stop") == "停止讨论"

    # chain_continues=true：显示下一轮，绝不显示「本轮结束」。
    await _push(group_server, room_id, "round_ended", {
        "termination": "completed", "status_seq": 2, "limit": 10,
        "chain_id": chain_id, "round_index": 1, "chain_continues": True,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论中（第 2 轮）'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert "本轮结束" not in await page.text_content("#group-room-status")

    # system_entry 实时追加时间线，并按 seq 去重（重复事件不产生第二条）。
    await _push(group_server, room_id, "system_entry", {
        "chain_id": chain_id, "seq": 9001, "text": "讨论继续（第 2 轮）",
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-timeline').textContent"
        ".includes('讨论继续（第 2 轮）')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await _push(group_server, room_id, "system_entry", {
        "chain_id": chain_id, "seq": 9001, "text": "讨论继续（第 2 轮）",
    })
    await page.wait_for_timeout(300)
    assert await page.eval_on_selector_all(
        "#group-room-timeline .group-msg.system",
        "els => els.filter(e => e.textContent.includes('讨论继续（第 2 轮）')).length",
    ) == 1

    # 停止按钮：点击发 WS stop_discussion，控件置灰并显示「正在停止…」。
    await page.click("#group-room-stop")
    await page.wait_for_function(
        "() => { const b = document.querySelector('#group-room-stop');"
        " return b.disabled && b.textContent === '正在停止…'; }",
        timeout=BROWSER_TIMEOUT_MS,
    )
    sends = await page.evaluate("() => window.__wsSends.map(s => JSON.parse(s))")
    assert {"type": "stop_discussion"} in sends

    # 迟到的旧链终态：chain_id 不一致 → 不得覆盖当前链状态（仍「讨论中（第 2 轮）」）。
    await _push(group_server, room_id, "discussion_ended", {
        "chain_id": f"{room_id}:0", "reason": "converged", "rounds": 1,
        "rounds_started": 1, "turns": 2, "elapsed_seconds": 3, "status_seq": 2,
    })
    await page.wait_for_timeout(300)
    assert await page.text_content("#group-room-status") == "讨论中（第 2 轮）"
    assert await page.locator("#group-room-stop").is_visible()

    # 停止出口的 round_ended(stopped)：文案「讨论已停止」，不得出现「本轮结束」。
    await _push(group_server, room_id, "round_ended", {
        "termination": "stopped", "status_seq": 2, "limit": 10,
        "chain_id": chain_id, "round_index": 2, "chain_continues": False,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论已停止'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert "本轮结束" not in await page.text_content("#group-room-status")

    # 当前链 discussion_ended(stopped)：文案保持「讨论已停止」，控件恢复（链结束则隐藏）。
    await _push(group_server, room_id, "discussion_ended", {
        "chain_id": chain_id, "reason": "stopped", "rounds": 1,
        "rounds_started": 2, "turns": 2, "elapsed_seconds": 3, "status_seq": 2,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论已停止'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert await page.locator("#group-room-stop").is_hidden()
    assert await page.text_content("#group-room-stop") == "停止讨论"
    assert not await page.eval_on_selector("#group-room-stop", "e => e.disabled")

    # WS 未连通 → 停止控件降级 REST；端点缺失（当前仓库）或无活动链（stopping=false）
    # 都必须恢复控件，不能永久置灰。
    await _push(group_server, room_id, "discussion_started",
                _discussion_started(f"{room_id}:2", personas.values()))
    await page.wait_for_selector("#group-room-stop", state="visible")
    await page.evaluate("() => { window.AsterwyndGroup._state.ws = null; }")
    await page.click("#group-room-stop")
    await page.wait_for_function(
        "() => { const b = document.querySelector('#group-room-stop');"
        " return !b.disabled && b.textContent === '停止讨论'; }",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # 刷新/重连恢复：room_state 的 discussion_round / discussion_reason 恢复状态文案。
    room_payload = await page.evaluate(
        "() => ({...window.AsterwyndGroup._state.activeRoom, discussion_mode: 'unlimited'})"
    )
    members = await page.evaluate("() => window.AsterwyndGroup._state.members")
    await _push(group_server, room_id, "room_state", {
        "room": room_payload, "members": members, "timeline": [],
        "round_active": True, "discussion_round": 2, "discussion_reason": None,
        "member_statuses": [], "status_seq": 0,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论中（第 2 轮）'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.wait_for_selector("#group-room-stop", state="visible")

    await _push(group_server, room_id, "room_state", {
        "room": room_payload, "members": members, "timeline": [],
        "round_active": False, "discussion_round": 0, "discussion_reason": "converged",
        "member_statuses": [], "status_seq": 0,
    })
    await page.wait_for_function(
        "() => document.querySelector('#group-room-status').textContent === '讨论已收敛'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert await page.locator("#group-room-stop").is_hidden()

    # single 房不恢复讨论文案：discussion_reason 有值也不显示讨论状态。
    await _push(group_server, room_id, "room_state", {
        "room": {**room_payload, "discussion_mode": "single"},
        "members": members, "timeline": [],
        "round_active": False, "discussion_round": 0,
        "discussion_reason": "stopped", "member_statuses": [], "status_seq": 0,
    })
    await page.wait_for_timeout(300)
    assert "讨论已停止" not in await page.text_content("#group-room-status")


@pytest.mark.asyncio
async def test_group_discussion_settings_dialog_and_mobile_header(page, group_server):
    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(group_server["url"])
    await page.wait_for_function(
        "() => window.AsterwyndGroupStatus !== undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click("#group-tab")
    personas, _admin_room_id = await _create_room(page, group_server["url"], ["甲", "乙"])
    everyone = await _api(page, group_server["url"], "POST", "/api/team/rooms", {
        "name": "无限讨论房",
        "members": list(personas.values()),
        "admin": personas["甲"],
        "reply_mode": "everyone",
    })
    everyone_room_id = everyone["room"]["id"]
    await page.evaluate("() => window.AsterwyndGroup.render()")
    await page.wait_for_function(
        "() => document.querySelectorAll('#group-room-list .group-item').length === 2",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # admin 房（默认）设置：unlimited 初始 disabled；同一对话框内把「应答模式」
    # 切到 everyone 后必须立即可选（动态联动，不要求先保存再重开），切回 admin 重新置灰。
    await page.click("#group-empty-drawer")
    await page.wait_for_selector("#group-sidebar.open")
    await _open_room(page, "状态房间")
    await page.click("#group-room-edit")
    await page.wait_for_selector("#group-field-discussion_mode", state="visible")
    assert await page.eval_on_selector(
        "#group-field-discussion_mode option[value='unlimited']", "e => e.disabled",
    ) is True
    assert await page.eval_on_selector(
        "#group-field-discussion_mode option[value='single']", "e => e.disabled",
    ) is False
    assert "everyone" in await page.text_content(".group-field-hint")
    await page.select_option("#group-field-reply_mode", "everyone")
    await page.wait_for_function(
        "() => document.querySelector(\"#group-field-discussion_mode option[value='unlimited']\").disabled === false",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.select_option("#group-field-discussion_mode", "unlimited")
    await page.select_option("#group-field-reply_mode", "admin")
    await page.wait_for_function(
        "() => document.querySelector(\"#group-field-discussion_mode option[value='unlimited']\").disabled === true"
        " && document.querySelector('#group-field-discussion_mode').value === 'single'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    dialog_box = await page.eval_on_selector(
        "#group-dialog",
        "e => { const r = e.getBoundingClientRect();"
        " return {left: r.left, right: r.right, width: r.width}; }",
    )
    assert dialog_box["right"] <= 390 + 1, dialog_box
    assert dialog_box["left"] >= -1, dialog_box
    await page.click(".group-dialog-actions button[type='button']")
    await page.wait_for_selector("#group-dialog", state="hidden")

    # everyone 房：unlimited 可选；390px 头部不横向溢出（停止控件收进次要动作区）。
    await page.click("#group-drawer-toggle")
    await page.wait_for_selector("#group-sidebar.open")
    await _open_room(page, "无限讨论房")
    await _push(group_server, everyone_room_id, "discussion_started",
                _discussion_started(f"{everyone_room_id}:1", personas.values()))
    await page.wait_for_selector("#group-room-stop", state="visible")
    metrics = await page.evaluate(
        """() => {
          const head = document.querySelector('.group-room-head').getBoundingClientRect();
          const actions = document.querySelector('.group-room-actions').getBoundingClientRect();
          return {
            overflow: document.documentElement.scrollWidth - window.innerWidth,
            headRight: head.right,
            actionsRight: actions.right,
            viewport: window.innerWidth,
            stopVisible: !document.querySelector('#group-room-stop').hidden,
          };
        }"""
    )
    assert metrics["stopVisible"] is True, metrics
    assert metrics["overflow"] <= 1, metrics
    assert metrics["headRight"] <= metrics["viewport"] + 1, metrics
    assert metrics["actionsRight"] <= metrics["viewport"] + 1, metrics

    await page.click("#group-room-edit")
    await page.wait_for_selector("#group-field-discussion_mode", state="visible")
    assert await page.eval_on_selector(
        "#group-field-discussion_mode option[value='unlimited']", "e => e.disabled",
    ) is False
    # 服务端结构化错误（400）必须在对话框内如实展示，不静默丢弃。
    await page.evaluate(
        """() => {
          window.__origFetch = window.fetch;
          window.fetch = (url, opts) => {
            if (String(url).includes('/api/team/rooms/')
                && opts && opts.method === 'PATCH') {
              return Promise.resolve(new Response(
                JSON.stringify({error: 'discussion_mode_requires_everyone'}),
                {status: 400, headers: {'Content-Type': 'application/json'}},
              ));
            }
            return window.__origFetch(url, opts);
          };
        }"""
    )
    await page.select_option("#group-field-discussion_mode", "unlimited")
    await page.click(".group-dialog-actions button[type='submit']")
    await page.wait_for_function(
        "() => document.querySelector('.group-dialog-error')"
        ".textContent.includes('everyone')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.evaluate("() => { window.fetch = window.__origFetch; }")
    await page.click(".group-dialog-actions button[type='button']")
    await page.wait_for_selector("#group-dialog", state="hidden")

    # 新建房间对话框：默认 admin ⇒ unlimited disabled；同一对话框切到 everyone 后
    # 立即可选，选中 unlimited 一步提交即可成功创建 everyone+unlimited 房间。
    await page.click("#group-drawer-toggle")
    await page.wait_for_selector("#group-sidebar.open")
    await page.click("#group-room-add")
    await page.wait_for_selector("#group-field-discussion_mode", state="visible")
    assert await page.eval_on_selector(
        "#group-field-discussion_mode option[value='unlimited']", "e => e.disabled",
    ) is True
    assert "everyone" in await page.text_content(".group-field-hint")
    await page.fill("#group-field-name", "一步无限房")
    await page.select_option("#group-field-reply_mode", "everyone")
    await page.select_option("#group-field-discussion_mode", "unlimited")
    await page.click(".group-dialog-actions button[type='submit']")
    await page.wait_for_selector("#group-dialog", state="hidden")
    await page.wait_for_function(
        "() => { const r = (window.AsterwyndGroup._state.rooms || []).find(x => x.name === '一步无限房');"
        " return Boolean(r && r.reply_mode === 'everyone' && r.discussion_mode === 'unlimited'); }",
        timeout=BROWSER_TIMEOUT_MS,
    )

# tests/web_tests/test_multi_session_browser.py
"""Playwright browser tests for the multi-session hub (issue #117).

Covers: hub session list + open tab, multi-tab isolation, refresh restore,
delete closes tab. Uses a tmp_path workspace with a pre-seeded session store.
"""
import socket
import threading
import time
import urllib.request
from datetime import datetime

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

# 该文件所有浏览器等待的显式上限。Playwright 默认 30s 在满负载 CI 上会与真实
# 「元素永不出现」的 bug 混在一起、且超时信息里只有选择器 —— issue #191 记录的
# 「偶发失败无输出」正是这种形态。统一收到一个可读常量。
BROWSER_TIMEOUT_MS = 15000


async def _install_fake_clock(page):
    """装**已暂停**的假时钟，把「100ms 宽限窗」交给测试显式推进，去掉墙钟依赖。

    必须**在导航之前**调用（Playwright 只接管安装之后创建的定时器）。

    只调 `clock.install()` 是**不够**的：实测装完后墙钟照常前进、`setTimeout(…, 100)`
    在真实 100ms 后仍会自行触发 —— 那样测试依旧活在墙钟里，只是多了一个可以加速
    的通道。真正让「宽限窗到点没」变成确定输入的是 `pause_at`：暂停后页面定时器
    **只能**由 `fast_forward(ms)` 推进（实测暂停后真实 elapsed 0.6s 不触发、
    `fast_forward(150)` 才触发）。

    这正是 issue #191 的教训：断言跑在定时器之前时，坏实现也能「碰巧通过」。
    暂停时钟把这个「之前/之后」变成测试的显式选择，而不是机器负载的函数。
    """
    await page.clock.install()
    # pause_at 要求目标时刻不在过去（Playwright 内部是 fast-forward-to），用一个
    # 足够远的未来常量，避免依赖 `datetime.now()` 而引入新的墙钟输入。
    await page.clock.pause_at(datetime(2099, 1, 1, 12, 0, 0))


async def _advance_past_grace_window(page):
    """把虚拟时间推过 blur 收起动作的 100ms 宽限窗，让所有挂起的收起动作确定性地
    触发（或确定性地已被取消）。"""
    await page.clock.fast_forward(500)


async def _open_two_tabs_frozen(page, base_url):
    """同 `_open_two_tabs`，但先装假时钟 —— 定时器只能由测试显式推进。

    用于「挂起的收起动作是否生效」类断言：把该动作的触发时机从墙钟解放出来，
    使坏实现确定性变红、好实现确定性变绿（见 `_install_fake_clock`）。
    """
    await _install_fake_clock(page)
    return await _open_two_tabs(page, base_url)


async def _dismiss_suggestions(page, *, frozen=False):
    """让当前 active tab 的输入框失焦并等建议收起（显式收起的确定性写法）。

    ``frozen=True`` 时先推进虚拟时间，让挂起的收起动作确定性地触发。
    """
    await page.evaluate(
        "document.querySelector('.tab-pane.active .user-input').blur()"
    )
    if frozen:
        # 假时钟已暂停：推进虚拟时间会**同步**触发挂起的收起动作，下面那句
        # wait_for_function 于是立刻满足（它是复合检查，不是真的在等）。
        # 保持它是因为 frozen=False 的调用点仍需要等真实墙钟。
        await _advance_past_grace_window(page)
    try:
        await page.wait_for_function(
            "document.querySelector('.tab-pane.active .slash-suggestions').hidden",
            timeout=BROWSER_TIMEOUT_MS,
        )
    except Exception as exc:  # noqa: BLE001 - 转成可读失败信息
        raise AssertionError(
            "输入框失焦后建议列表未收起；可见性="
            f"{await _suggestions_visible(page)!r}"
        ) from exc


async def _open_two_tabs(page, base_url):
    """打开预置会话 tab1 + 新建 tab2，返回 tab2 的 tab-id。

    tab-id 会从临时 `new-N` 被 rekey 成真实 session id（chat.js 的 handleTabEvent
    在 WS 握手事件到达时改名）。若提前缓存 data-tab-id 会拿到过期值而随机 flake
    —— 这与 issue #191 想根治的 flake 是同类不同源，必须显式等待 rekey 完成。
    """
    await page.goto(base_url)
    await page.wait_for_selector("#hub-view.active", timeout=BROWSER_TIMEOUT_MS)
    await page.click(".hub-session-open")
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.click("#hub-tab")
    await page.wait_for_selector("#hub-view.active", timeout=BROWSER_TIMEOUT_MS)
    await page.click("#hub-new-btn")
    await page.wait_for_selector(INPUT_SELECTOR, timeout=BROWSER_TIMEOUT_MS)
    await page.wait_for_function(
        "document.querySelectorAll('.session-tab').length === 2", timeout=BROWSER_TIMEOUT_MS
    )
    # 等新建 tab 完成 rekey（不再是 new-N），否则后续按 data-tab-id 定位会落空
    await page.wait_for_function(
        "[...document.querySelectorAll('.session-tab')]"
        ".every(t => !t.dataset.tabId.startsWith('new-'))",
        timeout=BROWSER_TIMEOUT_MS,
    )
    return await page.evaluate(
        "[...document.querySelectorAll('.session-tab')]"
        ".map(t => t.dataset.tabId).find(id => id !== 'aaaa11111111')"
    )


async def _suggestions_visible(page, pane_selector=None):
    """读某个 pane 的 slash 建议是否可见（默认当前 active pane）。"""
    pane = pane_selector or ".tab-pane.active"
    return await page.evaluate(
        "(pane) => { const el = document.querySelector(pane + ' .slash-suggestions');"
        " return el ? !el.hidden : null; }",
        pane,
    )


async def _show_slash_suggestions(page, text="/s"):
    """在当前 active tab 输入并等建议可见（失败信息带上下文）。"""
    await page.fill(INPUT_SELECTOR, text)
    try:
        await page.wait_for_selector(
            ".tab-pane.active .slash-suggestions:not([hidden])",
            timeout=BROWSER_TIMEOUT_MS,
        )
    except Exception as exc:  # noqa: BLE001 - 转成可读失败信息
        # f-string 里不能出现反斜杠（Python < 3.12 的语法限制，CI 跑 3.11），
        # 所以先求值再插值。
        active_tab = await page.evaluate(
            "document.querySelector('.tab-pane.active').dataset.tabId"
        )
        raise AssertionError(
            f"在输入框填入 {text!r} 后，当前标签页的 slash 建议未在 "
            f"{BROWSER_TIMEOUT_MS}ms 内出现；建议列表状态="
            f"{await _suggestions_visible(page)!r}，当前 tab={active_tab!r}"
        ) from exc


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
    """两个 tab 的 slash 匹配状态互不串扰：tab2 输 /s 出建议，切到 tab1 无建议，切回仍在。

    issue #191：本测试原先的「切走再切回」依赖两次 click 的墙钟间隔 —— 间隔短于
    chat.js blur 处理器的 100ms 宽限窗时，挂起的收起动作会在「切回后仍是 active」
    时触发，把 tab2 自己的建议收掉（探针实测：0ms 间隔失败、150ms 通过）。
    现在改为**不依赖间隔**：收敛由该 tab 的输入内容决定，interval 取任意值结果一致。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)

    # tab2（active）输 /s：建议只出现在 tab2
    await _show_slash_suggestions(page)

    # 切到 tab1：无建议（tab1 自己的 slashSuggestionsEl 是独立的，hidden）
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    assert not await _suggestions_visible(page, '.tab-pane[data-tab-id="aaaa11111111"]'), \
        "切到 tab1 后 tab1 自己的建议不应可见（它没输入过内容）"

    # 切回 tab2，然后**把虚拟时间推过 100ms 宽限窗**再断言。
    #
    # 断言必须落在宽限窗之后：切走时 tab2 的输入框失焦挂起了一个收起动作，
    # 「谁赢」取决于定时器与切回操作的相对顺序。假时钟让这个顺序由测试显式决定
    # （推进 = 定时器确定性地触发），而不是由两次 click 的墙钟耗时决定。
    # 若断言提前到定时器之前，无归属的实现（ORIG）也能「碰巧读到可见」而通过 ——
    # 那正是本轮审阅打回的 Issue 1。
    await page.click(f'.session-tab[data-tab-id="{tab2}"]')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await _advance_past_grace_window(page)
    assert await _suggestions_visible(page), (
        "切回 tab2 并越过 100ms 宽限窗后，其 slash 建议应仍可见。"
        "若失败，说明挂起的收起动作收掉了本 tab 自己的建议"
        "（issue #191 的根因：收起动作没有归属到触发它的 tab）。"
    )


@pytest.mark.asyncio
async def test_cross_tab_blur_does_not_hide_active_suggestions(page, seeded_web_server):
    """非活跃 tab 的失焦不得收起活跃 tab 的建议（t_b 判别测试）。

    复现 issue #191 的实现层根因：blur 收起动作读「触发时刻的 active tab」，
    与「哪个 tab 失焦」解耦，于是 tab1 的失焦可以收掉 tab2 的列表。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page)

    # 切到 tab1，在其输入框里输入（让 tab1 拿到焦点、产生属于它的失焦源）
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.fill(INPUT_SELECTOR, "x")

    # 切回 tab2 并聚焦其输入框；此刻 tab1 的输入框失焦 → 挂起 tab1 的收起定时器
    await page.click(f'.session-tab[data-tab-id="{tab2}"]')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.click(INPUT_SELECTOR)
    # 推进虚拟时间，让 tab1 的挂起定时器确定性触发（而非等墙钟）
    await _advance_past_grace_window(page)

    assert await _suggestions_visible(page), (
        "tab1 的失焦定时器触发时不应收起 tab2 的建议列表 —— "
        "失焦事件的归属标签页与建议列表的归属标签页必须一致（issue #191）。"
    )


@pytest.mark.asyncio
async def test_focus_returned_within_grace_window_keeps_suggestions(page, seeded_web_server):
    """宽限窗语义（保护 blur 守卫的 activeElement 检查）。

    用户点开空白处又把焦点移回输入框（在 100ms 宽限窗内），是「误点后马上回来继续
    输入」的真实操作。此时挂起的收起动作不应生效 —— 去掉 activeElement 守卫的实现
    会在这里把列表错误收掉。

    「失焦 → 重新聚焦」在**同一个 JS turn 内**用 DOM API 完成，间隔由浏览器决定
    （几毫秒），而不是两次 Playwright click 的墙钟间隔 —— 后者的裕度只有几十毫秒
    （空载约 40–49ms、满负载 51–74ms，而守卫边界是 100ms），会变成又一个时序 flake。
    """
    await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page)

    await page.evaluate(
        "() => { const el = document.querySelector('.tab-pane.active .user-input');"
        " el.blur(); el.focus(); }"
    )
    await _advance_past_grace_window(page)  # 让挂起的收起动作确实触发

    assert await _suggestions_visible(page), (
        "失焦后焦点又回到本 tab 输入框时，建议列表应保持可见；"
        "若被收起，说明 blur 守卫缺少「焦点已回到本 tab 输入框」这一检查。"
    )


@pytest.mark.asyncio
async def test_reopened_tab_reevaluates_suggestions_from_input(page, seeded_web_server):
    """收敛语义（t_c 判别测试）：收起后切走再切回，按输入内容重新判定为可见。

    这是「归属化但无收敛」与「有收敛」实现之间的唯一区分器之一：
    仅做 blur 归属化的实现会保持收起，本测试必须杀掉它。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page)

    # 显式收起（模拟用户点页面空白处）
    await _dismiss_suggestions(page, frozen=True)
    assert not await _suggestions_visible(page), "前置条件：建议应已被显式收起"

    # 切走再切回：输入框内容仍是 /s，收敛后应重新可见
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.click(f'.session-tab[data-tab-id="{tab2}"]')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await _advance_past_grace_window(page)

    assert await _suggestions_visible(page), (
        "切回 tab2 后建议应按其输入内容（/s）重新判定为可见；"
        "若仍收起，说明 switchTab 没有做收敛（只有 blur 归属化）。"
    )


@pytest.mark.asyncio
async def test_escape_then_enter_still_sends_message(page, seeded_web_server):
    """t_e 判别测试：Escape 收起建议后，Enter 仍须发送消息（不得被吞）。

    keydown 处理器第一行是 switchTab(tab.id)；若收敛无条件执行，会把列表复活，
    使同一个 keydown 落入 applySlashSuggestion 分支而非 sendMessage —— 消息永远发不出去。
    """
    await _open_two_tabs(page, seeded_web_server)
    await _show_slash_suggestions(page, "/status")

    await page.press(INPUT_SELECTOR, "Escape")
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active .slash-suggestions').hidden",
        timeout=BROWSER_TIMEOUT_MS,
    )
    before = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    await page.press(INPUT_SELECTOR, "Enter")
    await page.wait_for_timeout(800)
    after = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    remaining = await page.evaluate(
        "document.querySelector('.tab-pane.active .user-input').value"
    )

    assert after == before + 1, (
        f"Escape 收起建议后按 Enter 应发送消息（用户消息数 {before} → {before + 1}）；"
        f"实际 {before} → {after}，输入框残留 {remaining!r}。"
        "若消息未发出，说明 switchTab 的收敛在 keydown 路径上把列表复活、"
        "Enter 被误判为「应用建议项」而吞掉。"
    )


@pytest.mark.asyncio
async def test_dismissed_suggestions_not_reopened_by_keypress(page, seeded_web_server):
    """Escape 收起后，**同一标签页内的按键**不得让列表自行重新展开。

    收敛只对「真的从别的 tab 切过来」生效。若收敛无条件执行，keydown 处理器开头的
    `switchTab(tab.id)`（本来就是当前 tab）会顺手把列表重新展开 —— 用户明明按了
    Escape 表达「不想从列表里选」，下一次按键列表又冒出来。
    """
    await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page, "/status")

    await page.press(INPUT_SELECTOR, "Escape")
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active .slash-suggestions').hidden",
        timeout=BROWSER_TIMEOUT_MS,
    )

    # 按一个会走 keydown 处理器、但不会改变输入内容的键
    await page.press(INPUT_SELECTOR, "ArrowDown")
    await _advance_past_grace_window(page)

    assert not await _suggestions_visible(page), (
        "Escape 收起后，同一标签页内按键不应让建议列表自行重新展开。"
        "若列表又可见，说明收敛被无条件执行（keydown 处理器开头的 switchTab "
        "把「已是当前 tab」的调用也当成了切换）。"
    )


@pytest.mark.asyncio
async def test_escape_switch_back_then_enter_still_sends_message(page, seeded_web_server):
    """Escape 收起 → 切走 → 切回（列表按收敛重新出现）→ Enter 仍须发送消息。

    这条路径与上一条**不同**：上一条是同 tab 内 Escape 后直接 Enter（收敛不介入），
    本条是「收敛把用户已收起的列表重新展开」之后再 Enter。列表重新出现是按输入内容
    收敛的**预期**结果（用户已拍板「弹回来」），但用户此前的 Escape 表达的是
    「我不想从列表里选」；此时按 Enter 的意图是发送，不能因为列表恰好又可见
    就把这次发送吞掉（`/status` 的 insert_text 就是 '/status'，应用它等于什么都没做）。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page, "/status")

    # Escape 收起 → 切到 tab1 → 切回 tab2（收敛按输入内容重新展开）
    await page.press(INPUT_SELECTOR, "Escape")
    await page.wait_for_function(
        "document.querySelector('.tab-pane.active .slash-suggestions').hidden",
        timeout=BROWSER_TIMEOUT_MS,
    )
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.click(f'.session-tab[data-tab-id="{tab2}"]')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await _advance_past_grace_window(page)
    assert await _suggestions_visible(page), "前置条件：切回后列表应按输入内容重新可见"

    before = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    await page.press(INPUT_SELECTOR, "Enter")
    await page.wait_for_timeout(800)
    after = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    remaining = await page.evaluate(
        "document.querySelector('.tab-pane.active .user-input').value"
    )

    assert after == before + 1, (
        f"切回后列表虽按输入内容重新可见，但按 Enter 的意图是发送消息"
        f"（用户消息数 {before} → {before + 1}）；实际 {before} → {after}，"
        f"输入框残留 {remaining!r}。"
        "若未发出，说明「应用一条等于当前输入的建议」这个空操作吞掉了发送。"
    )


@pytest.mark.asyncio
async def test_hint_command_enter_completes_then_sends(page, seeded_web_server):
    """带参数提示的命令：列表可见时 Enter 先补全、再按一次才发送（D1c 的有意边界）。

    `/mode` 的 insert_text 是 `/mode `（补一个空格），应用它是**真实补全**而非空操作，
    所以沿用自动补全的既有语义（Enter = 接受补全）。这与 `/status` 的「空操作 → 直接
    发送」形成对照，两种行为都是契约的一部分，各自有测试钉住。
    """
    await _open_two_tabs_frozen(page, seeded_web_server)

    # 敲出带提示命令的前缀，列表首项即为该命令
    await page.fill(INPUT_SELECTOR, "/mode")
    await page.wait_for_selector(".tab-pane.active .slash-suggestions:not([hidden])",
                                 timeout=BROWSER_TIMEOUT_MS)
    before = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )

    await page.press(INPUT_SELECTOR, "Enter")
    await page.wait_for_timeout(600)
    after_first = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    value = await page.evaluate(
        "document.querySelector('.tab-pane.active .user-input').value"
    )

    assert after_first == before, (
        "列表可见时按 Enter 应接受带参数提示的补全（不发送）；"
        f"实际用户消息数 {before} → {after_first}，输入框 {value!r}。"
    )
    assert value.strip() == "/mode", f"补全后输入框应为 /mode（可带尾随空格）；实际 {value!r}"

    await page.press(INPUT_SELECTOR, "Enter")
    await page.wait_for_timeout(800)
    after_second = await page.evaluate(
        "document.querySelectorAll('.tab-pane.active .message.user').length"
    )
    assert after_second == before + 1, (
        f"补全后再按一次 Enter 应发送消息（{before} → {before + 1}）；实际 {after_second}。"
    )


@pytest.mark.asyncio
async def test_slow_click_then_return_keeps_suggestions(page, seeded_web_server):
    """t_d 判别测试：慢 click（按住 >100ms 再释放）切走、再切回，建议仍可见。

    仅做 blur 归属化（无收敛）的实现在此失败：定时器在 switchTab 之前触发，
    此刻 active 仍是原 tab，归属守卫放行 → 列表被收，切回不恢复。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)
    await _show_slash_suggestions(page)

    # 在 tab1 的 tab 按钮上按下并**保持按住**，其间把虚拟时间推过宽限窗：
    # 此刻 click 还没发生、active 仍是 tab2，于是挂起的收起动作既通过 active 归属
    # 守卫、也通过聚焦守卫 → 收掉 tab2 的列表。这就是「仅归属化」实现的缺陷场景。
    tab1_btn = page.locator('.session-tab[data-tab-id="aaaa11111111"]')
    box = await tab1_btn.bounding_box()
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await page.mouse.down()
    await _advance_past_grace_window(page)  # 定时器在切换之前触发
    await page.mouse.up()
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)

    # 切回 tab2：收敛后应可见（仅归属化的实现会保持收起）
    await page.click(f'.session-tab[data-tab-id="{tab2}"]')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await _advance_past_grace_window(page)

    assert await _suggestions_visible(page), (
        "按住标签页按钮越过宽限窗再切走、然后切回 tab2 时，其建议应仍可见。"
        "若失败，说明实现只做了 blur 归属化、缺少 switchTab 收敛 —— "
        "收起动作在切换之前触发时归属守卫会放行并收掉列表。"
    )


@pytest.mark.asyncio
async def test_closing_active_tab_converges_remaining_tab(page, seeded_web_server):
    """关闭当前活跃 tab 后，被切到的 tab 应重新收敛其建议可见性。

    关闭活跃 tab 会经 `closeTab` → `switchTab(next)`（`chat.js` 的 closeTab）走到
    收敛路径。这个构造是可证伪的关键：tab2 的建议**已被显式收起**但输入框仍是
    `/s`，切回它时「按输入内容应当可见」。无收敛的实现会把它留在收起状态。
    """
    tab2 = await _open_two_tabs_frozen(page, seeded_web_server)

    # tab2 输入 /s 后**显式收起**（输入框内容仍是 /s）
    await _show_slash_suggestions(page)
    await _dismiss_suggestions(page, frozen=True)
    assert not await _suggestions_visible(page), "前置条件：tab2 的建议应已被收起"

    # 切到 tab1 并关闭它（此刻它是活跃 tab）→ closeTab 会 switchTab 到 tab2
    await page.click('.session-tab[data-tab-id="aaaa11111111"]')
    await page.wait_for_selector('.tab-pane[data-tab-id="aaaa11111111"].active',
                                 timeout=BROWSER_TIMEOUT_MS)
    await page.click('.session-tab[data-tab-id="aaaa11111111"] .session-tab-close')
    await page.wait_for_selector(f'.tab-pane[data-tab-id="{tab2}"].active',
                                 timeout=BROWSER_TIMEOUT_MS)

    assert await _suggestions_visible(page), (
        "关闭活跃 tab 后切到的 tab2 应按其自身输入内容（/s）收敛为建议可见。"
        "若仍收起，说明切换路径没有做收敛（仅归属化的实现会停在这里）。"
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

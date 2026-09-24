"""Workflow 流程图浏览器 smoke（change ``workflow-graph-visualization``，tasks 3.1/5.1/5.2）。

Q7 的验收路径「CI 装 chromium 跑关键 smoke」：这里覆盖 node 单测覆盖不到的部分——
真实 DOM 渲染、事件分发到视图、自动打开视图、跨端断点、pinch/pan 手势。

CI 里没有浏览器时自动 skip（``p.chromium.launch`` 失败），与既有 ``test_browser.py``
同口径；CI 的 validate job 现在会 ``playwright install chromium``，所以这条会真跑。
"""
import threading
import time

import pytest

pytest.importorskip("playwright", reason="playwright not installed")

from agent.llm import LLMResponse
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app

import socket


@pytest.fixture
def fake_web_server(tmp_path):
    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    base_url = f"http://127.0.0.1:{port}"
    llm = ScriptedLLM([LLMResponse(content="fake", stop_reason="end_turn")])
    app = create_app(llm, workspace_root=tmp_path)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if server.started:
            break
        import time
        time.sleep(0.05)

    yield {"url": base_url, "app": app, "port": port}

    server.should_exit = True
    thread.join(timeout=5)


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


SNAPSHOT = {
    "workflow_id": "wf_demo",
    "spec_hash": "abc123",
    "goal": "demo workflow",
    "status": "running",
    "timestamp": 1.0,
    "nodes": [
        {"id": "a", "kind": "subagent", "status": "completed", "runs": 1,
         "summary": "done", "started_at": 0, "finished_at": 1,
         "failure_count": 3},
        {"id": "b", "kind": "subagent", "status": "started", "runs": 1,
         "summary": "", "started_at": 1, "finished_at": None,
         "failure_count": 0},
        {"id": "join", "kind": "aggregate", "status": "pending", "runs": 0,
         "summary": "", "started_at": None, "finished_at": None},
    ],
    "edges": [
        {"from": "a", "to": "join", "channel": "summary", "required": True,
         "reducer": None, "kind": "data", "status": "passed"},
        {"from": "b", "to": "join", "channel": "summary", "required": True,
         "reducer": None, "kind": "data", "status": "active"},
    ],
}


async def _push_workflow_event(page, event_type: str, data: dict) -> None:
    """在前端直接派发事件（绕过 ws），验证视图层的分发与渲染。

    第一次调用时装一个测试 tab 并 ``bindTab``——等价于 chat.js 里真实 tab 的接线
    （``graphState`` + ``onWorkflowStarted`` → ``switchToWorkflowView``）。
    """
    await page.evaluate(
        """([type, data]) => {
            const graph = window.AsterwyndWorkflow;
            if (!graph) throw new Error('workflow.js not loaded');
            if (!window.__testTab) {
                const tab = { graphState: graph.createGraphState() };
                // 等价于 chat.js 的 switchToWorkflowView：**只**让 workflow-view 可见
                // （其余 .view 全部收起，否则 canvas 会被推到视口外、手势测不到）。
                tab.onWorkflowStarted = () => {
                    document.querySelectorAll('.tab[data-tab]').forEach(
                        t => t.classList.toggle('active', t.dataset.tab === 'workflow'));
                    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
                    document.getElementById('workflow-view').classList.add('active');
                };
                window.__testTab = tab;
                graph.bindTab(tab);
            }
            graph.handleWorkflowEvent(window.__testTab, { type, data });
        }""",
        [event_type, data],
    )


async def _wait_app_ready(page) -> None:
    """等 app 自身的异步初始化落定，再派发测试事件。

    回归（与 issue #191 同类竞态）：``chat.js`` 的 ws 握手 → 建 tab → ``switchTab``
    → ``showView('chat')`` 是**异步**的，可能发生在测试派发 workflow 事件之后，
    把 workflow-view 的 active class 摘掉——表现为 ``#workflow-canvas svg``
    间歇性不可见。只等 ``window.AsterwyndWorkflow`` 就绪**不够**（那只能说明脚本
    加载完了，不说明 chat.js 的 tab 初始化跑完了）。

    就绪信号取「chat 视图出现已激活的输入框」（与 ``test_browser.py`` 既有口径一致）；
    fixture 没有 ws 时降级为短等。
    """
    try:
        await page.wait_for_selector(".tab-pane.active .user-input", timeout=5000)
    except Exception:  # noqa: BLE001 - 降级：无输入框的 fixture
        await page.wait_for_timeout(300)


async def _start_workflow(page, snapshot: dict) -> None:
    """模拟一条完整的真实事件流：``workflow_started`` → ``workflow_snapshot``。"""
    await _push_workflow_event(page, "workflow_started", {
        "workflow_id": snapshot["workflow_id"],
        "spec_hash": snapshot.get("spec_hash"),
        "goal": snapshot.get("goal", ""),
        "status": snapshot.get("status", "running"),
        "timestamp": snapshot.get("timestamp", 1.0),
    })
    await _push_workflow_event(page, "workflow_snapshot", snapshot)


@pytest.mark.asyncio
async def test_workflow_view_auto_opens_and_draws_svg(page, fake_web_server):
    """tasks 3.1/3.2：``workflow_started`` 自动打开视图并画出节点与边。"""
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")

    await _start_workflow(page, SNAPSHOT)

    assert await page.is_visible("#workflow-view")
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    node_ids = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.nodeId)")
    assert sorted(node_ids) == ["a", "b", "join"]

    statuses = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.status)")
    assert sorted(statuses) == ["completed", "pending", "started"]

    colors = await page.eval_on_selector_all(
        ".workflow-node rect", "els => els.map(e => e.getAttribute('stroke'))")
    assert "#4ade80" in colors  # completed 绿
    assert "#60a5fa" in colors  # started 蓝
    assert "#94a3b8" in colors  # pending 灰

    edge_statuses = await page.eval_on_selector_all(
        ".workflow-edge", "els => els.map(e => e.dataset.status)")
    assert sorted(edge_statuses) == ["active", "passed"]


@pytest.mark.asyncio
async def test_workflow_view_desktop_horizontal_layout(page, fake_web_server):
    """tasks 5.1：桌面（>720px）横向 DAG——层沿 x 递增。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    xs = await page.eval_on_selector_all(
        ".workflow-node",
        "els => els.map(e => parseFloat(e.getAttribute('transform').match(/translate\\(([-\\d.]+)/)[1]))",
    )
    # a/b 同层（x 相同），join 在下一层（x 更大）。
    assert xs[0] == xs[1]
    assert xs[2] > xs[0]


@pytest.mark.asyncio
async def test_workflow_view_mobile_vertical_layout(page, fake_web_server):
    """tasks 5.1：手机（≤720px）纵向 DAG——层沿 y 递增。"""
    await page.set_viewport_size({"width": 380, "height": 720})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    ys = await page.eval_on_selector_all(
        ".workflow-node",
        "els => els.map(e => parseFloat(e.getAttribute('transform').match(/translate\\([-\\d.]+, ([-\\d.]+)/)[1]))",
    )
    assert ys[0] == ys[1]
    assert ys[2] > ys[0]


@pytest.mark.asyncio
async def test_workflow_graph_pan_and_zoom(page, fake_web_server):
    """tasks 5.2：pan（单指拖动）与 pinch（双指）改 viewBox。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    before = await page.get_attribute("#workflow-canvas svg", "viewBox")

    box = await page.locator("#workflow-canvas").bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2

    # pan：单指拖动
    await page.mouse.move(cx, cy)
    await page.mouse.down()
    await page.mouse.move(cx + 60, cy + 30, steps=5)
    await page.mouse.up()
    after_pan = await page.get_attribute("#workflow-canvas svg", "viewBox")
    assert after_pan != before

    # pinch：两指距离变大 → 放大（viewBox 宽变小）
    width_of = lambda vb: float(vb.split()[2])
    w_before = width_of(after_pan)
    await page.evaluate("""() => {
        const host = document.getElementById('workflow-canvas');
        const fire = (type, id, x, y) => host.dispatchEvent(new PointerEvent(type, {
            pointerId: id, clientX: x, clientY: y, bubbles: true,
        }));
        fire('pointerdown', 1, 100, 100);
        fire('pointerdown', 2, 200, 200);
        fire('pointermove', 1, 60, 60);
        fire('pointermove', 2, 260, 260);
        fire('pointerup', 1, 60, 60);
        fire('pointerup', 2, 260, 260);
    }""")
    after_pinch = await page.get_attribute("#workflow-canvas svg", "viewBox")
    assert width_of(after_pinch) < w_before


@pytest.mark.asyncio
async def test_graph_recursion_exceeded_still_draws_graph_with_notice(page, fake_web_server):
    """**G14/D10 反转了 #190 决策 9**：超限时**仍然画图**，告警条叠在画布上方。

    原行为是命中 notice 就 ``renderMessage + return``——用户**失去整幅画面**，
    看不到哪些节点已完成、卡在哪个环。``nodes``/``edges`` 是无条件存在的，
    ``diagnostics`` 还带着 ``current_nodes``（超限那刻仍就绪的节点 = 回边死循环的
    直接答案）与 ``steps``，画出来才用得上。

    判定仍然**不按** ``nodes.length``（决策 9 的那半条不变）。
    """
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, {
        "workflow_id": "wf_big",
        "status": "graph_recursion_exceeded",
        "goal": "too big",
        "timestamp": 1.0,
        "nodes": [{"id": f"n{i}", "kind": "subagent", "status": "pending"} for i in range(12)],
        "edges": [],
        "diagnostics": {"reason": "max_nodes", "recursion_limit": 200, "message": "boom",
                        "steps": 11, "current_nodes": ["n0", "n1"]},
    })

    await page.wait_for_selector("#workflow-notice:not([hidden])")
    notice = await page.text_content("#workflow-notice")
    assert "max_nodes" in notice
    assert "n0" in notice and "n1" in notice, "告警条必须带上超限时仍就绪的节点"
    assert "11" in notice, "告警条必须带上 steps"
    # 图**仍然画出来**（这正是本 change 的修法）。
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")


@pytest.mark.asyncio
async def test_session_without_workflow_is_unaffected(page, fake_web_server):
    """tasks 6.3 兼容回归：没有 workflow 的会话前端不崩、workflow 入口保持隐藏。

    ``page`` fixture 已经把 pageerror 收集成失败，所以「不崩」在这里是硬断言。
    """
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")

    # 普通对话事件流走一遍：工作流通道的存在不得影响既有渲染。
    await page.evaluate("""() => {
        const owner = { graphState: window.AsterwyndWorkflow.createGraphState() };
        window.__t = owner;
        window.AsterwyndWorkflow.bindTab(owner);
    }""")

    assert await page.evaluate("() => document.getElementById('workflow-tab').hidden") is True
    assert await page.evaluate(
        "() => !document.getElementById('workflow-view').classList.contains('active')") is True

    # 空图状态下 canvas 显示占位而不是报错。
    await page.evaluate("() => window.AsterwyndWorkflow.renderPanel(window.__t)")
    assert "模型启动 workflow" in await page.text_content("#workflow-canvas")


@pytest.mark.asyncio
async def test_multi_workflow_tabs_switch(page, fake_web_server):
    """Q2：多图 tab——两张图各占一个 tab，点击可切换。"""
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")

    for wf_id, goal in (("wf_one", "first"), ("wf_two", "second")):
        await _push_workflow_event(page, "workflow_started", {
            "workflow_id": wf_id, "goal": goal, "status": "running", "timestamp": 1.0,
        })
        await _push_workflow_event(page, "workflow_snapshot", {
            **SNAPSHOT, "workflow_id": wf_id, "goal": goal,
        })

    await page.wait_for_selector("#workflow-tabs .graph-tab")
    # D6/Q3 = A：tab 标签是「#序号 + goal」——两张图都有 ``started_at`` 时按
    # ``started_at`` 排序编号，这里是同一时刻（都是 1.0）→ 按到达序稳定编号。
    tabs = await page.eval_on_selector_all(
        "#workflow-tabs .graph-tab .graph-tab-label", "els => els.map(e => e.textContent)")
    assert tabs == ["#1 first", "#2 second"]

    # 点第一个 tab 切过去（follow 关掉后不再被新事件抢焦点）。
    await page.click("#workflow-tabs .graph-tab:first-child")
    active = await page.eval_on_selector(
        "#workflow-tabs .graph-tab.active .graph-tab-label", "e => e.textContent")
    assert active == "#1 first"


def _big_foreach_snapshot() -> dict:
    """>= COLLAPSE_THRESHOLD 节点的图：1 个 foreach 容器 + 3 个 auto 层 + 48 叶子。"""
    nodes = [{"id": "src", "kind": "subagent", "status": "completed",
              "runs": 1, "summary": "", "started_at": 0, "finished_at": 1}]
    nodes.append({"id": "fan", "kind": "foreach", "status": "started",
                  "runs": 1, "summary": "", "started_at": 1, "finished_at": None,
                  "items": 12})
    for i in range(3):
        nodes.append({"id": f"__auto_agg__fan_{i}", "kind": "aggregate", "status": "failed",
                      "runs": 1, "summary": "", "started_at": 1, "finished_at": 2})
    for i in range(48):
        nodes.append({"id": f"leaf{i}", "kind": "subagent", "status": "completed",
                      "runs": 1, "summary": "", "started_at": 0, "finished_at": 1})
    nodes.append({"id": "root", "kind": "aggregate", "status": "started",
                  "runs": 1, "summary": "", "started_at": 1, "finished_at": None})

    def edge(src, dst, reducer=None):
        return {"from": src, "to": dst, "channel": "summary", "required": True,
                "reducer": reducer, "kind": "data", "status": "passed"}

    edges = [edge("src", "fan")]
    for i in range(3):
        edges.append(edge("fan", f"__auto_agg__fan_{i}"))
        edges.append(edge(f"__auto_agg__fan_{i}", "root", "concat"))
    for i in range(48):
        edges.append(edge(f"leaf{i}", "root", "concat"))

    return {"workflow_id": "wf_big", "spec_hash": "h", "goal": "big", "status": "running",
            "timestamp": 1.0, "nodes": nodes, "edges": edges}


@pytest.mark.asyncio
async def test_collapsed_group_expands_from_the_detail_drawer(page, fake_web_server):
    """tasks 4.1 / D5 + **Q2 = B**：折叠组的展开/收起由**详情抽屉**承担。

    点击语义拆分后，点节点 = 开详情（不再是展开）；展开 ```` 收进抽屉里给
    ``groupLeader`` 的「展开成员」动作。回归：``expandedGroups`` 只传给 layoutGraph
    而 collapseGraph 拿不到时，这个动作也是空操作，成员永远放不出来。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, _big_foreach_snapshot())
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    before = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.nodeId)")
    assert "fan" in before
    assert "__auto_agg__fan_0" not in before, "前置条件：auto 层默认应被折叠"

    # 点节点 = 开详情抽屉（**不再**展开折叠组）。
    await page.click(".workflow-node[data-node-id='fan']")
    await page.wait_for_selector("#workflow-drawer.open")
    still_collapsed = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.nodeId)")
    assert "__auto_agg__fan_0" not in still_collapsed, (
        f"点节点不应展开折叠组（Q2 = B）：{still_collapsed}"
    )

    # 抽屉里的「展开成员」才是展开入口。
    await page.click(".drawer-action[data-action='toggle-group']")
    after = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.nodeId)")
    assert "__auto_agg__fan_0" in after, f"抽屉展开无效：{after}"

    # 再点一次（此时按钮已变成「收起成员」）收回去。
    await page.click(".drawer-action[data-action='toggle-group']")
    again = await page.eval_on_selector_all(
        ".workflow-node", "els => els.map(e => e.dataset.nodeId)")
    assert "__auto_agg__fan_0" not in again, f"收起无效：{again}"


@pytest.mark.asyncio
async def test_click_any_node_opens_detail_drawer(page, fake_web_server):
    """D4：点**任意**节点都开详情——修复「非折叠组长节点点击是纯 no-op」。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    node_id = await page.text_content("#drawer-id")
    assert node_id == "a"

    # 抽屉开合**不改 viewBox**（重排会让用户丢失「我在看哪个节点」）。
    await page.evaluate("""() => {
        const svg = document.querySelector('#workflow-canvas svg');
        window.__viewBoxBefore = svg.getAttribute('viewBox');
    }""")
    await page.click("#workflow-scrim")
    await page.wait_for_function(
        "() => !document.getElementById('workflow-drawer').classList.contains('open')")
    assert await page.evaluate(
        "() => document.querySelector('#workflow-canvas svg').getAttribute('viewBox')"
    ) == await page.evaluate("() => window.__viewBoxBefore")

    # 重新打开后 Esc 也要能关（D4 的三种关闭方式）。
    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.keyboard.press("Escape")
    await page.wait_for_function(
        "() => !document.getElementById('workflow-drawer').classList.contains('open')")


@pytest.mark.asyncio
async def test_legend_is_visible_and_collapsible(page, fake_web_server):
    """D1：图例桌面默认展开、可折叠，且八档状态都在。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-legend:not([hidden])")

    text = await page.text_content("#workflow-legend")
    for label in ("未选中", "预算超限", "blocked", "passed"):
        assert label in text, f"图例缺少 {label}"

    assert await page.is_visible("#legend-body")
    await page.click("#legend-toggle")
    assert not await page.is_visible("#legend-body")
    await page.click("#legend-toggle")
    assert await page.is_visible("#legend-body")


@pytest.mark.asyncio
async def test_convo_tab_lazily_fetches_transcript(page, fake_web_server):
    """M4.2：切「对话」tab **才**触发 transcript 请求（懒加载契约）。

    放在「对话」tab 而非「任务」tab 是刻意的：放「任务」tab 意味着**一打开面板
    就得发 transcript 请求**，破掉 D4 的懒加载。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    # 测试 tab 没有真实 session（事件是直接派发的），补一个让请求能成形；
    # 路由本身（404 降级 / 三态）由 ``test_workflow_control_server.py`` 覆盖。
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")

    # 打开面板（默认「任务」tab）——**不该**有任何 transcript 请求。
    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    assert not [u for u in requests if "/transcript" in u], (
        f"打开面板就发了 transcript 请求（破了懒加载）：{requests}"
    )

    # 切到「对话」：这时才请求。
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_function(
        "() => document.querySelector('.drawer-body').textContent.length > 0")
    assert [u for u in requests if "/transcript" in u], "切到「对话」没有触发请求"


_ITEM_CONTAINER = {
    "kind": "candidates", "node_id": "fan", "node_kind": "foreach",
    "total": 2, "offset": 0, "limit": 50, "has_more": False,
    "reason_full": "", "reason_length": 0, "reason_truncated": False,
    "candidates": [
        {"index": 0, "subagent_id": "sa-0", "run_id": "r-0", "status": "completed",
         "label": "#0", "summary": "ok", "reason": "", "task": "对 a.js 体检",
         "failure_evidence": {"state": "clean", "total": 0, "truncated": False,
                              "message": "已检查，无失败记录。", "items": []}},
        {"index": 1, "subagent_id": "sa-1", "run_id": "r-1", "status": "failed",
         "label": "#1", "summary": "", "reason": "RuntimeError: boom",
         "task": "对 b.js 体检",
         "failure_evidence": {"state": "present", "total": 3, "truncated": True,
                              "message": "该 run 已结束；其执行记录里有失败步骤。",
                              "items": [{"type": "tool_result", "step": 7,
                                         "tool_name": "Bash", "status": "error",
                                         "error_type": "tool_error",
                                         "observation": "3 failed, 12 passed",
                                         "message": None, "text_truncated": False}]}},
    ],
}

#: 下钻载荷带**完整形态**的失败证据：它是唯一能渲染出「条目正文」的路径
#: （候选行只给计数线索）。`observation` 刻意超过前端 300 字符的预览上限，
#: 用来锁住「预览已截断」的标注——不标注会让用户以为正文就这么短（#212/#213 的坑）。
_LONG_OBSERVATION = "3 failed, 12 passed in 4.21s；" + "x" * 400

_ITEM_SINGLE = {
    "kind": "single", "node_id": "fan", "node_kind": "foreach",
    "subagent_id": "sa-1", "run_id": "r-1", "index": 1, "status": "failed",
    "task": "对 b.js 体检",
    "messages": [{"role": "assistant", "content": "THIS-IS-ITEM-ONE"}],
    "truncated": False, "included_tool_results": False,
    "limit": 50, "content_limit": 4000,
    "reason_full": "RuntimeError: boom", "reason_length": 18,
    "reason_truncated": False,
    "failure_evidence": {
        "state": "present", "total": 9, "truncated": True,
        "message": "该 run 已结束；其执行记录里有失败步骤（下面是最近的几条）。",
        "items": [
            {"type": "tool_result", "step": 7, "tool_name": "Bash",
             "status": "error", "error_type": "tool_error",
             "observation": _LONG_OBSERVATION, "message": None,
             "text_truncated": True},
            {"type": "llm_error", "step": 9, "tool_name": None,
             "status": "error", "error_type": "network_timeout",
             "observation": None, "message": "upstream timed out",
             "text_truncated": False},
        ],
    },
}


@pytest.mark.asyncio
async def test_foreach_candidate_drilldown_shows_that_item(page, fake_web_server):
    """spec Scenario：点候选项 → 按该 ``subagent_id`` 取**它自己**的 transcript。

    审阅发现的功能缺口：候选项点击原本是**空操作**（前端不读 ``subagentId``、
    后端也没有按 subagent 取数的入口）——点了没反应，而这条能力已写进正式 spec。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    requests = []

    async def _transcript_route(route):
        url = route.request.url
        requests.append(url)
        if "subagent_id=sa-1" in url:
            await route.fulfill(json=_ITEM_SINGLE)
        else:
            await route.fulfill(json=_ITEM_CONTAINER)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_selector(".cand[data-index='1']")

    # 点第二项 → 请求必须**指名**那一项的 subagent_id。
    await page.click(".cand[data-index='1']")
    await page.wait_for_function(
        "() => document.querySelector('.drawer-body').textContent.includes('THIS-IS-ITEM-ONE')")
    assert any("subagent_id=sa-1" in url for url in requests), (
        f"下钻没有按 subagent_id 取数（点了没反应）：{requests}"
    )
    body = await page.text_content(".drawer-body")
    assert "第 1 项" in body, body
    assert "对 b.js 体检" in body, body

    # 返回入口：回到候选列表（否则下钻后回不去）。
    await page.click(".transcript-back")
    await page.wait_for_selector(".cand[data-index='0']")


@pytest.mark.asyncio
async def test_foreach_node_shows_progress_count(page, fake_web_server):
    """D5：foreach 容器**常显**「完成 M/N」（不再只在 ≥50 节点折叠时才提项数）。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _wait_app_ready(page)
    snapshot = dict(SNAPSHOT)
    snapshot["nodes"] = [
        {"id": "fan", "kind": "foreach", "status": "started", "runs": 1,
         "summary": "", "started_at": 1, "finished_at": None, "items": 12,
         "items_completed": 3, "items_failed": 1, "items_running": 1,
         "item_states": ["completed"] * 3 + ["failed"] + ["running"] + ["queued"] * 7},
    ]
    snapshot["edges"] = []
    await _start_workflow(page, snapshot)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    text = await page.text_content(".workflow-node[data-node-id='fan']")
    assert "完成 3/12" in text, text
    assert "失败 1" in text, text


@pytest.mark.asyncio
async def test_collapsed_group_shows_aggregated_status(page, fake_web_server):
    """D5：折叠组长显示整组聚合状态（不是它自己的），且颜色可辨（不是兜底灰）。

    回归：``groupStatus`` 曾返回状态词表外的 ``"running"``，``nodeColor`` 落到兜底灰。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, _big_foreach_snapshot())
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    # 组长 fan 自身 started，但组里有 failed 成员 → 聚合状态 failed（红），不是兜底灰。
    status = await page.eval_on_selector(
        ".workflow-node[data-node-id='fan']", "e => e.dataset.status")
    assert status == "failed"

    stroke = await page.eval_on_selector(
        ".workflow-node[data-node-id='fan'] rect", "e => e.getAttribute('stroke')")
    assert stroke == "#f87171", stroke


@pytest.mark.asyncio
async def test_gestures_pan_after_pinch_release(page, fake_web_server):
    """5.2 回归：双指 pinch 后抬起一指，剩下的手指仍能继续 pan。

    gesture 层按**指针**记 capture（不是一个全局布尔位）——否则第二根手指落下
    会把状态置成「已拖动」，抬起后残留的错误状态会让复位逻辑失效。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")

    result = await page.evaluate("""() => {
        const host = document.getElementById('workflow-canvas');
        const svg = host.querySelector('svg');
        const fire = (type, id, x, y) => host.dispatchEvent(new PointerEvent(type, {
            pointerId: id, clientX: x, clientY: y, bubbles: true,
        }));
        const pinchStart = svg.getAttribute('viewBox');

        // pinch：两指分开 → 放大（viewBox 宽变小）
        fire('pointerdown', 1, 100, 100);
        fire('pointerdown', 2, 200, 200);
        fire('pointermove', 1, 60, 60);
        fire('pointermove', 2, 260, 260);
        const pinchEnd = svg.getAttribute('viewBox');

        // 抬起第二指，第一指继续拖动 → 仍应产生 pan（viewBox 原点变化）
        fire('pointerup', 2, 260, 260);
        const before = svg.getAttribute('viewBox');
        fire('pointermove', 1, 120, 120);
        const after = svg.getAttribute('viewBox');
        fire('pointerup', 1, 120, 120);
        return { pinchStart, pinchEnd, before, after };
    }""")

    width_of = lambda vb: float(vb.split()[2])
    assert width_of(result["pinchEnd"]) < width_of(result["pinchStart"]), (
        f"pinch 没放大：{result['pinchStart']} -> {result['pinchEnd']}")
    assert result["after"] != result["before"], (
        f"抬指后 pan 失效：{result['before']} -> {result['after']}")


@pytest.mark.asyncio
async def test_tick_keeps_status_word_and_appends_elapsed(page, fake_web_server):
    """回归（issue #197 follow-up）：本地计时器 tick 不得把状态词覆写成 ``undefined``。

    根因：``tick`` 读的是**快照原始节点**（snake_case、无 ``label``/``elapsedText``），
    却喂给读**布局投影字段**的 ``nodeStatusText``（``node.label`` /
    ``node.elapsedText``）——于是每秒一次的重绘把「completed · 1s」写成
    「undefined · 1s」。手机端尤其明显（图上所有节点都成了 undefined）。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _wait_app_ready(page)
    snapshot = dict(SNAPSHOT)
    snapshot["nodes"] = [
        {"id": "scan", "kind": "subagent", "status": "started", "runs": 1,
         "summary": "", "started_at": time.time(), "finished_at": None},
    ]
    snapshot["edges"] = []
    await _start_workflow(page, snapshot)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    # harness 直接派发事件、绕过了 chat.js 的 showView('workflow')，所以计时器
    # 得手动启动——**不启动的话 tick 永不运行，测试就是假保护**。
    await page.evaluate("() => window.AsterwyndWorkflow.startTicker()")

    # 初渲染（renderNode 走布局投影）一定是对的——先确认基线。
    text = await page.text_content(".workflow-node[data-node-id='scan'] [data-role='status']")
    assert "undefined" not in text, f"初渲染就不对：{text!r}"
    assert "running" in text, text

    # 推进本地计时器（tick 每 1s 跑一次），状态词必须还在。
    await page.wait_for_timeout(2200)
    text = await page.text_content(".workflow-node[data-node-id='scan'] [data-role='status']")
    assert "undefined" not in text, f"tick 把状态词覆写成了 {text!r}"
    assert "running" in text, f"tick 后状态词丢了：{text!r}"


@pytest.mark.asyncio
async def test_tick_keeps_foreach_progress_count(page, fake_web_server):
    """回归：tick 对 foreach 节点也要保留「完成 M/N」（同样读投影字段）。"""
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    snapshot = dict(SNAPSHOT)
    snapshot["nodes"] = [
        {"id": "fan", "kind": "foreach", "status": "started", "runs": 1,
         "summary": "", "started_at": 1, "finished_at": None, "items": 12,
         "items_completed": 3, "items_failed": 1, "items_running": 1,
         "item_states": ["completed"] * 3 + ["failed"] + ["running"] + ["queued"] * 7},
    ]
    snapshot["edges"] = []
    await _start_workflow(page, snapshot)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    await page.evaluate("() => window.AsterwyndWorkflow.startTicker()")

    await page.wait_for_timeout(2200)
    text = await page.text_content(".workflow-node[data-node-id='fan'] [data-role='status']")
    assert "undefined" not in text, f"tick 把 foreach 进度覆写成了 {text!r}"
    assert "完成 3/12" in text, f"tick 后 foreach 进度丢了：{text!r}"


@pytest.mark.asyncio
async def test_tick_keeps_tab_elapsed_live(page, fake_web_server):
    """回归（issue #197 follow-up）：运行中 tab 的「已跑 Xs」必须逐秒跳。

    根因：``tick()`` 只重绘节点与「最后更新于」，**不重绘多图 tab**——tab 的
    elapsed 冻结在最后一次快照到达的时刻（实测：图跑了 3 分钟，tab 仍写「已跑 5s」，
    而同屏的「最后更新于 19 秒前」在跳，两个数字自相矛盾）。design D6 明确要求
    运行中「已跑 42s」**实时跳秒**。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _wait_app_ready(page)
    snapshot = dict(SNAPSHOT)
    snapshot["started_at"] = time.time() - 5   # 图级起始时刻 → tab 显示「已跑 5s」
    await _start_workflow(page, snapshot)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    await page.evaluate("() => window.AsterwyndWorkflow.startTicker()")

    selector = ".graph-tab[data-workflow-id='wf_demo'] .graph-tab-sub"
    before = await page.text_content(selector)
    assert "已跑" in before, f"tab 未显示运行耗时：{before!r}"

    await page.wait_for_timeout(2500)
    after = await page.text_content(selector)
    assert after != before, (
        f"tab 耗时没有跳秒（tick 不重绘 tab）：{before!r} → {after!r}"
    )


_TOOL_CALL_SINGLE = {
    "kind": "single", "node_id": "a", "node_kind": "subagent",
    "subagent_id": "sa-a", "run_id": "r-a",
    "messages": [
        {"role": "system", "content": "你是一个受限的子 agent。"},
        {"role": "user", "content": "扫描仓库"},
        # 真实形态：模型这一轮**没有文字**，只有两个工具调用（回归的原始症状）。
        {"role": "assistant", "content": "",
         "tool_calls": [
             {"name": "Read", "arguments": "{\"path\": \"AGENTS.md\"}",
              "arguments_truncated": False},
             {"name": "Grep", "arguments": "{\"pattern\": \"workflow\", \"path\": \".\"}",
              "arguments_truncated": False},
         ]},
        {"role": "assistant", "content": "扫描完成：发现 3 处问题。"},
    ],
    "truncated": False, "included_tool_results": False,
    "limit": 50, "content_limit": 4000,
    "reason_full": "", "reason_length": 0, "reason_truncated": False,
}


@pytest.mark.asyncio
async def test_convo_tab_renders_tool_calls_instead_of_blank_lines(page, fake_web_server):
    """回归（用户实测发现）：只发起工具调用、不输出文字的 assistant 轮次**不能变空行**。

    原始症状：transcript 投影丢掉了 ``tool_calls``，于是模型每一个
    「只调工具、不写文字」的轮次（AgentLoop 里占大多数）都渲染成一行空的
    「ASSISTANT」——用户看到一连串空行，以为「对话不全」。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})

    async def _transcript_route(route):
        await route.fulfill(json=_TOOL_CALL_SINGLE)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    # 等 chat.js 的异步 init 落定再派发：否则它的 showHub() 会在派发之后把
    # #workflow-view 的 active 摘掉 → svg 变隐藏（与 #191 同源的既有竞态）。
    await _wait_app_ready(page)
    await _start_workflow(page, SNAPSHOT)
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")
    await page.wait_for_selector(
        "#workflow-canvas svg.workflow-svg", state="visible")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_selector(".tool-call-block")

    body = await page.text_content(".drawer-body")
    # 那一轮的工具调用必须可见（名字 + 参数）。
    assert "Read" in body, body
    assert "AGENTS.md" in body, body
    assert "Grep" in body, body
    # 两个 assistant 轮次都该有自己的角色标签（工具调用那一轮也是 assistant 的动作，
    # 标签不能省——用户要能分辨「谁在调工具」）。回归的**症状是空文本行**，不是标签。
    # 注意 ``text-transform: uppercase`` 只在 CSS 层——DOM 里的文本是小写。
    roles = await page.eval_on_selector_all(
        ".msg-role",
        "nodes => nodes.filter(n => n.textContent.toLowerCase() === 'assistant').length")
    assert roles == 2, f"assistant 轮次标签数不对：{roles}"
    # 真正的回归判据：不该存在**纯空白**的文本行（旧实现每轮产出一个空行）。
    blanks = await page.eval_on_selector_all(
        ".msg-text", "nodes => nodes.filter(n => !n.textContent.trim()).length")
    assert blanks == 0, f"仍渲染了 {blanks} 行空文本（正是用户看到的空 ASSISTANT）"


@pytest.mark.asyncio
async def test_convo_tab_survives_malformed_tool_arguments(page, fake_web_server):
    """``arguments`` 不是合法 JSON（流式截断/工具自定义格式）时原样显示，不炸。"""
    payload = dict(_TOOL_CALL_SINGLE)
    payload["messages"] = [
        {"role": "assistant", "content": "",
         "tool_calls": [{"name": "Bash", "arguments": "not-json{{{",
                         "arguments_truncated": True}]},
    ]
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    async def _transcript_route(route):
        await route.fulfill(json=payload)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    # 等 chat.js 的异步 init 落定再派发：否则它的 showHub() 会在派发之后把
    # #workflow-view 的 active 摘掉 → svg 变隐藏（与 #191 同源的既有竞态）。
    await _wait_app_ready(page)
    await _start_workflow(page, SNAPSHOT)
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")
    await page.wait_for_selector(
        "#workflow-canvas svg.workflow-svg", state="visible")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_selector(".tool-call-block")

    body = await page.text_content(".drawer-body")
    assert "not-json{{{" in body, body
    assert "参数已截断" in body, body
    assert not errors, f"渲染抛异常：{errors}"


@pytest.mark.asyncio
async def test_candidate_rows_show_failure_clues(page, fake_web_server):
    """候选项行必须渲染失败线索——含 R1 新增的**负向态**分支。

    review R2 Issue 1 实证：这条渲染块此前**零覆盖**（既有的 `_ITEM_CONTAINER`
    fixture 的候选字典根本没有 `failure_evidence` 键，`if (evidence)` 恒假，整块被
    跳过），删掉它测试全绿——假保护。本条把三种态都渲染出来：
    `present`（计数线索）、`clean`（负向态也要有一行，Q3 的精神：不显示 != 没事）。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})

    async def _transcript_route(route):
        await route.fulfill(json=_ITEM_CONTAINER)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_selector(".cand[data-index='1']")

    row0 = await page.text_content(".cand[data-index='0']")
    assert "已检查，无失败记录" in row0, (
        f"clean 的候选行必须有正向声明（负向态也各配一行文案，Q3）：{row0!r}"
    )
    row1 = await page.text_content(".cand[data-index='1']")
    assert "3 条工具/LLM 失败" in row1, f"present 的候选行必须给计数线索：{row1!r}"


@pytest.mark.asyncio
async def test_convo_tab_prefers_backend_message(page, fake_web_server):
    """证据区文案**优先用后端** `message`（review R2 Issue 2）。

    后端为「尚未派发」等情形写了专用文案（设计 D1 要求与「取不到记录」分开说）；
    前端若一律用自建表，那些区分就到不了用户眼前。这里给一个**只有后端会写**的
    句子，验证它真的被渲染出来。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    payload = {
        "kind": "none", "node_id": "a", "node_kind": "subagent",
        "message": "该节点未执行（未派发或未产生 run）",
        "reason_full": "", "reason_length": 0, "reason_truncated": False,
        "failure_evidence": {
            "state": "unavailable",
            "total": 0, "truncated": False,
            "message": "该节点尚未派发，暂时没有失败证据。",
            "items": [],
        },
    }

    async def _transcript_route(route):
        await route.fulfill(json=payload)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg")
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_function(
        "() => document.querySelector('.drawer-body').textContent.includes('失败证据')"
        " || document.querySelector('.drawer-body').textContent.includes('尚未派发')")

    body = await page.text_content(".drawer-body")
    assert "该节点尚未派发" in body, (
        f"前端丢弃了后端 message——「尚未派发」与「取不到记录」的区分在 UI 层落空：{body!r}"
    )


@pytest.mark.asyncio
async def test_convo_tab_renders_failure_evidence_body(page, fake_web_server):
    """「对话」tab 的失败证据**正文区**：标题条数 + 两条条目 + 预览截断标注 + 截断页脚。

    这是本 change 的**头号交付物**——issue #215 要回答的「哪个工具失败了、为什么」，
    答案正文只长在这段渲染里。review R3 实证：删掉整段条目渲染、删掉文本、关掉截断
    页脚、去掉标题条数，四条变异在 949 条测试下**全部存活**（用户直接退回
    「绿节点、零信号」的原始症状而无人报警）。本条把这四条一次锁死。

    同时锁住 grill Q2 用户确认的「前端预览 300 字符 + 显式截断标注」——
    「预览比正文短却不告知」是本仓库已踩过两次的坑（#212/#213）。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})

    async def _transcript_route(route):
        await route.fulfill(json=_ITEM_SINGLE)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _wait_app_ready(page)
    await _start_workflow(page, SNAPSHOT)
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")
    await page.wait_for_selector(
        "#workflow-canvas svg.workflow-svg", state="visible")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_selector(".failure-item")

    body = await page.text_content(".drawer-body")
    # 标题带**真实条数**（不是只写「失败证据」）。断言必须落在**标题元素**上：
    # 页脚的「共 9 条，只显示了最近 2 条」也含同样的子串，用 body 会漏掉这条变异
    # （实测：改标题为裸「失败证据」时 body 断言仍绿）。
    heading = await page.text_content(".drawer-body h3")
    assert "共 9 条" in heading, f"标题丢了真实条数：{heading!r}"
    # 条目正文：工具名 + 步序 + 错误类型 + 文本首行（tool_result 走 observation）。
    assert "Bash" in body and "step 7" in body and "tool_error" in body, body
    assert "3 failed, 12 passed" in body, f"失败文本没渲染出来：{body!r}"
    # 第二条走 message（llm_error 没有 observation）。
    assert "network_timeout" in body and "upstream timed out" in body, body
    # 预览截断必须**显式标注**（Q2 用户确认；#212/#213 的坑）。
    assert "预览已截断" in body, f"预览截断没有标注——用户会以为正文就这么短：{body!r}"
    # 截断页脚报告「省略了多少」。
    assert "共 9 条，只显示了最近 2 条" in body, f"截断页脚缺失：{body!r}"

    # 预览确实被截到 300 字符量级（不是把全文灌进来），且**摘要也不得无界**——
    # 一条没有换行的超长 observation 会让摘要绕过预览上限（review R3 后由本条发现）。
    pre_text = await page.text_content(".failure-text")
    assert len(pre_text) <= 300, f"预览未收窄：{len(pre_text)} 字符"
    summary_text = await page.text_content(".failure-summary")
    assert len(summary_text) <= 200, f"条目摘要无界：{len(summary_text)} 字符"
    assert body.count("x") < 429, "全量失败文本仍出现在 DOM 里"


@pytest.mark.asyncio
async def test_task_tab_shows_failure_clue_from_snapshot(page, fake_web_server):
    """「任务」tab 的快照失败线索三态（Q6 方案 D）。

    这是本抽屉**默认**打开的 tab，也是「绿节点有没有隐藏失败」的唯一零请求线索。
    review R3 实证：`SNAPSHOT` fixture 的节点根本没有 `failure_count` 键，
    `failureCountHint(undefined)` 恒返回 `null`，整段被跳过——把它换成 `null`
    全量测试照样绿。本条把三态都锁住：
    `N>0` → ⚠ 计数；`0` → 淡色「已检查、无失败」；无该键 → **不显示**。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _wait_app_ready(page)
    await _start_workflow(page, SNAPSHOT)
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg", state="visible")

    # N>0：默认「任务」tab 上要有 ⚠ 计数线索。
    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    body_a = await page.text_content(".drawer-body")
    assert "3 次工具/LLM 失败" in body_a and "⚠" in body_a, (
        f"有失败的节点在「任务」tab 上没有线索（用户不会知道要点进「对话」）：{body_a!r}"
    )
    hint_a = await page.text_content(".drawer-failure-hint")
    assert "对话" in hint_a, f"线索要指路到「对话」tab：{hint_a!r}"

    # 0：仍是正向声明（已检查、无失败），不是什么都不显示。
    await page.keyboard.press("Escape")
    await page.click(".workflow-node[data-node-id='b']")
    await page.wait_for_selector("#workflow-drawer.open")
    body_b = await page.text_content(".drawer-body")
    assert "已检查、无失败" in body_b, (
        f"零失败必须显示正向声明（Q3 的精神：不显示 != 没事）：{body_b!r}"
    )

    # 无该键（None）：**不显示**——「没数据」不得冒充「已检查」。
    await page.keyboard.press("Escape")
    await page.click(".workflow-node[data-node-id='join']")
    await page.wait_for_selector("#workflow-drawer.open")
    body_join = await page.text_content(".drawer-body")
    assert "已检查、无失败" not in body_join
    assert "失败" not in body_join


@pytest.mark.asyncio
async def test_convo_tab_falls_back_when_backend_message_is_missing(page, fake_web_server):
    """后端**没给** `message` 时，前端退化为自己的文案表——而不是显示空白。

    这条守的是 `failureText` 的兜底分支（review R3 实证：把它删成 `return ''`
    全量浏览器用例仍绿）。真实场景是老载荷 / 降级路径：只有 `state`、没有 `message`。
    显示空白会被读成「没问题」，正是本 change 要消灭的误读。
    """
    await page.set_viewport_size({"width": 1280, "height": 800})
    payload = {
        "kind": "single", "node_id": "a", "node_kind": "subagent",
        "subagent_id": "sa-x", "run_id": "r-x",
        "messages": [{"role": "assistant", "content": "hi"}],
        "truncated": False, "included_tool_results": False,
        "limit": 50, "content_limit": 4000,
        "reason_full": "", "reason_length": 0, "reason_truncated": False,
        # 只有 state，**没有** message（老载荷 / 降级）。
        "failure_evidence": {"state": "clean", "total": 0, "truncated": False,
                             "items": []},
    }

    async def _transcript_route(route):
        await route.fulfill(json=payload)

    await page.route("**/transcript*", _transcript_route)
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    # chat.js 的 ws 握手 → 建 tab → showView('chat') 是**异步**的，可能发生在派发
    # 之后并把 workflow-view 的 active 摘掉（svg 间歇性 hidden）。既有 13 条用例都
    # 走这个守卫，新增用例必须跟上，否则守护「头号交付物」的断言在 CI 里靠运气。
    await _wait_app_ready(page)
    await _start_workflow(page, SNAPSHOT)
    await page.evaluate("() => { window.__testTab.sessionId = 'test-session'; }")
    await page.wait_for_selector("#workflow-canvas svg.workflow-svg", state="visible")

    await page.click(".workflow-node[data-node-id='a']")
    await page.wait_for_selector("#workflow-drawer.open")
    await page.click(".drawer-tab[data-tab='convo']")
    await page.wait_for_function(
        "() => document.querySelector('.drawer-body').textContent.includes('失败证据')")

    body = await page.text_content(".drawer-body")
    assert "已检查，无失败记录" in body, (
        f"后端没给 message 时前端兜底表应出文案，而不是空白（空白会被读成没问题）：{body!r}"
    )

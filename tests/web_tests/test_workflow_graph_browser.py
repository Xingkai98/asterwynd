"""Workflow 流程图浏览器 smoke（change ``workflow-graph-visualization``，tasks 3.1/5.1/5.2）。

Q7 的验收路径「CI 装 chromium 跑关键 smoke」：这里覆盖 node 单测覆盖不到的部分——
真实 DOM 渲染、事件分发到视图、自动打开视图、跨端断点、pinch/pan 手势。

CI 里没有浏览器时自动 skip（``p.chromium.launch`` 失败），与既有 ``test_browser.py``
同口径；CI 的 validate job 现在会 ``playwright install chromium``，所以这条会真跑。
"""
import threading

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
         "summary": "done", "started_at": 0, "finished_at": 1},
        {"id": "b", "kind": "subagent", "status": "started", "runs": 1,
         "summary": "", "started_at": 1, "finished_at": None},
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
async def test_graph_recursion_exceeded_renders_notice_not_graph(page, fake_web_server):
    """Q6/决策 9：超限只渲染告警条，不画图（且不按 nodes.length 判断）。"""
    await page.goto(fake_web_server["url"])
    await page.wait_for_function("() => window.AsterwyndWorkflow !== undefined")
    await _start_workflow(page, {
        "workflow_id": "wf_big",
        "status": "graph_recursion_exceeded",
        "goal": "too big",
        "timestamp": 1.0,
        "nodes": [{"id": f"n{i}", "kind": "subagent", "status": "pending"} for i in range(210)],
        "edges": [],
        "diagnostics": {"reason": "max_nodes", "recursion_limit": 200, "message": "boom"},
    })

    await page.wait_for_selector("#workflow-canvas .graph-notice.error")
    notice = await page.text_content("#workflow-canvas .graph-notice.error")
    assert "max_nodes" in notice
    assert await page.query_selector("#workflow-canvas svg.workflow-svg") is None


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
    tabs = await page.eval_on_selector_all(
        "#workflow-tabs .graph-tab .graph-tab-label", "els => els.map(e => e.textContent)")
    assert tabs == ["first", "second"]

    # 点第一个 tab 切过去（follow 关掉后不再被新事件抢焦点）。
    await page.click("#workflow-tabs .graph-tab:first-child")
    active = await page.eval_on_selector(
        "#workflow-tabs .graph-tab.active .graph-tab-label", "e => e.textContent")
    assert active == "first"

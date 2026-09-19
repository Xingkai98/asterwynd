"""前端：图级终态 ``stalled`` 的表达 + 因由如实可见（change ``workflow-terminal-honesty``）。

覆盖 Q4（节点因由在前端不能被泛化文案遮蔽）与 D6（配色/文案可分辨、配色门槛）：

- **Q4**：后端 D3 把真实成因写进 ``node.reason``（图级闸门名+上限 / 「入边互等」），
  前端 ``explainNode()`` 必须让**用户看到那句话**——否则 #218 在用户可见层面没修。
- **D6**：``stalled`` 的配色/文案与 ``completed`` / ``budget_exceeded`` 可分辨，
  且到每个既有图级档的 RGB 欧氏距离 ≥ 100（可机械断言的「可分辨」门槛）。
"""
import json
import subprocess
from pathlib import Path

import pytest

GRAPH_JS = Path(__file__).parents[2] / "web" / "static" / "workflow_graph.js"

_HARNESS = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const calls = JSON.parse(process.argv[2]);
const context = { window: {} };
vm.createContext(context);
vm.runInContext(source, context);
const api = context.window.AsterwyndWorkflowGraph;
const out = calls.map(([name, argv]) => api[name](...argv));
process.stdout.write(JSON.stringify(out));
"""


def call(name: str, *args):
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(GRAPH_JS), json.dumps([[name, list(args)]])],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)[0]


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node unavailable")


# --- Q4：用户可见的因由 ------------------------------------------------------


def _max_routes_snapshot():
    """``max_routes`` 撞线：图级 ``graph_recursion_exceeded`` + 节点因由含闸门信息。"""
    return {
        "status": "graph_recursion_exceeded",
        "diagnostics": {"reason": "max_routes", "limit": 2,
                        "message": "GraphRecursionError: route node 'cycle_gate' exceeded max_routes 2"},
        "nodes": [
            {"id": "cycle_gate", "kind": "route", "status": "blocked",
             "reason": "图级闸门 max_routes 触发（GraphRecursionError: route node 'cycle_gate' exceeded max_routes 2），本节点未派发"},
            {"id": "end", "kind": "aggregate", "status": "blocked",
             "reason": "图级闸门 max_routes 触发（GraphRecursionError: route node 'cycle_gate' exceeded max_routes 2），本节点未派发"},
        ],
        "edges": [{"from": "cycle_gate", "to": "end", "kind": "control", "status": "inactive"}],
    }


def _stalled_snapshot():
    """无图级闸门的死锁：图级 ``stalled`` + 节点因由说明「入边互等」。"""
    return {
        "status": "stalled",
        "diagnostics": {},   # 无图级闸门
        "nodes": [
            {"id": "cycle_gate", "kind": "route", "status": "blocked",
             "reason": "入边互相等待（body），本节点永远未就绪"},
            {"id": "body", "kind": "aggregate", "status": "blocked",
             "reason": "入边互相等待（cycle_gate），本节点永远未就绪"},
        ],
        "edges": [{"from": "body", "to": "cycle_gate", "kind": "data", "status": "blocked"}],
    }


def test_route_cap_reason_reaches_the_user_visible_text():
    """Q4：``max_routes`` 图的用户可见因由必须含 ``max_routes``（不能被泛化文案遮掉）。

    只做后端穿透时，``explainNode`` 会返回泛化的「流程因图超限被停止…」，
    ``max_routes`` 与上限值一个字都不出现。
    """
    snap = _max_routes_snapshot()
    nodes = {n["id"]: n for n in snap["nodes"]}
    text = call("explainNode", nodes["cycle_gate"], snap["edges"], nodes,
                snap["status"], snap["diagnostics"])
    assert "max_routes" in text, f"用户可见因由未含闸门名：{text!r}"


def test_deadlock_reason_states_mutual_wait_not_upstream():
    """Q4：``stalled`` 死锁图的用户可见因由必须说明「入边互等」。

    只做后端穿透时，``explainNode`` 会返回「被上游 body 挡住，未执行」——
    那只说了「谁挡住」，没说「为什么永远不就绪」。
    """
    snap = _stalled_snapshot()
    nodes = {n["id"]: n for n in snap["nodes"]}
    text = call("explainNode", nodes["cycle_gate"], snap["edges"], nodes,
                snap["status"], snap["diagnostics"])
    assert "入边互相等待" in text, f"用户可见因由未说明互等：{text!r}"


def test_fallback_reason_does_not_hijack_generic_path():
    """Q4 反向护栏：纯兜底句**不**提权——它没有信息量，泛化路径更准确。

    兜底句 ``workflow ended before...`` 若被当成「具体因由」提权，会把更有用的
    图级/上游说明遮掉，等于把假话提前。
    """
    assert call("isSpecificNodeReason", "workflow ended before the node became ready") is False
    assert call("isSpecificNodeReason", "") is False
    assert call("isSpecificNodeReason", "图级闸门 max_routes 触发，本节点未派发") is True
    assert call("isSpecificNodeReason", "入边互相等待（body），本节点永远未就绪") is True


def test_budget_graph_still_takes_the_generic_stop_reason():
    """Q4 回归：预算停的 ``blocked`` 节点仍归图级停止原因（既有 G12 语义不变）。"""
    snap = {
        "status": "budget_exceeded",
        "nodes": [{"id": "w", "kind": "subagent", "status": "blocked", "reason": ""}],
        "edges": [],
    }
    nodes = {n["id"]: n for n in snap["nodes"]}
    text = call("explainNode", nodes["w"], snap["edges"], nodes, snap["status"],
                {"budget": {"exceeded_dimension": "tokens"}})
    assert "预算" in text, f"预算停的泛化文案丢了：{text!r}"


# --- D6：stalled 的视觉与文案 -------------------------------------------------


def test_stalled_has_a_graph_status_color_and_label():
    """D6：``stalled`` 必须有图级配色与人话标签，不能显示裸字符串。"""
    colors = call("graphStatusColors")
    assert "stalled" in colors
    label = call("graphStatusLabel", "stalled")
    assert label != "stalled", "不得显示裸字符串"
    assert "停滞" in label


def test_stalled_label_mentions_no_node_completed():
    """D6：tab 徽标文案要说明「无节点完成」——这是它与 failed 的区分点。"""
    label = call("graphStatusLabel", "stalled")
    assert "无节点完成" in label, f"文案未说明零完成：{label!r}"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _distance(a: str, b: str) -> float:
    ra, rb = _rgb(a), _rgb(b)
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5


def test_stalled_color_is_distinguishable_from_every_existing_graph_status():
    """D6：``stalled`` 到每个既有图级档的 RGB 欧氏距离 ≥ 100（「可分辨」的机械门槛）。

    既有调色板最接近的一对是 ``completed_with_failures`` ↔ ``budget_exceeded``，
    距离仅 51——若 ``stalled`` 落在同一橙带，就是同类混淆。
    """
    colors = call("graphStatusColors")
    stalled = colors["stalled"]
    for key, color in colors.items():
        if key == "stalled":
            continue
        assert _distance(stalled, color) >= 100, (
            f"stalled({stalled}) 与 {key}({color}) 距离 {_distance(stalled, color):.1f} < 100，不可分辨"
        )


def test_stalled_color_does_not_reuse_budget_exceeded_orange():
    """D6：``stalled`` 不得复用 ``budget_exceeded`` 的橙（二者语义不同）。"""
    colors = call("graphStatusColors")
    assert colors["stalled"] != colors["budget_exceeded"]
    assert colors["stalled"] != colors["completed_with_failures"]


def test_stalled_is_terminal_for_pruning_in_both_frontend_copies():
    """D5：前端两份副本（``workflow.js`` 数组 + ``workflow_graph.js`` 函数）都要含 stalled。"""
    import re

    workflow_js = (Path(__file__).parents[2] / "web" / "static" / "workflow.js").read_text()
    match = re.search(r"const TERMINAL_STATUSES = \[(.*?)\];", workflow_js, re.S)
    assert match, "TERMINAL_STATUSES 不在 workflow.js 里了"
    assert "stalled" in match.group(1)

    graph_js = GRAPH_JS.read_text()
    fn = re.search(r"function isGraphTerminal\(status\)\s*\{(.*?)\n  \}", graph_js, re.S)
    assert fn, "isGraphTerminal 不在 workflow_graph.js 里了"
    assert "stalled" in fn.group(1)


def test_legend_explains_stalled():
    """D6：图例必须解释 ``stalled``（图例与词表同源，不漂移）。"""
    legend = call("legendModel")
    graph_statuses = {entry["key"]: entry for entry in legend["graphStatuses"]}
    assert "stalled" in graph_statuses, "图例缺少图级终态一节或缺少 stalled"
    entry = graph_statuses["stalled"]
    assert entry["text"], "stalled 图例条目必须有人话解释"
    assert entry["color"] == call("graphStatusColors")["stalled"]
    assert entry["label"] == call("graphStatusLabel", "stalled")


def test_legend_covers_every_graph_status():
    """图例的图级终态一节与 ``GRAPH_STATUS_COLORS`` 词表同源。"""
    legend = call("legendModel")
    assert {e["key"] for e in legend["graphStatuses"]} == set(call("graphStatusColors"))
    for entry in legend["graphStatuses"]:
        assert entry["text"], f"{entry['key']} 缺人话解释"

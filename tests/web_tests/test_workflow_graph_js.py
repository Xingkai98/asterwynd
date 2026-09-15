"""前端 workflow 图纯函数单测（change ``workflow-graph-visualization``，tasks 3.2/3.3/4.1/5.1/5.2）。

Q7 的验收路径：分层布局 / 状态映射 / 折叠归类**与 DOM 解耦**，用 node + vm 在
CI 里真跑（复用 ``tests/web_tests/test_server.py`` 的 markdown.js 先例）。
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
    """在 node + vm 里调用前端纯函数，返回 JSON 反序列化后的结果。"""
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(GRAPH_JS), json.dumps([[name, list(args)]])],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)[0]


def call_many(*calls):
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(GRAPH_JS), json.dumps([list(c) for c in calls])],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node unavailable")


def _nodes(*specs):
    return [{"id": node_id, "kind": kind, "status": status} for node_id, kind, status in specs]


def _edge(source, target, *, kind="data", status="inactive", channel="summary",
          required=True, reducer=None):
    return {
        "from": source, "to": target, "kind": kind, "status": status,
        "channel": channel, "required": required, "reducer": reducer,
    }


# --- 3.2 状态映射 -----------------------------------------------------------


def test_node_colors_cover_seven_tiers():
    """spec「节点状态高亮」：七档各有颜色，且三档基本色对齐 spec 措辞。"""
    colors = call("nodeColors")
    assert set(colors) == {
        "pending", "started", "completed", "failed",
        "cancelled", "blocked", "budget_exceeded",
    }
    assert colors["completed"] == "#4ade80"   # 绿
    assert colors["started"] == "#60a5fa"     # 蓝
    assert colors["pending"] == "#94a3b8"     # 灰


def test_node_color_falls_back_for_unknown_status():
    assert call("nodeColor", "something_new") == "#94a3b8"


def test_edge_status_styles_cover_five_tiers():
    styles = call("edgeStatusStyles")
    assert set(styles) == {"inactive", "ready", "active", "passed", "blocked"}


def test_edge_style_distinguishes_passed_and_inactive():
    passed = call("edgeStyle", _edge("a", "b", status="passed"))
    inactive = call("edgeStyle", _edge("a", "b", status="inactive"))
    assert passed["color"] != inactive["color"]
    assert passed["opacity"] > inactive["opacity"]


def test_channel_dash_patterns():
    """channel 决定线型：summary/result_ref 实线、artifact 虚线、bus 点线。"""
    assert call("channelDash", "summary") == []
    assert call("channelDash", "result_ref") == []
    assert call("channelDash", "artifact") != []
    assert call("channelDash", "bus") != []


# --- 3.2 分层布局 -----------------------------------------------------------


CHAIN_NODES = _nodes(("a", "subagent", "completed"), ("b", "subagent", "started"),
                     ("c", "aggregate", "pending"))
CHAIN_EDGES = [_edge("a", "b"), _edge("b", "c")]


def test_layers_follow_dag_topology():
    layers = call("assignLayers", CHAIN_NODES, CHAIN_EDGES)
    assert layers == {"a": 0, "b": 1, "c": 2}


def test_layers_place_join_after_all_branches():
    nodes = _nodes(("a", "subagent", "completed"), ("b", "subagent", "completed"),
                   ("join", "aggregate", "started"))
    edges = [_edge("a", "join"), _edge("b", "join")]
    assert call("assignLayers", nodes, edges) == {"a": 0, "b": 0, "join": 1}


def test_layers_survive_cycles(monkeypatch):
    """route 回边成环：分层必须收敛（不无限循环、不抛）。"""
    nodes = _nodes(("work", "subagent", "started"), ("gate", "route", "pending"),
                   ("done", "subagent", "pending"))
    edges = [_edge("work", "gate"), _edge("gate", "done", kind="control"),
             _edge("gate", "work", kind="control")]
    layers = call("assignLayers", nodes, edges)
    assert set(layers) == {"work", "gate", "done"}
    assert layers["gate"] > layers["work"]


def test_horizontal_layout_moves_right_along_layers():
    layout = call("layoutGraph", CHAIN_NODES, CHAIN_EDGES, {"orientation": "horizontal"})
    by_id = {node["id"]: node for node in layout["nodes"]}
    assert by_id["a"]["x"] < by_id["b"]["x"] < by_id["c"]["x"]


def test_vertical_layout_moves_down_along_layers():
    layout = call("layoutGraph", CHAIN_NODES, CHAIN_EDGES, {"orientation": "vertical"})
    by_id = {node["id"]: node for node in layout["nodes"]}
    assert by_id["a"]["y"] < by_id["b"]["y"] < by_id["c"]["y"]


def test_layout_does_not_overlap_same_layer_siblings():
    nodes = _nodes(("a", "subagent", "started"), ("b", "subagent", "started"),
                   ("join", "aggregate", "pending"))
    edges = [_edge("a", "join"), _edge("b", "join")]
    layout = call("layoutGraph", nodes, edges, {"orientation": "vertical"})
    by_id = {node["id"]: node for node in layout["nodes"]}
    assert by_id["a"]["x"] != by_id["b"]["x"]
    assert abs(by_id["a"]["y"] - by_id["b"]["y"]) < 1


def test_layout_returns_edge_paths_between_endpoints():
    layout = call("layoutGraph", CHAIN_NODES, CHAIN_EDGES, {"orientation": "horizontal"})
    assert len(layout["edges"]) == 2
    for edge in layout["edges"]:
        assert edge["path"].startswith("M ")
        assert edge["from"] and edge["to"]


def test_edge_paths_are_finite_numbers():
    """回归：``edgePath`` 必须拿到带 width/height 的节点盒——缺失会画出 ``M NaN NaN``。"""
    result = call_many(
        ["layoutGraph", [CHAIN_NODES, CHAIN_EDGES, {"orientation": "horizontal"}]],
        ["layoutGraph", [CHAIN_NODES, CHAIN_EDGES, {"orientation": "vertical"}]],
    )
    for layout in result:
        for edge in layout["edges"]:
            assert "NaN" not in edge["path"], edge["path"]
            assert "undefined" not in edge["path"]


def test_layout_reports_content_size():
    layout = call("layoutGraph", CHAIN_NODES, CHAIN_EDGES, {"orientation": "horizontal"})
    assert layout["width"] > 0 and layout["height"] > 0


def test_empty_graph_layout_is_safe():
    layout = call("layoutGraph", [], [], {"orientation": "horizontal"})
    assert layout["nodes"] == []
    assert layout["edges"] == []


# --- 5.1 跨端断点 -----------------------------------------------------------


def test_orientation_breakpoint_at_720():
    assert call("graphOrientation", 1024) == "horizontal"
    assert call("graphOrientation", 721) == "horizontal"
    assert call("graphOrientation", 720) == "vertical"
    assert call("graphOrientation", 380) == "vertical"


def test_layout_fits_content_into_viewport_width():
    layout = call("fitToWidth", {"width": 4000, "height": 500}, 360)
    assert layout["scale"] < 1
    assert layout["width"] <= 360 / layout["scale"] + 0.001


# --- 5.2 缩放平移 -----------------------------------------------------------


def test_viewbox_transform_identity():
    box = call("viewBoxFor", {"zoom": 1, "panX": 0, "panY": 0, "width": 800, "height": 600})
    assert box == "0 0 800 600"


def test_viewbox_transform_zooms_and_pans():
    box = call("viewBoxFor", {"zoom": 2, "panX": -100, "panY": -50, "width": 800, "height": 600})
    assert box == "100 50 400 300"


def test_pinch_zoom_is_clamped():
    app = call("applyPinch", {"zoom": 1, "panX": 0, "panY": 0}, 10.0, 0, 0)
    assert app["zoom"] <= 4
    shrunk = call("applyPinch", {"zoom": 1, "panX": 0, "panY": 0}, 0.001, 0, 0)
    assert shrunk["zoom"] >= 0.25


def test_pan_updates_offset():
    panned = call("applyPan", {"zoom": 1, "panX": 0, "panY": 0}, 30, -20)
    assert panned["panX"] == 30 and panned["panY"] == -20


# --- 4.1 规模分级 / 折叠 -----------------------------------------------------


def test_small_graph_is_not_collapsed():
    result = call("collapseGraph", CHAIN_NODES, CHAIN_EDGES, {"threshold": 50})
    assert result["collapsed"] is False
    assert [node["id"] for node in result["nodes"]] == ["a", "b", "c"]


def test_large_graph_collapses_foreach_and_auto_layers():
    nodes = _nodes(("src", "subagent", "completed"), ("fan", "foreach", "started"),
                   ("__auto_agg__fan_1", "aggregate", "completed"),
                   ("__auto_agg__fan_2", "aggregate", "pending"),
                   ("root", "aggregate", "started"))
    nodes[1]["items"] = 12
    edges = [
        _edge("src", "fan"),
        _edge("fan", "__auto_agg__fan_1"),
        _edge("fan", "__auto_agg__fan_2"),
        _edge("__auto_agg__fan_1", "root"),
        _edge("__auto_agg__fan_2", "root"),
    ]
    result = call("collapseGraph", nodes, edges, {"threshold": 3})

    assert result["collapsed"] is True
    visible_ids = [node["id"] for node in result["nodes"]]
    assert "fan" in visible_ids
    assert "__auto_agg__fan_1" not in visible_ids
    assert "__auto_agg__fan_2" not in visible_ids
    assert "root" in visible_ids

    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["collapsed"] is True
    assert fan["memberCount"] == 3       # 自身 + 2 个 auto 层成员
    assert fan["itemCount"] == 12


def test_collapse_group_aggregates_status():
    """D5 聚合状态：任一 failed→failed；否则任一 started→运行中；全 completed→completed。

    返回值必须落在节点状态词表内（``NODE_COLORS`` 的键）——返回表外的词会让
    ``nodeColor`` 落到兜底灰（回归：曾经返回 D5 口语里的 ``"running"``）。
    """
    known = set(call("nodeColors"))
    assert call("groupStatus", ["completed", "completed"]) == "completed"
    assert call("groupStatus", ["completed", "started"]) == "started"
    assert call("groupStatus", ["completed", "failed"]) == "failed"
    assert call("groupStatus", ["completed", "blocked"]) == "blocked"
    assert call("groupStatus", ["completed", "budget_exceeded"]) == "blocked"
    assert call("groupStatus", []) == "pending"
    for statuses in ([], ["completed"], ["completed", "started"], ["failed"],
                     ["blocked"], ["budget_exceeded"], ["pending", "started"]):
        assert call("groupStatus", statuses) in known, statuses


def test_collapsed_leader_carries_group_status():
    """D5：折叠后的组长显示**整组**聚合状态，不是它自己的状态。"""
    nodes = _nodes(("src", "subagent", "completed"), ("fan", "foreach", "pending"),
                   ("__auto_agg__fan_1", "aggregate", "failed"),
                   ("root", "aggregate", "started"))
    nodes[1]["items"] = 8
    edges = [_edge("src", "fan"), _edge("fan", "__auto_agg__fan_1"),
             _edge("__auto_agg__fan_1", "root")]
    result = call("collapseGraph", nodes, edges, {"threshold": 3})

    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["collapsed"] is True
    # 组长自己 pending，但组里有 failed 成员 → 组长按整组显示 failed。
    assert fan["status"] == "failed"
    # 聚合状态必须可渲染（落在状态词表内），否则前端会画出兜底灰。
    assert fan["status"] in set(call("nodeColors"))


def test_expanded_group_keeps_members_visible():
    """D5「点击展开局部」：用户展开过的组不再折叠成员。"""
    nodes = _nodes(("fan", "foreach", "started"),
                   ("__auto_agg__fan_1", "aggregate", "completed"),
                   ("root", "aggregate", "started"))
    nodes[0]["items"] = 4
    edges = [_edge("fan", "__auto_agg__fan_1"), _edge("__auto_agg__fan_1", "root")]

    result = call("collapseGraph", nodes, edges, {"threshold": 2, "expandedGroups": ["fan"]})

    visible = [node["id"] for node in result["nodes"]]
    assert "__auto_agg__fan_1" in visible
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert not fan.get("collapsed")


def test_group_leader_flag_survives_expansion():
    """回归：展开态下组长仍须带 ``groupLeader``，否则用户无法再点回收起。

    渲染层用 ``groupLeader``（不是 ``collapsed``）判可点击——若展开后标志消失，
    折叠组就是单向操作。
    """
    nodes = _nodes(("fan", "foreach", "started"),
                   ("__auto_agg__fan_1", "aggregate", "completed"),
                   ("root", "aggregate", "started"))
    nodes[0]["items"] = 4
    edges = [_edge("fan", "__auto_agg__fan_1"), _edge("__auto_agg__fan_1", "root")]

    collapsed = call("collapseGraph", nodes, edges, {"threshold": 2})
    opened = call("collapseGraph", nodes, edges, {"threshold": 2, "expandedGroups": ["fan"]})

    for result, expected_collapsed in ((collapsed, True), (opened, False)):
        fan = next(node for node in result["nodes"] if node["id"] == "fan")
        assert fan["groupLeader"] is True
        assert bool(fan.get("collapsed")) is expected_collapsed


def test_layout_projection_carries_group_leader():
    """``layoutGraph`` 必须把 ``groupLeader`` 透传给渲染层（否则点击无判据）。"""
    nodes = _nodes(("fan", "foreach", "started"),
                   ("__auto_agg__fan_1", "aggregate", "completed"))
    nodes[0]["items"] = 4
    edges = [_edge("fan", "__auto_agg__fan_1")]
    collapsed = call("collapseGraph", nodes, edges, {"threshold": 2})
    layout = call("layoutGraph", collapsed["nodes"], collapsed["edges"],
                  {"orientation": "horizontal"})
    fan = next(node for node in layout["nodes"] if node["id"] == "fan")
    assert fan["groupLeader"] is True
    assert fan["collapsed"] is True


def test_layout_of_collapsed_large_graph_is_finite():
    """4.1 端到端（纯函数侧）：50-200 节点折叠后布局仍可渲染。"""
    nodes = [{"id": f"leaf{i}", "kind": "subagent", "status": "completed"} for i in range(60)]
    nodes.append({"id": "fan", "kind": "foreach", "status": "started", "items": 12})
    nodes += [{"id": f"__auto_agg__{i}", "kind": "aggregate", "status": "completed"}
              for i in range(6)]
    nodes.append({"id": "root", "kind": "aggregate", "status": "started"})
    edges = [{"from": f"leaf{i}", "to": "fan", "channel": "summary", "required": True,
              "reducer": None, "kind": "data", "status": "passed"} for i in range(60)]
    edges += [{"from": "fan", "to": f"__auto_agg__{i}", "channel": "summary",
               "required": True, "reducer": None, "kind": "data", "status": "passed"}
              for i in range(6)]
    edges += [{"from": f"__auto_agg__{i}", "to": "root", "channel": "summary",
               "required": True, "reducer": "concat", "kind": "data", "status": "passed"}
              for i in range(6)]

    collapsed = call("collapseGraph", nodes, edges, {"threshold": 50})
    assert collapsed["collapsed"] is True
    visible = [n["id"] for n in collapsed["nodes"]]
    assert not any(v.startswith("__auto_agg__") for v in visible)

    layout = call("layoutGraph", collapsed["nodes"], collapsed["edges"],
                  {"orientation": "vertical"})
    assert len(layout["nodes"]) == len(collapsed["nodes"])
    for edge in layout["edges"]:
        assert "NaN" not in edge["path"]


def test_collapsed_edges_rewire_around_hidden_nodes():
    nodes = _nodes(("src", "subagent", "completed"), ("fan", "foreach", "started"),
                   ("__auto_agg__fan_1", "aggregate", "completed"),
                   ("root", "aggregate", "started"))
    edges = [_edge("src", "fan"), _edge("fan", "__auto_agg__fan_1"),
             _edge("__auto_agg__fan_1", "root")]
    result = call("collapseGraph", nodes, edges, {"threshold": 2})

    pairs = {(edge["from"], edge["to"]) for edge in result["edges"]}
    assert pairs == {("src", "fan"), ("fan", "root")}


# --- 4.1/Q6 超限告警 --------------------------------------------------------


def test_graph_notice_for_running_graph_is_null():
    assert call("graphNotice", {"status": "running", "nodes": []}) is None


def test_graph_notice_for_recursion_exceeded():
    notice = call("graphNotice", {
        "status": "graph_recursion_exceeded",
        "diagnostics": {"reason": "max_nodes", "recursion_limit": 27, "message": "too big"},
    })
    assert notice["level"] == "error"
    assert "27" in notice["message"]


def test_graph_notice_does_not_read_nodes_length():
    """Q6/决策 9：超限判定不依赖 ``nodes.length``。"""
    many_nodes = [{"id": f"n{i}", "kind": "subagent", "status": "pending"} for i in range(250)]
    assert call("graphNotice", {"status": "running", "nodes": many_nodes}) is None

"""前端纯函数层的新增能力（change ``enhance-workflow-graph-ux``，M2.8–M2.12）。

与 ``test_workflow_graph_js.py`` 同一套 node + vm 验收路径（Q7），分文件是为了让
「#190 既有契约」与「本 change 的新增能力」各自可读。
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


def call_many(*calls):
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(GRAPH_JS), json.dumps([list(c) for c in calls])],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node unavailable")


def _nodes(*specs):
    return [{"id": nid, "kind": kind, "status": status} for nid, kind, status in specs]


def _edge(source, target, *, kind="data", status="inactive", channel="summary"):
    return {
        "from": source, "to": target, "kind": kind, "status": status,
        "channel": channel, "required": True, "reducer": None,
    }


# --- M2.8：图例与词表同源 ---------------------------------------------------


def test_legend_covers_every_node_kind():
    """spec「图例与状态词表同源」：节点类型从 ``KIND_GLYPHS`` 同源生成。"""
    legend = call("legendModel")
    kinds = {entry["key"] for entry in legend["kinds"]}
    assert kinds == set(call("kindGlyphs"))
    for entry in legend["kinds"]:
        assert entry["glyph"] == call("kindGlyph", entry["key"])
        assert entry["text"], "每个图例条目必须有人话解释，不是裸术语"


def test_legend_covers_all_eight_node_states():
    """D1/D2b：八档状态（本 change 从七档扩为八档）每一档都在图例里。"""
    legend = call("legendModel")
    statuses = {entry["key"] for entry in legend["statuses"]}
    assert statuses == set(call("nodeColors"))
    assert "skipped" in statuses
    for entry in legend["statuses"]:
        assert entry["label"] == call("nodeLabel", entry["key"])
        assert entry["color"] == call("nodeColor", entry["key"])
        assert entry["text"], f"{entry['key']} 缺人话解释"


def test_legend_covers_all_edge_statuses_and_channels():
    """边五档 + channel 的三种**线型**都要有图例（D1）。

    channel 按去重后的线型出图例：``summary`` 与 ``result_ref`` 画出来是同一条
    实线，各占一行只是让图例变长。所以这里断言「每个 channel 的线型都有代表」，
    而不是「每个 channel 名都占一行」。
    """
    legend = call("legendModel")
    assert {entry["key"] for entry in legend["edges"]} == set(call("edgeStatusStyles"))
    shown = {tuple(entry["dash"]) for entry in legend["channels"]}
    declared = {tuple(call("channelDash", key)) for key in call("channelNames")}
    assert shown == declared, f"图例线型 {shown} 覆盖不全 {declared}"


def test_legend_dashes_match_channel_dash():
    """图例的线型必须与 ``CHANNEL_DASH`` 同源，否则会漂移。"""
    for entry in call("legendModel")["channels"]:
        assert entry["dash"] == call("channelDash", entry["key"])


# --- M2.9：异常态四重编码 ---------------------------------------------------


def test_every_node_status_has_a_full_encoding():
    """D2：色 + 角标 + 边框形状 + 状态词——不靠颜色单独承载语义。"""
    encodings = call("statusEncodings")
    assert set(encodings) == set(call("nodeColors"))
    for status, enc in encodings.items():
        assert enc["borderStyle"] in ("solid", "dashed", "double"), status
        assert isinstance(enc["badge"], str)


def test_abnormal_statuses_are_distinguishable_without_color():
    """灰度/色觉障碍场景：异常态彼此的**角标与边框**必须不同。"""
    encodings = call("statusEncodings")
    seen = {}
    for status in ("failed", "blocked", "budget_exceeded", "cancelled", "skipped"):
        enc = encodings[status]
        assert enc["badge"], f"{status} 没有角标——只靠颜色区分"
        key = (enc["badge"], enc["borderStyle"])
        assert key not in seen, f"{status} 与 {seen[key]} 的编码完全相同"
        seen[key] = status


def test_skipped_is_visually_distinct_from_blocked():
    """D2b 的立项命题：一个是「被连累没跑成」，一个是「条件没选它」。"""
    encodings = call("statusEncodings")
    assert call("nodeColor", "skipped") != call("nodeColor", "blocked")
    assert encodings["skipped"]["badge"] != encodings["blocked"]["badge"]


#: 角标字形白名单：默认字体（Segoe UI / system-ui）普遍覆盖的 BMP 符号区。
#: ``⏸``（U+23F8）落在 Misc Technical，多数系统字体缺失、渲染成豆腐块——实测踩到过，
#: 所以预算档用 ``‖``（U+2016）而不是暂停符。
_BADGE_WHITELIST = frozenset("✕⊘‖⊝—")


def test_status_badges_avoid_uncovered_glyphs():
    """角标只用白名单里的字符——超出即可能渲染成豆腐块。"""
    for status, enc in call("statusEncodings").items():
        for ch in enc["badge"]:
            assert ch in _BADGE_WHITELIST, (
                f"{status} 的角标 {ch!r} (U+{ord(ch):04X}) 不在安全字形白名单里"
            )


def test_normal_statuses_have_no_badge():
    """正常态不占位：只有异常态才加角标/加粗（D2）。"""
    encodings = call("statusEncodings")
    for status in ("pending", "started", "completed"):
        assert encodings[status]["badge"] == ""
        assert encodings[status]["borderStyle"] == "solid"


# --- M2.12：因果说明 --------------------------------------------------------


def _explain(node_id, nodes, edges, graph_status="completed", diagnostics=None):
    """按 ``explainNode(node, edges, nodesById, graphStatus, diagnostics)`` 调用。

    首参是**单个节点**（签名如此），所以这里按 id 取出来传。
    """
    by_id = {node["id"]: node for node in nodes}
    return call("explainNode", by_id[node_id], edges, by_id, graph_status,
                diagnostics or {})


def test_explain_failed_uses_own_reason():
    nodes = [{"id": "a", "kind": "subagent", "status": "failed",
              "reason": "RuntimeError: model exploded"}]
    why = _explain("a", nodes, [])
    assert "RuntimeError" in why


def test_explain_blocked_names_the_blocking_upstream():
    nodes = [
        {"id": "a", "kind": "subagent", "status": "failed", "reason": "boom"},
        {"id": "b", "kind": "subagent", "status": "blocked"},
    ]
    why = _explain("b", nodes, [_edge("a", "b", status="blocked")])
    assert "a" in why


def test_explain_blocked_walks_through_blocked_upstreams():
    """G12 修正：``blocked`` 常是**整条链**一起 blocked，只扫 failed 一无所获。"""
    nodes = [
        {"id": "s", "kind": "subagent", "status": "blocked"},
        {"id": "mid", "kind": "subagent", "status": "blocked"},
        {"id": "t", "kind": "subagent", "status": "blocked"},
    ]
    why = _explain("t", nodes, [_edge("s", "mid"), _edge("mid", "t")])
    assert "s" in why, f"没有穿透 blocked 上游找到真正的源头：{why}"


def test_explain_blocked_prefers_graph_level_stop_reason():
    """D2 修正：图级停止原因**优先**于沿边扫描（签名扩了才会看到图级 status）。"""
    nodes = [{"id": "t", "kind": "subagent", "status": "blocked"}]
    why = _explain("t", nodes, [], graph_status="budget_exceeded")
    assert "预算" in why or "budget" in why.lower()


def test_explain_budget_exceeded_includes_numbers_from_graph_budget():
    """G13：用户看到「预算超限」的下一个动作必然是「花了多少」。"""
    nodes = [{"id": "t", "kind": "subagent", "status": "budget_exceeded",
              "reason": "budget exceeded (tokens)"}]
    budget = {"exceeded_dimension": "tokens",
              "dimensions": {"tokens": {"limit": 100000, "used": 152300}}}
    why = _explain("t", nodes, [], graph_status="budget_exceeded",
                   diagnostics={"budget": budget})
    assert "100" in why and "152" in why


def test_explain_blocked_falls_back_when_nothing_upstream():
    nodes = [{"id": "t", "kind": "subagent", "status": "blocked", "reason": "some reason"}]
    assert _explain("t", nodes, [])


def test_explain_returns_null_for_normal_statuses():
    """正常态不占位（D2：``why`` 小字只在异常态出现）。"""
    nodes = [{"id": "a", "kind": "subagent", "status": "completed"}]
    assert _explain("a", nodes, []) is None


# --- M2.11：并行边等距偏移 --------------------------------------------------


def test_parallel_edges_are_spread_apart():
    """D7：同一对节点 3 条边——不偏移时三条路径**逐字相同**，画出来只有一条线。"""
    nodes = _nodes(("a", "subagent", "completed"), ("b", "subagent", "completed"))
    edges = [
        _edge("a", "b", status="passed", channel="summary"),
        _edge("a", "b", status="passed", channel="result_ref"),
        _edge("a", "b", status="passed", channel="artifact"),
    ]
    layout = call("layoutGraph", nodes, edges, {"orientation": "horizontal"})
    paths = [edge["path"] for edge in layout["edges"]]
    assert len(set(paths)) == 3, f"并行边仍然重合：{paths}"


def test_single_edge_between_pair_is_not_offset():
    """只有一条边时不偏移——偏移是「重合」的解药，不是常态。"""
    nodes = _nodes(("a", "subagent", "completed"), ("b", "subagent", "completed"))
    edges = [_edge("a", "b", status="passed")]
    with_offset = call("layoutGraph", nodes, edges, {"orientation": "horizontal"})
    plain = call("edgePath", with_offset["nodes"][0], with_offset["nodes"][1], "horizontal")
    assert with_offset["edges"][0]["path"] == plain


def test_parallel_edge_offsets_are_symmetric_around_the_midline():
    """偏移对称铺开（igraph ``curve_multiple``）：n 条边的偏移和为 0。"""
    nodes = _nodes(("a", "subagent", "completed"), ("b", "subagent", "completed"))
    edges = [
        _edge("a", "b", channel="summary"),
        _edge("a", "b", channel="result_ref"),
        _edge("a", "b", channel="artifact"),
    ]
    layout = call("layoutGraph", nodes, edges, {"orientation": "horizontal"})
    offsets = [edge["offset"] for edge in layout["edges"]]
    assert abs(sum(offsets)) < 1e-6, offsets
    assert len(set(offsets)) == 3


def test_edge_path_accepts_offset_parameter_backwards_compatibly():
    """``edgePath`` 是对外导出的 API：加**可选**参数，旧签名继续可用。"""
    a = {"x": 0, "y": 0, "width": 168, "height": 58}
    b = {"x": 264, "y": 0, "width": 168, "height": 58}
    plain = call("edgePath", a, b, "horizontal")
    shifted = call("edgePath", a, b, "horizontal", 9)
    assert plain.startswith("M ") and shifted.startswith("M ")
    assert plain != shifted


def test_parallel_offsets_stay_finite_for_many_edges():
    """极端情况（同对 10+ 条边）不得产生 NaN 或越界。"""
    nodes = _nodes(("a", "subagent", "completed"), ("b", "subagent", "completed"))
    edges = [_edge("a", "b", channel="summary") for _ in range(12)]
    layout = call("layoutGraph", nodes, edges, {"orientation": "vertical"})
    for edge in layout["edges"]:
        assert "NaN" not in edge["path"]
        assert "undefined" not in edge["path"]


# --- M2.11：边统计口径 ------------------------------------------------------


def test_edge_count_line_omits_explanation_when_numbers_match():
    """D7：一致就不解释——小图（<50 节点）根本不会发生折叠去重。"""
    assert call("edgeCountLabel", 6, 6) == "6 paths"


def test_edge_count_line_explains_when_numbers_differ():
    """不一致时才给可解释口径，且**不写死**「含并行边/折叠合并」这种断言。"""
    label = call("edgeCountLabel", 6, 11)
    assert "6" in label and "11" in label
    assert "path" in label and "edge" in label


# --- M2.11：多图 tab 的编号与排序（Q3 = A） ---------------------------------


def _graph_entry(wid, status, started_at, finished_at=None):
    return {"id": wid, "status": status, "started_at": started_at,
            "finished_at": finished_at}


def test_graph_ranks_follow_started_at_order():
    """Q3 选项 A：``#N`` = 按 ``started_at`` 排序的秩。"""
    ranked = call("rankGraphs", [
        _graph_entry("wf3", "completed", 300.0),
        _graph_entry("wf1", "started", 100.0),
        _graph_entry("wf2", "completed", 200.0),
    ])
    assert [entry["id"] for entry in ranked] == ["wf1", "wf2", "wf3"]
    assert [entry["rank"] for entry in ranked] == [1, 2, 3]


def test_graph_order_is_by_rank_not_by_status():
    """Q3 = A 的代价：不再「运行中排最前」——编号与空间顺序必须一致。"""
    ranked = call("rankGraphs", [
        _graph_entry("wf1", "started", 100.0),
        _graph_entry("wf2", "completed", 200.0),
        _graph_entry("wf3", "completed", 300.0),
    ])
    assert [entry["id"] for entry in ranked] == ["wf1", "wf2", "wf3"]


def test_graphs_without_started_at_sort_last():
    """D3 的哨兵统一成 ``null``：不能把它当 epoch 0 排到最前。"""
    ranked = call("rankGraphs", [
        _graph_entry("declared", "declared", None),
        _graph_entry("wf1", "completed", 100.0),
    ])
    assert [entry["id"] for entry in ranked] == ["wf1", "declared"]
    assert ranked[1]["rank"] == 2


def test_graph_tab_meta_formats_number_relative_time_and_progress():
    """D6：``#N · 相对时间 · 耗时 · M/N``（M/N 由前端从 nodes 自算）。"""
    meta = call("graphTabMeta",
                {"id": "wf1", "status": "completed", "started_at": 100.0,
                 "finished_at": 238.0},
                3, 1238.0, {"completed": 5, "failed": 0, "running": 0, "total": 5})
    assert meta["rank"] == 3
    assert meta["duration"] == "2m18s"
    assert meta["relative"] == "16 分钟前"
    assert meta["progress"] == "5/5"


def test_graph_tab_meta_running_shows_ticking_elapsed():
    """D6：运行中显示「已跑 42s」并实时跳秒——相对时间在这里没有意义。"""
    meta = call("graphTabMeta",
                {"id": "wf1", "status": "started", "started_at": 1000.0,
                 "finished_at": None},
                1, 1042.0, {"completed": 2, "failed": 0, "running": 1, "total": 5})
    assert meta["relative"] == "已跑 42s"
    assert meta["duration"] == "42s"


def test_graph_tab_meta_is_safe_without_timestamps():
    """``declared`` 态没有任何时间：不得渲染成 epoch 0 或 NaN。"""
    meta = call("graphTabMeta", {"id": "wf1", "status": "declared"}, 1, 1000.0, None)
    assert "NaN" not in json.dumps(meta)
    assert meta["duration"] in ("", "—")
    assert meta["progress"] == ""


def test_graph_progress_counts_nodes_not_logical_units():
    """D6 口径：``M/N`` 由前端从 ``snapshot.nodes`` 自算，**不用**快照的
    ``total/completed/failed``（那是逻辑单元口径，foreach 容器按 N+1 计，
    且 running 帧根本不带）。"""
    nodes = [
        {"id": "a", "status": "completed"},
        {"id": "fan", "status": "completed", "items": 12},
        {"id": "b", "status": "failed"},
    ]
    progress = call("nodeProgress", nodes)
    assert progress == {"completed": 2, "failed": 1, "running": 0, "total": 3}
    assert call("progressLabel", progress) == "2/3"


def test_graph_progress_is_available_mid_flight():
    """running 帧也要能算出来（快照的 total/completed/failed 在 running 时缺席）。"""
    nodes = [{"id": "a", "status": "completed"}, {"id": "b", "status": "started"}]
    assert call("progressLabel", call("nodeProgress", nodes)) == "1/2"


# --- M2.7：图级状态走独立词表 ----------------------------------------------


def test_graph_status_colors_are_a_separate_table():
    """D10：图级 status 不得塞进 ``NODE_COLORS``——后者有精确相等契约测试。"""
    graph_colors = call("graphStatusColors")
    node_colors = call("nodeColors")
    assert "completed_with_failures" in graph_colors
    assert "graph_recursion_exceeded" in graph_colors
    assert "running" not in node_colors
    assert "completed_with_failures" not in node_colors


def test_graph_status_label_covers_completed_with_failures():
    """G26 的图级终态必须有可读标签，不能显示裸字符串。"""
    assert call("graphStatusLabel", "completed_with_failures") != "completed_with_failures"
    assert call("graphStatusLabel", "graph_recursion_exceeded") != "graph_recursion_exceeded"


def test_graph_notice_carries_current_nodes_and_steps():
    """G14：超限那刻的 ready 节点 = 回边死循环的直接答案，不能丢。"""
    notice = call("graphNotice", {
        "status": "graph_recursion_exceeded",
        "diagnostics": {"reason": "max_nodes", "recursion_limit": 27,
                        "message": "too big", "steps": 11,
                        "current_nodes": ["gate", "work"]},
    })
    assert notice["steps"] == 11
    assert notice["current_nodes"] == ["gate", "work"]
    assert "gate" in notice["message"]


# --- M2.10：elapsed / 陈旧度 ------------------------------------------------


def test_format_elapsed_is_compact_and_stable():
    assert call("formatElapsed", 42) == "42s"
    assert call("formatElapsed", 138) == "2m18s"
    assert call("formatElapsed", 3600) == "1h0m"


def test_format_age_distinguishes_slow_from_dead():
    """G8：图卡住时用户要能区分「慢」与「死」。"""
    assert call("formatAge", 5) == "5 秒前"
    assert call("formatAge", 120) == "2 分钟前"


# --- M2.7：超限仍画图 -------------------------------------------------------


def test_graph_recursion_exceeded_is_terminal_for_pruning():
    """D9(d)：两个终态列表漏一个，那张图就被当成 running——永不淘汰、永久排最前。"""
    import re

    source = (Path(__file__).parents[2] / "web" / "static" / "workflow.js").read_text()
    match = re.search(r"const TERMINAL_STATUSES = \[(.*?)\];", source, re.S)
    assert match, "TERMINAL_STATUSES 不在 workflow.js 里了"
    assert "completed_with_failures" in match.group(1)
    assert "graph_recursion_exceeded" in match.group(1)


def test_node_progress_and_tab_meta_share_the_same_progress_shape():
    """``graphTabMeta`` 的 ``progress`` 直接来自 ``progressLabel(nodeProgress(...))``。"""
    nodes = [{"id": "a", "status": "completed"}]
    progress = call("nodeProgress", nodes)
    meta = call("graphTabMeta", {"id": "wf", "status": "completed",
                                 "started_at": 0.0, "finished_at": 1.0}, 1, 1.0, progress)
    assert meta["progress"] == call("progressLabel", progress)


# --- M3.8：「对话」tab 的刷新节律（定死，不是「取一次就完」） --------------


def test_transcript_refreshes_on_a_pinned_cadence():
    """design D4 要求刷新节律**定死**：既不是打开取一次就完，也不是每个快照重排。

    窗口值只由纯函数自己判——测试不复制那个数字，否则改节律要改两处。
    """
    running = {"id": "a", "status": "started"}
    # 刚取过 → 不重取（不能每个快照/每一 tick 都重排）。
    assert call("transcriptRefreshDue", running,
                {"paused": False, "lastFetchedAt": 1000.0, "now": 1000.0}) is False
    assert call("transcriptRefreshDue", running,
                {"paused": False, "lastFetchedAt": 1000.0, "now": 1000.5}) is False
    # 隔了一分钟 → 一定该重取（节律是有限的，不会「永不更新」）。
    assert call("transcriptRefreshDue", running,
                {"paused": False, "lastFetchedAt": 1000.0, "now": 1060.0}) is True
    # 从没取过 → 立即取。
    assert call("transcriptRefreshDue", running,
                {"paused": False, "lastFetchedAt": None, "now": 1000.0}) is True


def test_transcript_refresh_stops_for_terminal_nodes():
    """节点已终态 → 不会再有新消息，轮询是纯浪费。"""
    for status in ("completed", "failed", "cancelled", "blocked",
                   "budget_exceeded", "skipped"):
        assert call("transcriptRefreshDue", {"id": "a", "status": status},
                    {"paused": False, "lastFetchedAt": 0.0, "now": 99999.0}) is False


def test_transcript_refresh_stops_while_paused():
    """暂停按钮停的就是这条定时器——暂停是**有效**的（不是装饰）。"""
    assert call("transcriptRefreshDue", {"id": "a", "status": "started"},
                {"paused": True, "lastFetchedAt": 0.0, "now": 99999.0}) is False


# --- 失败证据的前端纯函数层（change fix-issue-215，Q6 方案 D） ----------------


def test_failure_evidence_text_covers_every_backend_state():
    """后端 ``FAILURE_EVIDENCE_STATES`` 的**每一个**取值都要有前端文案。

    这条是「前端版本落后于后端」的机械防线：后端加一个新 state 而前端没跟上时，
    用户看到的会是空白——而空白会被读成「没问题」，正是本 change 要消灭的误读。
    """
    from web.session import FAILURE_EVIDENCE_STATES

    texts = call("failureEvidenceTexts")
    missing = sorted(set(FAILURE_EVIDENCE_STATES) - set(texts))
    assert not missing, f"后端有、前端没有文案的 state：{missing}"
    for state in FAILURE_EVIDENCE_STATES:
        assert texts[state].strip(), f"{state} 缺文案"
    # 七态文案互不相同——串台会让用户读到与自己处境相反的结论。
    assert len(set(texts.values())) == len(texts)


def test_failure_evidence_text_degrades_readably_for_unknown_state():
    """未知 state 必须给可读降级，不能返回空串/undefined。"""
    for unknown in ("brand_new_state", "", "PRESENT", None):
        text = call("failureEvidenceText", unknown)
        assert isinstance(text, str) and text.strip(), f"{unknown!r} 降级成了空"
    assert call("failureEvidenceText", "present") == call("failureEvidenceTexts")["present"]


def test_failure_count_hint_wording_covers_llm_errors_too():
    """线索措辞必须覆盖**两种**失败口径。

    计数口径（`count_failures`）是「工具失败 + LLM 错误」，只写「工具失败」会在
    run 因 LLM 调用失败而红时把用户带去查工具（review R4 低 1：端到端实测一个工具
    都没失败、只有 `llm_error`，而抽屉默认 tab 说「工具失败」）。兄弟出口
    （`workflow_transcript.js` 的候选行）已用准确措辞，这里跟它对齐。
    """
    for count in (1, 3):
        hint = call("failureCountHint", count)
        assert "工具/LLM 失败" in hint, f"{count} 条的线索措辞没覆盖 LLM 错误：{hint!r}"


def test_failure_count_hint_separates_no_data_from_zero():
    """「任务」tab 的一行线索：``None`` 不显示、``0`` 显示正向声明、``N`` 显示计数。

    变异点：把 ``None`` 与 ``0`` 折叠成同一句 → 本条必须变红（折叠后用户会重新落回
    「没显示 = 没事」的旧误读，而 ``0`` 恰恰是「系统检查过」的证据）。
    """
    assert call("failureCountHint", None) is None, "没有数据 → 不显示"
    assert call("failureCountHint", 0) == "已检查、无失败。"
    assert call("failureCountHint", 1).startswith("⚠") and "1 次" in call("failureCountHint", 1)
    assert "3 次" in call("failureCountHint", 3)
    assert call("failureCountHint", 0) != call("failureCountHint", None)


def test_failure_item_summary_shows_tool_step_and_error_type():
    """条目摘要至少含工具名、步序、错误类型——那是「哪个工具失败了」的答案。"""
    summary = call("failureItemSummary", {
        "type": "tool_result", "step": 7, "tool_name": "Bash",
        "status": "error", "error_type": "tool_error",
        "observation": "3 failed, 12 passed\nmore lines", "text_truncated": False,
    })
    assert "Bash" in summary and "7" in summary and "tool_error" in summary
    assert "3 failed" in summary
    assert "\n" not in summary, "摘要必须是单行"


def test_failure_item_summary_handles_llm_error_and_truncation():
    """``llm_error`` 条目的文本在 ``message`` 上（没有 ``tool_name``/``observation``）——
    摘要不得因此变成空串；被截断时必须显式标注，否则用户以为正文就这么短。"""
    summary = call("failureItemSummary", {
        "type": "llm_error", "step": 9, "tool_name": None, "status": "error",
        "error_type": "network_timeout", "message": "upstream timed out",
        "text_truncated": True,
    })
    assert "network_timeout" in summary and "upstream timed out" in summary
    assert "已截断" in summary, "截断必须显式标注"

    empty = call("failureItemSummary", {"type": "llm_error", "step": 2})
    assert isinstance(empty, str), "缺字段不得返回 undefined"

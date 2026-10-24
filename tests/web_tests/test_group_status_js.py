# tests/web_tests/test_group_status_js.py
"""群聊成员状态纯函数（web/static/group_status.js）的 node + vm 单测。

复用 ``test_workflow_graph_js.py`` 的先例：前端纯函数与 DOM 解耦，在 CI 里真跑。
"""
import json
import subprocess
from pathlib import Path

import pytest

STATUS_JS = Path(__file__).parents[2] / "web" / "static" / "group_status.js"

_HARNESS = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const calls = JSON.parse(process.argv[2]);
const context = { window: {} };
vm.createContext(context);
vm.runInContext(source, context);
const api = context.window.AsterwyndGroupStatus;
const out = calls.map(([name, argv]) => api[name](...argv));
process.stdout.write(JSON.stringify(out));
"""


def call_many(*calls):
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(STATUS_JS), json.dumps([list(c) for c in calls])],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def call(name, *args):
    return call_many((name, list(args)))[0]


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node unavailable")


def _status(pid, phase, tools=None, count=None):
    return {
        "persona_id": pid,
        "phase": phase,
        "tools": tools or [],
        "tool_count": count if count is not None else len(tools or []),
    }


def test_status_event_replaces_whole_table_and_drops_stale_seq():
    state = {"statuses": {}, "seq": 5}
    newer = call("applyStatusEvent", state, {
        "status_seq": 6,
        "statuses": [_status("a", "thinking"), _status("b", "tool", ["Bash"])],
    })
    assert newer["applied"] is True
    assert newer["state"]["seq"] == 6
    assert newer["state"]["statuses"]["b"]["phase"] == "tool"
    assert newer["state"]["statuses"]["b"]["tools"] == ["Bash"]

    stale = call("applyStatusEvent", newer["state"], {
        "status_seq": 6,
        "statuses": [_status("a", "idle")],
    })
    assert stale["applied"] is False
    assert stale["state"]["statuses"]["a"]["phase"] == "thinking"


def test_terminal_removes_member_and_round_end_clears_all():
    state = {"statuses": {
        "a": _status("a", "thinking"), "b": _status("b", "typing"),
    }, "seq": 10}
    one = call("applyTerminal", state, {
        "persona_id": "a", "status_seq": 11,
    })
    assert one["applied"] is True
    assert "a" not in one["state"]["statuses"]
    assert "b" in one["state"]["statuses"]

    ended = call("applyTerminal", one["state"], {
        "termination": "completed", "status_seq": 12,
    })
    assert ended["applied"] is True
    assert ended["clearedAll"] is True
    assert ended["state"]["statuses"] == {}

    stale = call("applyTerminal", ended["state"], {
        "persona_id": "a", "status_seq": 11,
    })
    assert stale["applied"] is False
    assert stale["state"]["statuses"] == {}


def test_snapshot_resets_watermark_even_when_seq_is_smaller():
    state = {"statuses": {"a": _status("a", "tool", ["Bash"])}, "seq": 42}
    snap = call("applySnapshot", state, {
        "member_statuses": [_status("b", "thinking")],
        "status_seq": 0,
        "round_active": True,
    })
    assert snap["state"]["seq"] == 0
    assert snap["state"]["statuses"]["b"]["phase"] == "thinking"
    assert "a" not in snap["state"]["statuses"]

    idle = call("applySnapshot", state, {
        "member_statuses": [_status("a", "thinking")],
        "status_seq": 3,
        "round_active": False,
    })
    assert idle["state"]["statuses"] == {}
    assert idle["state"]["seq"] == 3


def test_speaking_fallback_only_raises_idle_and_respects_seq():
    state = {"statuses": {"a": _status("a", "thinking")}, "seq": 4}
    no_downgrade = call("applySpeakingFallback", state, {
        "persona_id": "a", "status_seq": 4,
    })
    assert no_downgrade["changed"] is False

    raised = call("applySpeakingFallback", state, {
        "persona_id": "b", "status_seq": 5,
    })
    assert raised["changed"] is True
    assert raised["state"]["statuses"]["b"]["phase"] == "running"

    stale = call("applySpeakingFallback", state, {
        "persona_id": "b", "status_seq": 3,
    })
    assert stale["changed"] is False


def test_format_phase_labels_and_tool_names():
    assert call("formatPhase", "idle", [], 0) == "空闲"
    assert call("formatPhase", "running", [], 0) == "运行中"
    assert call("formatPhase", "thinking", [], 0) == "正在思考"
    assert call("formatPhase", "typing", [], 0) == "正在输入"
    assert call("formatPhase", "tool", ["Bash"], 1) == "正在使用工具 · Bash"
    assert call("formatPhase", "tool", ["Bash", "Read"], 2) == "正在使用工具 · Bash、Read（2 个）"
    assert call("formatPhase", "tool", ["Bash"], 2) == "正在使用工具 · Bash（2 个）"


def test_describe_change_returns_one_line():
    before = {"statuses": {"a": _status("a", "thinking")}, "seq": 1}
    after = {"statuses": {"a": _status("a", "typing")}, "seq": 2}
    text = call("describeChange", before, after, {"a": "甲"})
    assert text == "甲 正在输入"

    same = call("describeChange", before, before, {"a": "甲"})
    assert same is None


def test_merge_timeline_keeps_newer_entries_and_server_wins_same_seq():
    current = [
        {"seq": 1, "text": "old"},
        {"seq": 3, "text": "arrived-during-fetch"},
    ]
    incoming = [
        {"seq": 1, "text": "server-authoritative"},
        {"seq": 2, "text": "server-entry"},
    ]
    merged = call("mergeTimeline", current, incoming)
    assert [entry["seq"] for entry in merged] == [1, 2, 3]
    assert merged[0]["text"] == "server-authoritative"
    assert merged[2]["text"] == "arrived-during-fetch"


def test_merge_timeline_ignores_client_only_null_seq_entries():
    merged = call("mergeTimeline", [{"seq": None, "text": "synthetic"}],
                  [{"seq": 1, "text": "server"}])
    assert merged == [{"seq": 1, "text": "server"}]


# ---------------------------------------------------------------- 讨论链
# change group-unlimited-discussion（design Decision 7 / web-ui spec delta）：
# describeRoundEnd / describeDiscussionEnd / shouldShowStop / shouldApplyChainEvent。


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("converged", "讨论已收敛"),
        ("stopped", "讨论已停止"),
        ("max_rounds", "讨论达安全上限"),
        ("max_turns", "讨论达安全上限"),
        ("max_seconds", "讨论达安全上限"),
        ("all_failed", "讨论已中止（本轮无人发言，存在失败）"),
        ("mode_changed", "讨论已结束（模式已变更）"),
        ("cancelled", "讨论已中止"),
        ("error", "讨论异常结束"),
        ("round_limit", "讨论因本轮达上限结束"),
        ("completed", "讨论已结束"),
    ],
)
def test_describe_discussion_end_maps_every_reason(reason, expected):
    assert call("describeDiscussionEnd", reason) == expected


def test_describe_discussion_end_unknown_reason_is_none():
    assert call("describeDiscussionEnd", "bogus") is None
    assert call("describeDiscussionEnd", None) is None
    assert call("describeDiscussionEnd", "") is None


def test_describe_round_end_single_keeps_existing_four_labels():
    # single 的 round_ended 四键不变、零行为变化：既有四档文案逐字保持。
    assert call("describeRoundEnd", {"termination": "completed"}) == "本轮结束"
    assert call("describeRoundEnd", {"termination": "all_failed"}) == "本轮结束"
    assert call("describeRoundEnd", {"termination": "limit"}) == "本轮因达上限结束"
    assert call("describeRoundEnd", {"termination": "cancelled"}) == "本轮已中止"
    assert call("describeRoundEnd", {"termination": "error"}) == "本轮异常结束"


def test_describe_round_end_unlimited_stopped_is_discussion_stopped():
    text = call("describeRoundEnd", {
        "termination": "stopped", "chain_id": "room:1", "round_index": 3,
        "chain_continues": False,
    })
    assert text == "讨论已停止"
    assert "本轮结束" not in text


def test_describe_round_end_chain_continues_shows_next_round_not_round_end():
    text = call("describeRoundEnd", {
        "termination": "completed", "chain_id": "room:1", "round_index": 1,
        "chain_continues": True,
    })
    assert text == "讨论中（第 2 轮）"
    assert "本轮结束" not in text
    # 只带 chain_continues 也认链（旧服务端字段的兼容路径）。
    assert call("describeRoundEnd", {
        "termination": "completed", "round_index": 2, "chain_continues": True,
    }) == "讨论中（第 3 轮）"


def test_describe_round_end_chain_terminal_defers_to_discussion_ended():
    # 链即将结束但还不是终态：不抢文案，等 discussion_ended 给终态文案。
    assert call("describeRoundEnd", {
        "termination": "completed", "chain_id": "room:1", "round_index": 2,
        "chain_continues": False,
    }) is None
    assert call("describeRoundEnd", {
        "termination": "limit", "chain_id": "room:1", "round_index": 2,
        "chain_continues": False,
    }) is None
    # 取消/异常链的 teardown 投递是尽力而为：先给中止提示，避免状态悬空。
    assert call("describeRoundEnd", {
        "termination": "cancelled", "chain_id": "room:1", "round_index": 2,
        "chain_continues": False,
    }) == "讨论已中止"
    assert call("describeRoundEnd", {
        "termination": "error", "chain_id": "room:1", "round_index": 2,
        "chain_continues": False,
    }) == "讨论异常结束"


def test_should_show_stop_only_for_unlimited_active_round():
    unlimited = {"round_active": True, "room": {"discussion_mode": "unlimited"}}
    assert call("shouldShowStop", unlimited) is True
    assert call("shouldShowStop", {
        "round_active": False, "room": {"discussion_mode": "unlimited"},
    }) is False
    assert call("shouldShowStop", {
        "round_active": True, "room": {"discussion_mode": "single"},
    }) is False
    assert call("shouldShowStop", {"round_active": True, "room": {}}) is False
    assert call("shouldShowStop", {"round_active": True}) is False
    assert call("shouldShowStop", {}) is False


def test_should_apply_chain_event_guards_stale_chain():
    payload = {"chain_id": "room:2", "termination": "stopped"}
    assert call("shouldApplyChainEvent", "room:2", payload) is True
    # 迟到的旧链终态：chain_id 不一致 → 丢弃，不得覆盖新链状态。
    assert call("shouldApplyChainEvent", "room:1", payload) is False
    # 事件不带 chain_id（single / 旧服务端 payload）→ 兼容应用。
    assert call("shouldApplyChainEvent", "room:1", {"termination": "completed"}) is True
    assert call("shouldApplyChainEvent", "room:1", {"chain_id": None}) is True
    # 当前链未知（刷新/重连/错过 discussion_started）→ 接受并由事件认链。
    assert call("shouldApplyChainEvent", None, payload) is True
    assert call("shouldApplyChainEvent", "", payload) is True

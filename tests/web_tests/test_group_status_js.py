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

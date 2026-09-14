"""workflow store：result_ref 落盘 / 读取 / 事件日志（tasks 1.1、5.1、5.2）。

覆盖 grill 决策 1/2/3：

- **独立 subtree**（grill 决策 1）：结果落在 ``.asterwynd/workflows/<workflow_id>/``，
  与 ``SubagentSnapshotStore`` 的 ``.asterwynd/subagents/`` 命名空间完全分离——
  清理 checkpoint 的 ``rmtree`` 不会连结果一起删。
- **无 dedup skip**（grill 决策 1）：同内容重复写仍然是真实写盘，第二次读得到文件
  （``SessionStore.save()`` 的 dedup 会让第二次写变成 no-op）。
- **原子写 + 每 key 独立文件**：并发写不互相截断。
- **跨进程可解析**（Q9/5.2）：新 store 实例 / 子进程按 ref 读回正文。
- ref 解析必须拒绝越界路径（``..`` 逃逸）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent.run_config import AgentMode
from agent.session import SessionSnapshot
from agent.subagent.snapshot import SubagentSnapshotStore
from agent.subagent.workflow_store import (
    DEFAULT_READ_LIMIT,
    MAX_READ_LIMIT,
    RESULT_REF_PREFIX,
    WorkflowStore,
)


@pytest.fixture
def store(tmp_path) -> WorkflowStore:
    return WorkflowStore.for_workspace(tmp_path, "wf_test1")


# --- 1.1 独立 subtree + ref 格式 --------------------------------------------


def test_store_lives_in_independent_subtree(tmp_path):
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    ref = store.save_result("run_a", "full result")
    assert ref == f"{RESULT_REF_PREFIX}wf_test1/run_a"
    path = store.path_for(ref)
    assert path.is_file()
    # 独立 subtree：不在 .asterwynd/subagents 下
    assert ".asterwynd/workflows/wf_test1" in str(path)
    assert ".asterwynd/subagents" not in str(path)
    assert path.read_text(encoding="utf-8") == "full result"


def test_snapshot_store_remove_does_not_delete_results(tmp_path):
    """grill 决策 1 的核心回归：checkpoint 清理（rmtree 整个 run 目录）不能删结果。"""
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    ref = store.save_result("run_a", "keep me")
    snapshot_store = SubagentSnapshotStore.for_workspace(tmp_path)
    snapshot_store.save(
        SessionSnapshot(
            schema_version="1.0",
            session_id="run_a",
            created_at="",
            updated_at="",
            messages=[],
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_a",
            iteration=1,
        )
    )
    assert snapshot_store.remove("run_a") is True
    assert store.load(ref) == "keep me"


def test_repeated_identical_write_is_not_deduped(tmp_path):
    """SessionStore 的 dedup 会把第二次同内容写变成 no-op；workflow store 不行。"""
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    first = store.save_result("run_a", "same text")
    store.path_for(first).unlink()
    second = store.save_result("run_a", "same text")
    assert second == first
    assert store.load(second) == "same text"


def test_each_key_gets_its_own_file(tmp_path):
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    a = store.save_result("run_a", "a")
    b = store.save_result("run_b", "b")
    assert store.path_for(a) != store.path_for(b)
    assert (store.load(a), store.load(b)) == ("a", "b")


def test_load_missing_ref_returns_none(store):
    assert store.load(f"{RESULT_REF_PREFIX}wf_test1/absent") is None


def test_result_ref_prefix_round_trips(store):
    ref = store.save_result("run_a", "x")
    workflow_id, key = WorkflowStore.parse_ref(ref)
    assert (workflow_id, key) == ("wf_test1", "run_a")


def test_parse_ref_rejects_foreign_and_traversing_refs(store):
    for bad in (
        "artifact://workflow/../etc/passwd",
        "artifact://workflow/wf_test1/../../escape",
        "artifact://subagent/wf_test1/run_a",
        "/etc/passwd",
        "artifact://workflow/wf_test1",
        "artifact://workflow//run_a",
        "",
    ):
        with pytest.raises(ValueError):
            WorkflowStore.parse_ref(bad)


# --- 1.1 分页读取 -----------------------------------------------------------


def test_read_paginates_result_text(store):
    body = "".join(f"{i:04d}\n" for i in range(100))  # 500 chars
    ref = store.save_result("run_a", body)
    page = store.read(ref, offset=0, limit=50)
    assert page["ref"] == ref
    assert page["offset"] == 0
    assert page["total_chars"] == len(body)
    assert page["content"] == body[:50]
    assert page["truncated"] is True

    tail = store.read(ref, offset=len(body) - 10, limit=50)
    assert tail["content"] == body[-10:]
    assert tail["truncated"] is False


def test_read_defaults_and_clamps_limit(store):
    body = "x" * (MAX_READ_LIMIT + 100)
    ref = store.save_result("run_a", body)
    default_page = store.read(ref)
    assert len(default_page["content"]) == DEFAULT_READ_LIMIT
    clamped = store.read(ref, limit=MAX_READ_LIMIT * 10)
    assert len(clamped["content"]) == MAX_READ_LIMIT


def test_read_unknown_ref_reports_missing(store):
    page = store.read(f"{RESULT_REF_PREFIX}wf_test1/nope")
    assert page["content"] == ""
    assert page["total_chars"] == 0
    assert page["missing"] is True


# --- 1.1 事件日志（D4 权威事件源） ------------------------------------------


def test_event_log_round_trips_and_appends(store):
    store.append_event({"type": "node_terminal", "node_id": "a", "status": "completed"})
    store.append_event({"type": "workflow_terminal", "status": "completed"})
    events = store.read_events()
    assert [event["type"] for event in events] == ["node_terminal", "workflow_terminal"]
    assert events[0]["node_id"] == "a"


def test_event_log_survives_new_store_instance(tmp_path):
    WorkflowStore.for_workspace(tmp_path, "wf_test1").append_event({"type": "t", "n": 1})
    fresh = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    assert [event["type"] for event in fresh.read_events()] == ["t"]


def test_read_events_on_empty_store_is_empty_list(store):
    assert store.read_events() == []


# --- 5.2 跨进程可解析 -------------------------------------------------------


def test_result_ref_resolves_across_processes(tmp_path):
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    ref = store.save_result("run_a", "cross-process payload")
    script = (
        "import json, sys\n"
        "from agent.subagent.workflow_store import WorkflowStore\n"
        "store = WorkflowStore.for_workspace(sys.argv[1], 'wf_test1')\n"
        "print(json.dumps(store.read(sys.argv[2])))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), ref],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["content"] == "cross-process payload"
    assert payload["missing"] is False


def test_for_workspace_isolates_workflow_ids(tmp_path):
    one = WorkflowStore.for_workspace(tmp_path, "wf_one")
    two = WorkflowStore.for_workspace(tmp_path, "wf_two")
    ref_one = one.save_result("run_a", "one")
    assert two.load(ref_one.replace("wf_one", "wf_two")) is None
    assert one.load(ref_one) == "one"

"""Agent 通用 artifact 存储（change ``tool-result-lifecycle``，D4）。

覆盖：ref 格式族与段级校验、作用域隔离（agent 不认 workflow ref，反之亦然）、
原子写 / 分页读、{根 session_id / 子 run_id} 寻址、显式清理、resume 后仍可解析。
"""
import pytest

from agent.artifact_store import (
    AGENT_REF_PREFIX,
    RESULT_REF_PREFIX,
    AgentArtifactStore,
    ArtifactRef,
    artifacts_root,
    extract_result_ref,
)
from agent.subagent.workflow_store import WorkflowStore


def test_agent_ref_round_trip(tmp_path):
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    ref = store.save_result("result-1", "hello world")
    assert ref == f"{AGENT_REF_PREFIX}s-abc/result-1"
    assert store.load(ref) == "hello world"


def test_agent_store_falls_outside_sessions_dir(tmp_path):
    """D4：artifacts 必须在 ``sessions/<id>/`` 之外（``SessionStore.remove`` 是 rmtree）。"""
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    ref = store.save_result("k", "body")
    path = store.path_for(ref)
    assert ".asterwynd" in path.parts
    assert "artifacts" in path.parts
    assert "sessions" not in path.parts


def test_agent_artifact_paged_read(tmp_path):
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    body = "x" * 100
    ref = store.save_result("k", body)
    page = store.read(ref, offset=0, limit=10)
    assert page["content"] == "x" * 10
    assert page["total_chars"] == 100
    assert page["truncated"] is True
    tail = store.read(ref, offset=90, limit=10)
    assert tail["content"] == "x" * 10
    assert tail["truncated"] is False


def test_agent_artifact_missing_self_describes(tmp_path):
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    page = store.read(f"{AGENT_REF_PREFIX}s-abc/absent")
    assert page["missing"] is True
    assert page["content"] == ""


def test_agent_store_rejects_foreign_and_malformed_refs(tmp_path):
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    bad = [
        f"{AGENT_REF_PREFIX}other/key",          # 别的作用域
        f"{RESULT_REF_PREFIX}wf/key",            # workflow 前缀（不是 agent）
        "artifact://agent/../leak",              # 段级逃逸
        "artifact://agent/s-abc/../x",           # 段级逃逸（key）
        f"{AGENT_REF_PREFIX}s-abc/",             # 少了 key
        "not-a-ref",
    ]
    for ref in bad:
        with pytest.raises(ValueError):
            store.path_for(ref)
        assert store.load(ref) is None  # load 吞掉 ValueError 返回 None


def test_workflow_store_still_rejects_agent_refs(tmp_path):
    """泛化不能松掉 workflow store 的作用域校验。"""
    store = WorkflowStore.for_workspace(tmp_path, "wf_test1")
    with pytest.raises(ValueError):
        store.path_for(f"{AGENT_REF_PREFIX}s-abc/x")
    assert store.load(f"{AGENT_REF_PREFIX}s-abc/x") is None


def test_shared_artifact_ref_parse_routes_both_kinds():
    wf = ArtifactRef.parse("artifact://workflow/wf_1/root")
    assert (wf.kind, wf.scope_id, wf.key) == ("workflow", "wf_1", "root")
    ag = ArtifactRef.parse("artifact://agent/s-abc/result-1")
    assert (ag.kind, ag.scope_id, ag.key) == ("agent", "s-abc", "result-1")
    with pytest.raises(ValueError):
        ArtifactRef.parse("artifact://bogus/x/y")


def test_remove_results_is_explicit_and_scoped(tmp_path):
    store_a = AgentArtifactStore.for_workspace(tmp_path, "s-a")
    store_b = AgentArtifactStore.for_workspace(tmp_path, "s-b")
    store_a.save_result("k", "a")
    store_b.save_result("k", "b")

    assert AgentArtifactStore.remove_results(tmp_path, "s-a") is True
    assert store_a.load(store_a.ref("k")) is None
    assert store_b.load(store_b.ref("k")) == "b"  # 别的作用域不受影响
    # 目录不存在时返回 False（幂等）
    assert AgentArtifactStore.remove_results(tmp_path, "s-a") is False
    assert artifacts_root(tmp_path) == tmp_path / ".asterwynd" / "artifacts"


def test_extract_result_ref_reads_embedded_marker():
    ref = "artifact://agent/s-abc/result-9"
    text = f"head…[truncated; full result in result_ref: {ref}]"
    assert extract_result_ref(text) == ref
    assert extract_result_ref("no marker here") is None
    assert extract_result_ref("…[truncated]") is None


def test_session_store_remove_also_clears_artifacts(tmp_path):
    """D4：SessionStore.remove 显式清理 artifacts/<session_id>（_sessions 永不清理）。"""
    from agent.session import SessionStore

    sessions_root = tmp_path / ".asterwynd" / "sessions"
    sessions_root.mkdir(parents=True)
    (sessions_root / "s-del").mkdir()
    (sessions_root / "s-del" / "messages.json").write_text("[]", encoding="utf-8")
    store = AgentArtifactStore.for_workspace(tmp_path, "s-del")
    ref = store.save_result("k", "body")
    other = AgentArtifactStore.for_workspace(tmp_path, "s-keep")
    other.save_result("k", "other")

    SessionStore(sessions_root=str(sessions_root)).remove("s-del")

    assert store.load(ref) is None                       # artifact removed
    assert other.load(other.ref("k")) == "other"         # unrelated scope survives

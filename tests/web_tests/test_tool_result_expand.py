"""Web 工具结果按需回读（change ``tool-result-lifecycle``，D12）。

- ``tool_result`` 事件不再带全文、带 ``tool_call_id``（loop 侧已断言，见
  ``test_tool_result_lifecycle_loop.py``）；
- 服务端 ``resolve_tool_result`` 三态：全文直返 / 已 spill 走 ref 读回 / missing；
- HTTP 端点存在且只读（session 校验）。
"""
import json
from pathlib import Path

import pytest

from agent.artifact_store import AgentArtifactStore
from agent.memory.tool_result_policy import make_preview
from agent.message import Message, tool_result_message


class _FakeSession:
    def __init__(self, messages, session_id="s-1"):
        self.messages = messages
        self.session_id = session_id
        self.workspace_root = None


def test_resolve_returns_full_text_when_not_spilled():
    from web.session import resolve_tool_result

    session = _FakeSession([tool_result_message("c1", "the full result")])
    payload = resolve_tool_result(session, "c1")
    assert payload["missing"] is False
    assert payload["content"] == "the full result"


def test_resolve_reads_back_through_ref_when_spilled(tmp_path):
    from web.session import resolve_tool_result

    store = AgentArtifactStore.for_workspace(tmp_path, "s-1")
    ref = store.save_result("result-1", "verbatim original body")
    preview = make_preview("old body" * 1000, ref=ref)
    session = _FakeSession([tool_result_message("c1", preview)])
    session.workspace_root = tmp_path
    payload = resolve_tool_result(session, "c1", tmp_path)
    assert payload["missing"] is False
    assert payload["content"] == "verbatim original body"


def test_resolve_missing_when_message_evicted():
    from web.session import resolve_tool_result

    session = _FakeSession([Message(role="user", content="hi")])
    payload = resolve_tool_result(session, "c-gone")
    assert payload["missing"] is True
    assert payload["content"] == ""
    assert payload["reason"]


def test_resolve_missing_when_ref_unreadable(tmp_path):
    from web.session import resolve_tool_result

    ref = "artifact://agent/s-1/never-written"
    preview = make_preview("x" * 50_000, ref=ref)
    session = _FakeSession([tool_result_message("c1", preview)])
    payload = resolve_tool_result(session, "c1", tmp_path)
    assert payload["missing"] is True
    assert payload["reason"]


def test_resolve_missing_without_workspace_root_for_spilled():
    from web.session import resolve_tool_result

    store_ref = "artifact://agent/s-1/result-1"
    preview = make_preview("x" * 50_000, ref=store_ref)
    session = _FakeSession([tool_result_message("c1", preview)])
    payload = resolve_tool_result(session, "c1", workspace_root=None)
    assert payload["missing"] is True


def test_resolve_refuses_cross_scope_ref(tmp_path):
    """L2 纵深防御：消息内嵌了别的 scope 的 ref ⇒ 拒绝（不读他人 scope）。"""
    from web.session import resolve_tool_result

    other = AgentArtifactStore.for_workspace(tmp_path, "s-OTHER")
    other_ref = other.save_result("result-1", "someone else's body")
    preview = make_preview("x" * 50_000, ref=other_ref)
    session = _FakeSession([tool_result_message("c1", preview)], session_id="s-1")
    payload = resolve_tool_result(session, "c1", tmp_path)
    assert payload["missing"] is True          # not served across scopes
    assert payload["content"] == ""

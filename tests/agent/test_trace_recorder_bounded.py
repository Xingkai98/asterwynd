"""trace / tool_calls_made 的 bounded（change ``tool-result-lifecycle``，D2/D6b/D9）。

trace 与 ``tool_calls_made`` 的工具结果全文**无模型面消费者**（D11 核实）⇒ 只需
有界预览 + 诚实标记，不落 ref。分析字段（工具名/状态/错误类型）保持。
"""
from agent.trace_recorder import (
    TRACE_BOUNDED_MARKER,
    TRACE_PREVIEW_CHARS,
    TraceRecorder,
    bound_text,
    bound_value,
)


def test_bound_text_noop_under_limit():
    assert bound_text("short") == "short"


def test_bound_text_truncates_and_marks():
    big = "A" * (TRACE_PREVIEW_CHARS + 1000)
    out = bound_text(big)
    assert out.endswith(TRACE_BOUNDED_MARKER)
    assert len(out) < len(big)
    # 诚实：无 ref（trace 不落 ref）
    assert "result_ref" not in out


def test_bound_value_preserves_structure_and_bounds_leaves():
    args = {"path": "/x", "content": "B" * (TRACE_PREVIEW_CHARS + 5000), "n": 3}
    out = bound_value(args)
    assert out["path"] == "/x"
    assert out["n"] == 3
    assert out["content"].endswith(TRACE_BOUNDED_MARKER)
    assert len(out["content"]) < 5000


def test_record_tool_result_bounds_large_observation_keeps_analysis_fields():
    rec = TraceRecorder()
    rec.record_tool_result(
        "Read", "ok", 12.3, "C" * (TRACE_PREVIEW_CHARS + 9000), error_type=None,
        approval_required=False, approval_granted=True,
    )
    step = rec.steps[-1]
    assert step.type == "tool_result"
    assert step.data["tool_name"] == "Read"
    assert step.data["status"] == "ok"
    assert step.data["duration_ms"] == 12.3
    assert step.data["approval_granted"] is True
    assert step.data["observation"].endswith(TRACE_BOUNDED_MARKER)
    assert len(step.data["observation"]) < TRACE_PREVIEW_CHARS + 100


def test_record_tool_call_bounds_arguments():
    rec = TraceRecorder()
    rec.record_tool_call("Write", {"path": "/a", "content": "D" * (TRACE_PREVIEW_CHARS + 9000)})
    step = rec.steps[-1]
    assert step.type == "tool_call"
    assert step.data["arguments"]["path"] == "/a"
    assert step.data["arguments"]["content"].endswith(TRACE_BOUNDED_MARKER)


def test_record_iteration_bounds_assistant_preview_and_tool_calls():
    rec = TraceRecorder()
    rec.record_iteration(
        iteration=1,
        assistant_preview="E" * (TRACE_PREVIEW_CHARS + 9000),
        tool_calls=[{"id": "c1", "name": "Write", "arguments": {"content": "F" * 9000}}],
    )
    step = rec.steps[-1]
    assert step.data["assistant_preview"].endswith(TRACE_BOUNDED_MARKER)
    assert step.data["tool_calls"][0]["arguments"]["content"].endswith(TRACE_BOUNDED_MARKER)


def test_record_edit_bounds_summary():
    rec = TraceRecorder()
    rec.record_edit("/a.py", "ok", "G" * (TRACE_PREVIEW_CHARS + 9000))
    step = rec.steps[-1]
    assert step.data["summary"].endswith(TRACE_BOUNDED_MARKER)


def test_full_trace_opt_in_keeps_verbatim():
    """D11：benchmark 显式开 ``full_trace=True`` 时保留全文。"""
    rec = TraceRecorder(full_trace=True)
    body = "H" * (TRACE_PREVIEW_CHARS + 9000)
    rec.record_tool_result("Read", "ok", 1.0, body)
    rec.record_tool_call("Write", {"content": body})
    rec.record_iteration(iteration=1, assistant_preview=body)
    assert rec.steps[-3].data["observation"] == body
    assert rec.steps[-2].data["arguments"]["content"] == body
    assert rec.steps[-1].data["assistant_preview"] == body


def test_record_tool_result_spill_step_shape():
    rec = TraceRecorder()
    rec.record_tool_result_spill(spilled_messages=3, bounded_ledger=2, released_bytes=380_000)
    step = rec.steps[-1]
    assert step.type == "tool_result_spill"
    assert step.data == {
        "spilled_messages": 3,
        "bounded_ledger": 2,
        "released_bytes": 380_000,
    }

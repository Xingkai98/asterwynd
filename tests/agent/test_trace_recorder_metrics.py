"""Tests for TraceRecorder observability extensions — token/timestamp/schema.

Covers design.md 第二/三轮：record_iteration 记录 token/model/finish_reason，
record_tool_result 记录 error_type，TraceStep 加 timestamp，to_dict 加
schema_version——全部向后兼容（默认值，不破坏既有事件）。
"""
from __future__ import annotations

import pytest

from agent.trace_recorder import TraceRecorder


class TestTraceStepTimestamp:
    def test_record_adds_timestamp(self) -> None:
        rec = TraceRecorder()
        rec.record("test_event", key="value")
        step = rec.steps[-1]
        assert step.timestamp > 0

    def test_timestamp_is_float(self) -> None:
        rec = TraceRecorder()
        rec.record("test_event")
        assert isinstance(rec.steps[-1].timestamp, float)

    def test_timestamp_not_in_data_payload(self) -> None:
        """timestamp 是 TraceStep 字段，不污染 data 负载（向后兼容）"""
        rec = TraceRecorder()
        rec.record("test_event", key="value")
        assert "timestamp" not in rec.steps[-1].data

    def test_legacy_record_without_timestamp_still_works(self) -> None:
        """向后兼容：直接构造 TraceStep 不带 timestamp 也 OK"""
        rec = TraceRecorder()
        rec.steps.append(__import__("agent.trace_recorder", fromlist=["TraceStep"]).TraceStep(
            step=1, type="legacy", data={}
        ))
        assert rec.steps[-1].type == "legacy"


class TestRecordIterationTokens:
    def test_record_iteration_with_tokens(self) -> None:
        rec = TraceRecorder()
        rec.record_iteration(
            1,
            assistant_preview="hello",
            input_tokens=100,
            output_tokens=50,
            model="gpt-4o-mini",
            finish_reason="stop",
        )
        data = rec.steps[-1].data
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert data["model"] == "gpt-4o-mini"
        assert data["finish_reason"] == "stop"

    def test_record_iteration_without_tokens_backward_compat(self) -> None:
        """旧调用（不传 token）不崩"""
        rec = TraceRecorder()
        rec.record_iteration(1, assistant_preview="hello")
        data = rec.steps[-1].data
        assert data.get("input_tokens") is None


class TestRecordToolResultErrorType:
    def test_record_tool_result_with_error_type(self) -> None:
        rec = TraceRecorder()
        rec.record_tool_result("Bash", "error", 12.3, "boom", error_type="timeout")
        data = rec.steps[-1].data
        assert data["error_type"] == "timeout"

    def test_record_tool_result_without_error_type(self) -> None:
        rec = TraceRecorder()
        rec.record_tool_result("Bash", "ok", 1.0, "fine")
        assert rec.steps[-1].data.get("error_type") is None


class TestSchemaVersion:
    def test_to_dict_has_schema_version(self) -> None:
        rec = TraceRecorder()
        d = rec.to_dict()
        assert d.get("schema_version") == "1.1"

    def test_to_dict_keeps_legacy_fields(self) -> None:
        """向后兼容：既有顶层字段保留"""
        rec = TraceRecorder(task_id="t1", mode="build")
        d = rec.to_dict()
        assert d["task_id"] == "t1"
        assert d["mode"] == "build"
        assert "steps" in d

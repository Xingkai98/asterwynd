"""Unit + integration tests for ToolQualityStore and soft degradation.

Covers tasks 4.1-4.4: per-run aggregation into a quality score, low-score
soft degradation out of variable-layer selection, permission model untouched,
and JSON persistence across runs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.embedding import NGramEmbedding
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta
from agent.loop import AgentLoop
from agent.message import Message
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tools.base import Tool
from agent.tools.governance import ToolQualityStore, ToolSelector
from agent.tools.registry import ToolRegistry
from agent.trace_recorder import TraceRecorder


class _FakeTool(Tool):
    name = "fake"
    description = "a fake tool for testing"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "ok"


class TestQualityScore:
    def test_score_combines_success_duration_approval(self) -> None:
        store = ToolQualityStore(window_size=50, min_samples=5)
        for i in range(10):
            store.record(
                "T",
                success=i < 8,  # 8/10 success
                duration_ms=2000.0,  # duration factor = 1 - 2000/30000
                approval_required=i < 5,
                approval_granted=i < 4,  # 4/5 approved
            )
        score = store.score("T")
        assert score is not None
        assert score == pytest.approx(
            0.5 * 0.8 + 0.3 * (1 - 2000.0 / 30000.0) + 0.2 * 0.8,
            abs=1e-6,
        )

    def test_insufficient_data_returns_neutral(self) -> None:
        store = ToolQualityStore(window_size=50, min_samples=5)
        for _ in range(3):
            store.record("T", success=True, duration_ms=5.0)
        assert store.score("T") is None
        assert store.is_degraded("T") is False

    def test_unknown_tool_returns_neutral(self) -> None:
        store = ToolQualityStore(min_samples=1)
        assert store.score("missing") is None
        assert store.is_degraded("missing") is False

    def test_approval_denials_lower_score(self) -> None:
        denied = ToolQualityStore(window_size=50, min_samples=5)
        granted = ToolQualityStore(window_size=50, min_samples=5)
        for i in range(10):
            denied.record(
                "T", success=True, duration_ms=100.0,
                approval_required=True, approval_granted=False,
            )
            granted.record(
                "T", success=True, duration_ms=100.0,
                approval_required=True, approval_granted=True,
            )
        assert granted.score("T") > denied.score("T")

    def test_no_approval_signal_renormalizes_weights(self) -> None:
        store = ToolQualityStore(window_size=50, min_samples=5)
        for _ in range(10):
            store.record("T", success=True, duration_ms=2000.0)
        score = store.score("T")
        expected = (0.5 * 1.0 + 0.3 * (1 - 2000.0 / 30000.0)) / 0.8
        assert score == pytest.approx(expected, abs=1e-6)

    def test_low_success_rate_degrades(self) -> None:
        store = ToolQualityStore(window_size=50, min_samples=3)
        for _ in range(5):
            store.record("Flaky", success=False, duration_ms=1000.0)
        assert store.is_degraded("Flaky") is True
        assert "Flaky" in store.degraded_tools()
        assert store.quality_notice("Flaky") is not None
        assert store.quality_notice("ok_tool") is None


class TestQualityPersistence:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "quality.json"
        first = ToolQualityStore(window_size=50, min_samples=5, store_path=path)
        for _ in range(8):
            first.record("T", success=True, duration_ms=100.0)
        first.save()
        assert path.exists()

        second = ToolQualityStore(window_size=50, min_samples=5, store_path=path)
        assert second.score("T") == pytest.approx(first.score("T"), abs=1e-9)

    def test_load_missing_file_is_noop(self, tmp_path: Path) -> None:
        store = ToolQualityStore(store_path=tmp_path / "nope.json")
        assert store.score("T") is None


class TestRegistryQualityIntegration:
    def _registry(self, tools: list[Tool]) -> ToolRegistry:
        reg = ToolRegistry(mode_policy=ModePolicy())
        for t in tools:
            reg.register(t)
        selector = ToolSelector(embedder=NGramEmbedding(dim=2048), top_k=5)
        reg.set_selector(selector)
        reg._sync_governance_indexes()
        return reg

    def test_soft_degradation_excluded_from_selection_kept_in_all(self) -> None:
        class _ReadTool(_FakeTool):
            name = "Read"
            description = "read a file from disk"

        class _FlakyTool(_FakeTool):
            name = "Flaky"
            description = "flaky helper tool for transforming data"

        class _HelperTool(_FakeTool):
            name = "Helper"
            description = "reliable helper tool for transforming data"

        reg = self._registry([_ReadTool(), _FlakyTool(), _HelperTool()])
        reg._selector.set_stable_tools(["Read"])
        store = ToolQualityStore(window_size=50, min_samples=3)
        for _ in range(5):
            store.record("Flaky", success=False, duration_ms=1000.0)
        reg.set_quality(store)

        selected_names = [
            s["function"]["name"]
            for s in reg.select_schemas("use the flaky helper tool to transform data")
        ]
        assert "Flaky" not in selected_names
        assert "Read" in selected_names  # stable layer always injected

        all_names = [s["function"]["name"] for s in reg.get_all_schemas()]
        assert "Flaky" in all_names  # soft: still visible and callable

    def test_stable_layer_tool_not_excluded_when_degraded(self) -> None:
        class _ReadTool(_FakeTool):
            name = "Read"
            description = "read a file from disk"

        reg = self._registry([_ReadTool()])
        reg._selector.set_stable_tools(["Read"])
        store = ToolQualityStore(window_size=50, min_samples=1)
        for _ in range(3):
            store.record("Read", success=False, duration_ms=5000.0)
        reg.set_quality(store)

        names = [
            s["function"]["name"]
            for s in reg.select_schemas("read the config file")
        ]
        assert "Read" in names

    def test_quality_does_not_override_permissions(self) -> None:
        class _WriteTool(_FakeTool):
            name = "WriteLike"
            description = "write a file"
            read_only = False

        reg = ToolRegistry(
            mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
        )
        reg.register(_WriteTool())
        store = ToolQualityStore(window_size=50, min_samples=1)
        for _ in range(5):
            store.record("WriteLike", success=True, duration_ms=5.0)
        reg.set_quality(store)

        # High quality must not widen permissions: still denied in read-only.
        assert reg.get_all_schemas() == []


class _ToolThenEndLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(id="c1", name="Echo", arguments="{}")
                ],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_loop_feeds_quality_store_and_trace():
    class _EchoTool(_FakeTool):
        name = "Echo"
        description = "echo back"

    store = ToolQualityStore(window_size=50, min_samples=1)
    reg = ToolRegistry(mode_policy=ModePolicy())
    reg.register(_EchoTool())
    reg.set_quality(store)

    loop = AgentLoop(
        llm=_ToolThenEndLLM(),
        tool_registry=reg,
        hooks=HookManager(),
    )
    trace = TraceRecorder()
    result = await loop.run([Message(role="user", content="echo")], trace_recorder=trace)

    assert result.tool_calls_made and result.tool_calls_made[0].name == "Echo"
    score = store.score("Echo")
    assert score is not None
    assert score > 0.9  # echo always succeeds, fast

    # trace tool_result carries the quality event schema (batch-2 Q10).
    tool_results = [s for s in trace.steps if s.type == "tool_result"]
    assert tool_results
    assert "approval_required" in tool_results[0].data
    assert "approval_granted" in tool_results[0].data

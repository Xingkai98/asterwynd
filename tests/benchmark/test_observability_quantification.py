"""Benchmark quantification (task 6.3) — deterministic, no real LLM.

Covers the three quantifiable observability claims with labeled/golden data:
(a) CostLedger bill() groups by session/phase/tool with correct totals,
(b) ErrorClassifier reaches 100% accuracy on a labeled sample set covering all
    four categories plus the text-fallback branches,
(c) an AgentLoop tool-error path records tokens + error_type in the trace and
    cost in the ledger end-to-end.
"""
from __future__ import annotations

import pytest

from agent.cost_tracker import CostLedger
from agent.llm import LLMResponse, Usage
from agent.message import Message
from agent.observability import ErrorCategory, ErrorClassifier
from agent.tools.base import Tool, ToolCallDelta
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.loop import AgentLoop
from agent.trace_recorder import TraceRecorder


# ---------------------------------------------------------------------------
# (a) CostLedger bill() — session/phase/tool attribution
# ---------------------------------------------------------------------------

def test_cost_ledger_bill_groups_by_session_phase_tool() -> None:
    ledger = CostLedger()
    # gpt-4o price: $2.50 / $10.00 per 1M (input/output).
    ledger.record("gpt-4o", 1000, 500, session_id="s1", phase="building", tool_name="Read")
    ledger.record("gpt-4o", 2000, 1000, session_id="s1", phase="building", tool_name="Bash")
    ledger.record("gpt-4o", 500, 250, session_id="s2", phase="planning", tool_name="Read")

    bill = ledger.bill()
    assert bill["by_session"]["s1"]["tokens"] == 4500
    assert bill["by_session"]["s2"]["tokens"] == 750
    assert bill["by_phase"]["building"]["tokens"] == 4500
    assert bill["by_phase"]["planning"]["tokens"] == 750
    assert bill["by_tool"]["Read"]["tokens"] == 2250  # 1500 (s1) + 750 (s2)
    assert bill["by_tool"]["Bash"]["tokens"] == 3000

    expected_s1 = (1000 / 1e6) * 2.5 + (500 / 1e6) * 10 + (2000 / 1e6) * 2.5 + (1000 / 1e6) * 10
    assert bill["by_session"]["s1"]["cost"] == pytest.approx(expected_s1)
    assert bill["by_phase"]["building"]["cost"] == pytest.approx(expected_s1)
    assert bill["by_tool"]["Read"]["cost"] == pytest.approx((1000 / 1e6) * 2.5 + (500 / 1e6) * 10 + (500 / 1e6) * 2.5 + (250 / 1e6) * 10)
    assert ledger.total() == pytest.approx(
        expected_s1
        + (500 / 1e6) * 2.5 + (250 / 1e6) * 10
    )


def test_cost_ledger_unknown_model_records_tokens_without_cost() -> None:
    ledger = CostLedger()
    ledger.record("future-model-99", 1000, 1000, session_id="s1", phase="building")
    bill = ledger.bill()
    assert bill["by_session"]["s1"]["tokens"] == 2000
    assert bill["by_session"]["s1"]["cost"] == 0.0
    assert ledger.total() == 0.0


# ---------------------------------------------------------------------------
# (b) ErrorClassifier — labeled sample set, 100% accuracy
# ---------------------------------------------------------------------------

def test_error_classifier_labeled_samples_100_percent_accuracy() -> None:
    clf = ErrorClassifier()
    samples: list[tuple[dict, ErrorCategory]] = [
        # structured error_type (all four categories)
        (dict(error_type="permission_denied"), ErrorCategory.PERMISSION_DENIED),
        (dict(error_type="timeout"), ErrorCategory.NETWORK_TIMEOUT),
        (dict(error_type="parse_error"), ErrorCategory.PARAMETER_ERROR),
        # finish_reason → model error
        (dict(finish_reason="max_tokens"), ErrorCategory.MODEL_ERROR),
        (dict(finish_reason="content_filter"), ErrorCategory.MODEL_ERROR),
        # text fallback branches
        (dict(text="[Permission denied: /etc]"), ErrorCategory.PERMISSION_DENIED),
        (dict(text="connection timed out"), ErrorCategory.NETWORK_TIMEOUT),
        (dict(text="[Error: something bad]"), ErrorCategory.PARAMETER_ERROR),
    ]
    # every category appears at least once + at least one text-fallback sample
    categories_seen = {expected for _, expected in samples}
    assert categories_seen == {
        ErrorCategory.PERMISSION_DENIED,
        ErrorCategory.NETWORK_TIMEOUT,
        ErrorCategory.MODEL_ERROR,
        ErrorCategory.PARAMETER_ERROR,
    }
    assert any("text" in kwargs for kwargs, _ in samples)
    for kwargs, expected in samples:
        assert clf.classify(**kwargs) == expected


def test_error_classifier_alert_levels() -> None:
    clf = ErrorClassifier()
    assert clf.alert_level(ErrorCategory.PERMISSION_DENIED) == "immediate"
    assert clf.alert_level(ErrorCategory.NETWORK_TIMEOUT) == "warn"
    assert clf.alert_level(ErrorCategory.MODEL_ERROR) == "warn"
    assert clf.alert_level(ErrorCategory.PARAMETER_ERROR) == "record"
    assert clf.alert_level(ErrorCategory.UNKNOWN) == "record"


# ---------------------------------------------------------------------------
# (c) AgentLoop tool-error path — trace tokens + error_type + ledger end-to-end
# ---------------------------------------------------------------------------

class _DeniedTool(Tool):
    name = "DeniedTool"
    description = "fails with permission denied"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "[Permission denied: can't write there]"


class _ToolThenDoneLLM:
    model = "gpt-4o-mini"

    def __init__(self) -> None:
        self.call_count = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content="using tool",
                tool_calls=[ToolCallDelta(id="c1", name="DeniedTool", arguments="{}")],
                stop_reason="tool_calls",
                usage=Usage(input_tokens=100, output_tokens=50),
            )
        return LLMResponse(
            content="done",
            stop_reason="end_turn",
            usage=Usage(input_tokens=200, output_tokens=100),
        )


@pytest.mark.asyncio
async def test_agentloop_tool_error_path_records_trace_and_ledger() -> None:
    registry = ToolRegistry()
    registry.register(_DeniedTool())
    trace = TraceRecorder()
    ledger = CostLedger()
    loop = AgentLoop(
        llm=_ToolThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        cost_ledger=ledger,
    )

    await loop.run(
        [Message(role="user", content="test")],
        trace_recorder=trace,
        session_id="quant-session",
    )

    # Trace: llm_iteration carries token usage; tool_result carries error_type.
    llm_steps = [s for s in trace.steps if s.type == "llm_iteration"]
    assert llm_steps, "trace should record llm_iteration steps"
    assert llm_steps[0].data["input_tokens"] == 100
    assert llm_steps[0].data["output_tokens"] == 50
    tool_result_steps = [s for s in trace.steps if s.type == "tool_result"]
    assert tool_result_steps, "trace should record tool_result"
    assert tool_result_steps[0].data["status"] == "error"
    assert tool_result_steps[0].data["error_type"] == "permission_denied"

    # Ledger: both LLM calls recorded, session cost attributed.
    assert ledger.total() > 0
    bill = ledger.bill()
    assert bill["by_session"]["quant-session"]["tokens"] == 450  # 100+50+200+100
    assert bill["by_phase"]["building"]["tokens"] == 450
    # phase resolved from the default build mode -> "building"

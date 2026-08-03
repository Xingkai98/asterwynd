"""Loop-level sandbox event tests (design.md Decision 6).

A run with an active TraceRecorder wires the sandbox event sink: a denied Bash
command lands a structured ``sandbox`` step with the calling tool_call_id, and
the sink is restored afterwards so a recorder-less run / a later emit does not
leak events into a stale trace.
"""
from __future__ import annotations

import json

import pytest

from agent.approval import ApprovalDecisionStatus, ApprovalResponse
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta
from agent.loop import AgentLoop
from agent.message import Message
from agent.sandbox_events import emit_sandbox_event
from agent.tools.builtin.bash import BashTool
from agent.tools.registry import ToolRegistry
from agent.trace_recorder import TraceRecorder
from agent.workspace_policy import WorkspacePolicy


class StaticApprovalHandler:
    def __init__(self, status: ApprovalDecisionStatus):
        self.status = status
        self.requests = []

    async def request_approval(self, request):
        self.requests.append(request)
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=self.status,
            reason="static",
        )


class BashThenDoneLLM:
    def __init__(self, cmd: str):
        self._cmd = cmd
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(
                        id="c1", name="Bash", arguments=json.dumps({"cmd": self._cmd})
                    )
                ],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


def _build_loop(cmd: str, tmp_path) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(BashTool(policy=WorkspacePolicy(tmp_path)))
    return AgentLoop(
        llm=BashThenDoneLLM(cmd),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=StaticApprovalHandler(ApprovalDecisionStatus.APPROVED),
    )


@pytest.mark.asyncio
async def test_run_records_sandbox_denied_event(tmp_path):
    trace = TraceRecorder(task_id="sandbox-events")
    loop = _build_loop("rm -rf /", tmp_path)

    result = await loop.run([Message(role="user", content="run")], trace_recorder=trace)

    assert result.content == "done"
    sandbox_steps = [s for s in trace.steps if s.type == "sandbox"]
    assert len(sandbox_steps) == 1
    assert sandbox_steps[0].data["event"] == "denied"
    assert sandbox_steps[0].data["reason"] == "workspace_policy"
    assert sandbox_steps[0].data["command"] == "rm -rf /"
    assert sandbox_steps[0].data["tool_call_id"] == "c1"


@pytest.mark.asyncio
async def test_sink_restored_after_run(tmp_path):
    trace = TraceRecorder(task_id="sandbox-events")
    loop = _build_loop("echo ok", tmp_path)

    await loop.run([Message(role="user", content="run")], trace_recorder=trace)

    # The sink is restored to the default no-op after the run: a later emit
    # must not land in the finished trace.
    emit_sandbox_event("denied", reason="after-run")
    assert [s for s in trace.steps if s.type == "sandbox"] == []

"""Loop-level sandbox event tests (design.md Decision 6).

A run with an active TraceRecorder wires the sandbox event sink: a denied Bash
command lands a structured ``sandbox`` step with the calling tool_call_id, and
the sink is restored afterwards so a recorder-less run / a later emit does not
leak events into a stale trace.

The last section locks the cross-context restore (issue #264): an abandoned
pending subagent run, finalised by GC inside a *later* run's Context, must not
rewrite that run's sink.
"""
from __future__ import annotations

import asyncio
import gc
import json

import pytest

from agent.approval import ApprovalDecisionStatus, ApprovalResponse
from agent.config import AsterwyndConfig
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta, Usage
from agent.loop import AgentLoop
from agent.message import Message
from agent.run_config import AgentMode
from agent.sandbox_events import emit_sandbox_event
from agent.subagent.manager import SubAgentManager
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


def _build_loop(cmd: str, tmp_path, llm=None) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(BashTool(policy=WorkspacePolicy(tmp_path)))
    return AgentLoop(
        llm=llm or BashThenDoneLLM(cmd),
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


# --- Cross-context restore of the sink (issue #264) ---------------------------


def _last_user(messages) -> str:
    for message in reversed(messages):
        if getattr(message, "role", None) == "user":
            return getattr(message, "content", "") or ""
    return ""


_ABANDONED_CHILD_TASK = "__SANDBOX_SINK_ABANDONED_CHILD__"


class HangingChildLLM:
    """Hangs the subagent run whose task text carries the marker.

    The subagent stops on the ``asyncio.sleep`` inside ``AgentLoop.run`` — the
    exact suspension point whose ``finally`` is unwound when the abandoned task
    is later finalised by GC.
    """

    model = "sandbox-sink-hanging-child"

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        if _ABANDONED_CHILD_TASK in _last_user(messages):
            await asyncio.sleep(9999)
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))


def _plant_abandoned_pending_run(tmp_path) -> None:
    """Drive a hanging subagent run on its own event loop, then close that loop.

    The task stays pending (the CI log line ``Task was destroyed but it is
    pending!`` describes exactly this state) and every local reference is
    dropped, so it is only reachable through the ``manager._active_tasks``
    cycle — i.e. it becomes cyclic garbage, finalised by the ``gc.collect()``
    the *live* run performs below.

    The plant Context holds **no** sink (no recorder anywhere in this chain), so
    the abandoned run's ``previous`` snapshot is the default ``_NOOP``: this is
    the "events silently lost" shape of issue #264.

    No ``gc.collect()`` here on purpose — collecting now would finalise the task
    in a Context without a live sink, where the defect is unobservable.
    """
    manager = SubAgentManager(
        llm=HangingChildLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def plant():
        child = manager.create_subagent(name="abandoned", mode="build")
        await manager.run_subagent(
            subagent_id=child["subagent_id"], task=_ABANDONED_CHILD_TASK, wait=False
        )
        await asyncio.sleep(0.05)  # let the subagent enter AgentLoop.run and hang

    try:
        loop.run_until_complete(plant())
    finally:
        loop.close()  # not cancelled: the task stays pending
    # Drop every reference except the manager<->task cycle.
    del loop, plant, manager


class GcThenDeniedBashLLM:
    """Finalises the abandoned task mid-run, then requests a denied command.

    The ``gc.collect()`` fires while *this* run's sink is installed — the window
    in which the abandoned run's teardown can clobber it. The following ``Bash``
    turn then emits a real ``denied`` sandbox event through the production path.
    """

    def __init__(self, cmd: str) -> None:
        self._cmd = cmd
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            gc.collect()
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


def test_abandoned_pending_run_teardown_does_not_clobber_live_sink(tmp_path):
    """issue #264 回归：遗留 pending 子 run 的迟后终结不得改写**活跃** run 的 sink。

    机制（详见 change 的 ``diagnosis.md`` 的 ``## Root Cause``）：子 run 是独立
    ``Task``；其所属 event loop 关闭后，遗留的 pending task 被 GC 终结时，
    ``GeneratorExit`` 会展开该协程**所有嵌套的** ``finally``——包括
    ``AgentLoop.run`` 里对 sandbox sink 的恢复。协程 finalize **不安装**该 task
    自己的 Context，而 ``ContextVar.set`` 写入**当前正在运行的**上下文；若恢复用普通
    ``set_sandbox_sink(previous)``，它就会把后续 run 的 sink 清成 ``_NOOP``，使其
    sandbox 事件**静默丢失**（一条安全拒绝事件不再落入任何 trace）。

    **变异验证**：把 ``finally`` 改回 ``set_sandbox_sink(previous_sandbox_sink)``，
    本用例必须变红（活跃 recorder 收到 0 条 sandbox 事件）。
    """
    _plant_abandoned_pending_run(tmp_path)

    trace = TraceRecorder(task_id="sandbox-events")
    loop = _build_loop("rm -rf /", tmp_path, llm=GcThenDeniedBashLLM("rm -rf /"))

    asyncio.run(loop.run([Message(role="user", content="run")], trace_recorder=trace))

    sandbox_steps = [s for s in trace.steps if s.type == "sandbox"]
    assert len(sandbox_steps) == 1, (
        "遗留 run 的跨上下文收尾把活跃 run 的 sandbox sink 改写了："
        f"活跃 trace 收到 {len(sandbox_steps)} 条 sandbox 事件（应为 1）"
    )
    assert sandbox_steps[0].data["event"] == "denied"
    assert sandbox_steps[0].data["reason"] == "workspace_policy"
    assert sandbox_steps[0].data["command"] == "rm -rf /"


@pytest.mark.asyncio
async def test_nested_run_sandbox_events_return_to_parent_trace(tmp_path):
    """嵌套恢复（issue #264 D1 的同上下文分支）：子 run 退出后回落到**父** sink。

    父 run 在自己的轮次里跑一个带 recorder 的嵌套 run；嵌套 run 退出时它对 sink 的
    恢复必须复原父 run 的 sink，使父 run 之后发出的事件仍落**父** trace——既不丢，
    也不串进子 trace。锁住守护式 ``reset(token)`` 的同上下文语义（与旧
    ``set(previous)`` 行为一致）。
    """
    parent_trace = TraceRecorder(task_id="parent")
    nested_trace = TraceRecorder(task_id="nested")
    nested_loop = _build_loop("rm -rf /", tmp_path)

    class NestedThenParentEmitLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                await nested_loop.run(
                    [Message(role="user", content="nested")],
                    trace_recorder=nested_trace,
                )
                emit_sandbox_event("denied", command="rm -rf /", reason="parent")
            return LLMResponse(content="done", stop_reason="end_turn")

    loop = _build_loop("echo ok", tmp_path, llm=NestedThenParentEmitLLM())

    await loop.run([Message(role="user", content="run")], trace_recorder=parent_trace)

    nested_steps = [s.data for s in nested_trace.steps if s.type == "sandbox"]
    parent_steps = [s.data for s in parent_trace.steps if s.type == "sandbox"]
    assert len(nested_steps) == 1, "嵌套 run 自己的事件未落入自己的 trace"
    assert len(parent_steps) == 1, "子 run 退出后父 run 的事件未回落到父 sink"
    assert parent_steps[0]["reason"] == "parent"
    assert all(step["reason"] != "parent" for step in nested_steps)

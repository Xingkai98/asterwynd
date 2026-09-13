"""Subagent concurrency queue runtime (change ``subagent-concurrency-queue``).

Covers design D1-D7 and the grill decision record
(``openspec/changes/subagent-concurrency-queue/reviews/grill-design.md``):

- queueing instead of fail-fast (D2/D3, Q1),
- permits bound to execution rather than to waiting (D1, Q2-Q4),
- depth-based spawn tool removal (D4, Q6),
- cumulative per-orchestration spawn counting (D5, Q5),
- explicit parent/child identity fields (D6),
- ``RunSubagent``/``GetSubagentRun`` parallelism (D7),
- cancellation of a queued run (Q7) and tool-description guidance (Q8).
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.bus import MessageBus
from agent.subagent.context import (
    current_bus,
    reset_bus,
    reset_current_run_id,
    reset_spawn_depth,
    set_bus,
    set_current_run_id,
    set_spawn_depth,
)
from agent.subagent.manager import SubAgentManager
from agent.tools.builtin.subagents import (
    GetSubagentRunTool,
    RunPatternTool,
    RunSubagentTool,
)
from agent.workspace_policy import WorkspacePolicy

SPAWN_TOOLS = ("CreateSubagent", "RunSubagent", "RunPattern", "ResumeSubagent")
READ_TOOLS = (
    "ListSubagents",
    "GetSubagentRun",
    "CancelSubagentRun",
    "InspectSubagentTranscript",
    "PublishBusMessage",
    "ReadBus",
)


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="subagent done", stop_reason="end_turn", usage=Usage(5, 5))


class SlowLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)
        return LLMResponse(content="late", stop_reason="end_turn", usage=Usage(5, 5))


class PausableLLM:
    """Every LLM call blocks until the gate is resumed.

    ``entered`` counts calls that reached the gate, so a test can observe how
    many runs actually started executing while the gate is closed.
    """

    def __init__(self, on_enter=None):
        self._gate = asyncio.Event()
        self._gate.set()
        self.entered = 0
        self.on_enter = on_enter

    def pause(self) -> None:
        self._gate.clear()

    def resume(self) -> None:
        self._gate.set()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.entered += 1
        if self.on_enter is not None:
            self.on_enter()
        await self._gate.wait()
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


class ProbeLLM:
    """Records the contextvars observed inside each child run."""

    def __init__(self):
        self.depths: list[int] = []
        self.buses: list[object] = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.depths.append(_current_depth())
        self.buses.append(current_bus())
        return LLMResponse(content="probe", stop_reason="end_turn", usage=Usage(5, 5))


def _current_depth() -> int:
    from agent.subagent.context import current_spawn_depth

    return current_spawn_depth()


async def _wait_until(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.01)


def _manager(**kwargs) -> SubAgentManager:
    kwargs.setdefault("config", AsterwyndConfig())
    kwargs.setdefault("parent_mode", AgentMode.BUILD)
    return SubAgentManager(**kwargs)


def _run_status(manager: SubAgentManager, summary: dict) -> str:
    session = manager._sessions[summary["subagent_id"]]
    return session.runs[-1].status if session.runs else "none"


def _tool_names(loop) -> set[str]:
    return {schema["function"]["name"] for schema in loop.tool_registry.get_all_schemas()}


# --- D2/D3: queueing replaces fail-fast ---


@pytest.mark.asyncio
async def test_concurrency_overflow_queues_instead_of_failing():
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")

    first = await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    second = await manager.run_subagent(subagent_id=two["subagent_id"], task="t2", wait=False)

    assert first["status"] == "running"
    # 瞬时并发已满：入队而不是抛 concurrency limit
    assert second["status"] == "queued"
    assert second["run_id"]
    # 排队 run 不占执行任务表（D2/任务 2.3）
    assert second["run_id"] not in manager._active_tasks
    assert first["run_id"] in manager._active_tasks
    await _wait_until(lambda: llm.entered == 1)
    assert llm.entered == 1  # 排队 run 尚未执行

    llm.resume()
    done = await manager.get_subagent_run(
        subagent_id=two["subagent_id"], run_id=second["run_id"], wait=True, timeout_s=3
    )
    assert done["status"] == "completed"


@pytest.mark.asyncio
async def test_queue_full_returns_signal_without_creating_run_record():
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1, max_queued_runs=1)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")
    three = manager.create_subagent(name="three")

    await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    await manager.run_subagent(subagent_id=two["subagent_id"], task="t2", wait=False)
    rejected = await manager.run_subagent(subagent_id=three["subagent_id"], task="t3", wait=False)

    assert rejected["status"] == "queue_full"
    assert "queue is full" in rejected["reason"]
    # Q1：不创建 run record，也不占用 session
    session = manager._sessions[three["subagent_id"]]
    assert session.runs == []
    assert session.active_run_id is None
    llm.resume()


@pytest.mark.asyncio
async def test_queue_full_never_rejects_a_run_that_can_start():
    """队列满判定发生在泵之后：有空槽的 spawn 永远先启动，不会误报 queue_full。"""
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=2, max_queued_runs=1)
    ids = [manager.create_subagent(name=f"s{i}")["subagent_id"] for i in range(3)]

    first = await manager.run_subagent(subagent_id=ids[0], task="t0", wait=False)
    second = await manager.run_subagent(subagent_id=ids[1], task="t1", wait=False)
    # 两个槽都占满，第三个进队列（队列上限 1，恰好不溢出）
    third = await manager.run_subagent(subagent_id=ids[2], task="t2", wait=False)
    assert (first["status"], second["status"], third["status"]) == ("running", "running", "queued")

    # 第一个跑完，槽位释放 → 队列里的 run 应当被泵起来，而不是被拒
    llm.resume()
    done_first = await manager.get_subagent_run(
        subagent_id=ids[0], run_id=first["run_id"], wait=True, timeout_s=3
    )
    assert done_first["status"] == "completed"
    await _wait_until(lambda: _run_status(manager, {"subagent_id": ids[2]}) in {"running", "completed"})
    final = await manager.get_subagent_run(
        subagent_id=ids[2], run_id=third["run_id"], wait=True, timeout_s=3
    )
    assert final["status"] == "completed"


@pytest.mark.asyncio
async def test_cancelled_queued_run_is_skipped_and_slot_reused():
    """Q7 惰性跳过：取消的排队 run 不执行，但队列名额的释放不阻塞后续 run。"""
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1, max_queued_runs=5)
    holder = manager.create_subagent(name="holder")
    cancelled_session = manager.create_subagent(name="cancelled")
    later = manager.create_subagent(name="later")

    await manager.run_subagent(subagent_id=holder["subagent_id"], task="hold", wait=False)
    queued = await manager.run_subagent(
        subagent_id=cancelled_session["subagent_id"], task="drop me", wait=False
    )
    later_run = await manager.run_subagent(subagent_id=later["subagent_id"], task="later", wait=False)
    assert queued["status"] == "queued" and later_run["status"] == "queued"

    await manager.cancel_subagent_run(
        subagent_id=cancelled_session["subagent_id"], run_id=queued["run_id"]
    )
    llm.resume()
    done = await manager.get_subagent_run(
        subagent_id=later["subagent_id"], run_id=later_run["run_id"], wait=True, timeout_s=3
    )
    assert done["status"] == "completed"
    # 被取消的 run 从未真正执行：状态保持 cancelled，摘要为空
    assert _run_status(manager, cancelled_session) == "cancelled"
    assert manager._sessions[cancelled_session["subagent_id"]].runs[-1].summary == ""
    assert manager._permits.in_use == 0


@pytest.mark.asyncio
async def test_wait_true_blocks_through_queue_until_terminal():
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")

    await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    waiting = asyncio.create_task(
        manager.run_subagent(subagent_id=two["subagent_id"], task="t2", wait=True, timeout_s=3)
    )
    await _wait_until(lambda: _run_status(manager, two) == "queued")

    llm.resume()
    result = await asyncio.wait_for(waiting, timeout=3)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_queued_run_time_budget_starts_at_execution():
    """Q3：排队不耗预算——monitor 与 started_at 都在真正执行时才启动。"""
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")

    await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    queued = await manager.run_subagent(
        subagent_id=two["subagent_id"], task="t2", wait=False, max_time_s=0.2
    )
    assert queued["status"] == "queued"
    assert manager._sessions[two["subagent_id"]].runs[-1].started_at is None

    # 排队超过 max_time_s 也不会被超时保护误杀
    await asyncio.sleep(0.4)
    assert _run_status(manager, two) == "queued"

    llm.resume()
    done = await manager.get_subagent_run(
        subagent_id=two["subagent_id"], run_id=queued["run_id"], wait=True, timeout_s=3
    )
    assert done["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_queued_run_marks_cancelled_and_frees_session():
    """Q7：取消排队 run 标 cancelled + 清 active_run_id + 唤醒 waiter。"""
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")

    await manager.run_subagent(subagent_id=one["subagent_id"], task="t1", wait=False)
    queued = await manager.run_subagent(subagent_id=two["subagent_id"], task="t2", wait=False)
    assert queued["status"] == "queued"

    waiting = asyncio.create_task(
        manager.get_subagent_run(
            subagent_id=two["subagent_id"], run_id=queued["run_id"], wait=True, timeout_s=3
        )
    )
    cancelled = await manager.cancel_subagent_run(
        subagent_id=two["subagent_id"], run_id=queued["run_id"]
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["reason"] == "cancelled"
    session_two = manager._sessions[two["subagent_id"]]
    assert session_two.active_run_id is None
    assert session_two.status == "idle"

    # 被取消的排队 run 会被 worker 惰性跳过，且 session 可再次运行
    resumed = await asyncio.wait_for(waiting, timeout=3)
    assert resumed["status"] == "cancelled"
    llm.resume()
    rerun = await manager.run_subagent(subagent_id=two["subagent_id"], task="t3", wait=True, timeout_s=3)
    assert rerun["status"] == "completed"


# --- D1: permits bind to execution, not to waiting ---


class ParentSpawningLLM:
    """The parent run's first LLM call spawns children and waits for them.

    Emulates a subagent loop whose tool call is ``RunSubagent(wait=true)``:
    the parent run is inside ``loop.run()`` (holding its permit) when it
    blocks, which is exactly the deadlock-prone shape D1 must defuse.
    """

    def __init__(self, manager, child_ids):
        self.manager = manager
        self.child_ids = list(child_ids)
        self.calls = 0
        self.holders_at_enter: list[frozenset[str]] = []
        self.children: list[dict] = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        self.holders_at_enter.append(frozenset(self.manager._permit_holders))
        if self.calls == 1:
            for child_id in self.child_ids:
                self.children.append(
                    await self.manager.run_subagent(
                        subagent_id=child_id, task="child task", wait=True, timeout_s=5
                    )
                )
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.mark.asyncio
async def test_parent_run_releases_permit_while_waiting_on_child():
    """D1/Q2：父 run 阻塞等子时交还许可，否则 max_active=1 下自我饥饿。"""
    parent = _manager(llm=StaticLLM(), max_active=1)
    parent_session = parent.create_subagent(name="parent")
    children = [parent.create_subagent(name=f"child-{i}") for i in range(2)]
    parent.llm = ParentSpawningLLM(parent, [c["subagent_id"] for c in children])

    result = await asyncio.wait_for(
        parent.run_subagent(subagent_id=parent_session["subagent_id"], task="parent task", wait=True),
        timeout=5,
    )
    assert result["status"] == "completed"
    assert [child["status"] for child in parent.llm.children] == ["completed", "completed"]
    # 子 run 执行时，占用许可的不是父 run
    parent_run_id = result["run_id"]
    child_entries = parent.llm.holders_at_enter[1:]
    assert child_entries, "children must have executed"
    for holders in child_entries:
        assert parent_run_id not in holders
    # 父 run 执行时确实持许可，且全部结束后许可归还干净
    assert parent_run_id in parent.llm.holders_at_enter[0]
    assert parent._permit_holders == set()
    assert parent._permits.in_use == 0


@pytest.mark.asyncio
async def test_permit_accounting_is_balanced_after_runs():
    manager = _manager(llm=StaticLLM(), max_active=2)
    ids = [manager.create_subagent(name=f"w{i}")["subagent_id"] for i in range(3)]
    results = await asyncio.gather(
        *[manager.run_subagent(subagent_id=i, task="t", wait=True) for i in ids]
    )
    assert all(r["status"] == "completed" for r in results)
    assert manager._permit_holders == set()
    assert manager._permits.in_use == 0  # type: ignore[attr-defined]


# --- D4/Q6: depth removes spawn tools, keeps read tools ---


def test_depth_limit_removes_spawn_tools_but_keeps_read_tools():
    manager = _manager(llm=StaticLLM(), max_depth=1)
    deep = _tool_names(manager._build_subagent_loop(AgentMode.BUILD, depth=1))
    for name in SPAWN_TOOLS:
        assert name not in deep, name
    for name in READ_TOOLS:
        assert name in deep, name

    shallow = _tool_names(manager._build_subagent_loop(AgentMode.BUILD, depth=0))
    for name in SPAWN_TOOLS:
        assert name in shallow, name


def test_build_subagent_loop_depth_defaults_to_exposing_everything():
    """签名兼容（grill 低危项）：depth=None 沿用现状。"""
    manager = _manager(llm=StaticLLM(), max_depth=0)
    names = _tool_names(manager._build_subagent_loop(AgentMode.BUILD))
    for name in SPAWN_TOOLS:
        assert name in names, name


@pytest.mark.asyncio
async def test_deep_child_agent_runs_without_spawn_tools():
    """D4 端到端：depth 到限的子 run 实际执行时工具集不含 spawn 工具。"""
    seen: list[set[str]] = []

    class ToolProbeLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            seen.append({tool["function"]["name"] for tool in (tools or [])})
            return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))

    manager = _manager(llm=ToolProbeLLM(), max_depth=1, max_active=2)
    first = manager.create_subagent(name="first")
    await manager.run_subagent(subagent_id=first["subagent_id"], task="t", wait=True)
    # 该子 run depth=1 == max_depth → 无 spawn 工具
    assert seen, "child run must have executed"
    for schema_names in seen:
        assert "CreateSubagent" not in schema_names
        assert "RunSubagent" not in schema_names
        assert "RunPattern" not in schema_names
        assert "ResumeSubagent" not in schema_names
        assert "GetSubagentRun" in schema_names


# --- D5/Q5: cumulative spawn counting ---


@pytest.mark.asyncio
async def test_cumulative_spawn_budget_counts_create_and_run():
    manager = _manager(llm=StaticLLM(), max_spawns=3)
    one = manager.create_subagent(name="one")  # 1
    assert one["subagent_id"]
    manager.create_subagent(name="two")  # 2
    await manager.run_subagent(subagent_id=one["subagent_id"], task="t", wait=True)  # 3

    with pytest.raises(RuntimeError, match="spawn budget"):
        manager.create_subagent(name="three")
    with pytest.raises(RuntimeError, match="spawn budget"):
        await manager.run_subagent(
            subagent_id=manager.list_subagents()[1]["subagent_id"], task="t", wait=False
        )


@pytest.mark.asyncio
async def test_resume_also_counts_towards_spawn_budget(tmp_path):
    manager = _manager(
        llm=SlowLLM(),
        max_spawns=2,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    created = manager.create_subagent(name="one")  # 1
    launched = await manager.run_subagent(
        subagent_id=created["subagent_id"], task="t", wait=False, max_time_s=0.1
    )  # 2：预算耗尽，且超时保护会写下 checkpoint
    await _wait_until(lambda: manager._sessions[created["subagent_id"]].status == "idle")

    with pytest.raises(RuntimeError, match="spawn budget"):
        await manager.resume_subagent(
            subagent_id=created["subagent_id"],
            run_id=launched["run_id"],
            task="continue",
            wait=False,
        )


# --- D6: explicit parent/child identity ---


def test_session_records_explicit_identity_fields():
    manager = _manager(llm=StaticLLM(), max_depth=5)
    root_created = manager.create_subagent(name="root-level")
    root_summary = manager.get_subagent(root_created["subagent_id"])
    assert root_summary["depth"] == 1
    assert root_summary["parent_run_id"] is None
    assert root_summary["workflow_id"] is None
    assert root_summary["node_id"] is None

    depth_token = set_spawn_depth(2)
    run_token = set_current_run_id("parent-run-id")
    try:
        nested = manager.create_subagent(name="nested")
        nested_summary = manager.get_subagent(nested["subagent_id"])
    finally:
        reset_current_run_id(run_token)
        reset_spawn_depth(depth_token)
    assert nested_summary["depth"] == 3
    assert nested_summary["parent_run_id"] == "parent-run-id"


@pytest.mark.asyncio
async def test_queued_run_keeps_identity_after_spawning_context_is_gone():
    """grill 高危项：排队 run 的 depth/bus 必须在入队时捕获。"""
    llm = PausableLLM()
    llm.pause()
    manager = _manager(llm=llm, max_active=1, max_depth=5)
    blocker = manager.create_subagent(name="blocker")
    queued_session = manager.create_subagent(name="queued")
    await manager.run_subagent(subagent_id=blocker["subagent_id"], task="hold", wait=False)

    bus = MessageBus()
    depth_token = set_spawn_depth(2)
    bus_token = set_bus(bus)
    try:
        queued = await manager.run_subagent(
            subagent_id=queued_session["subagent_id"], task="child", wait=False
        )
    finally:
        reset_bus(bus_token)
        reset_spawn_depth(depth_token)
    assert queued["status"] == "queued"
    # 显式字段在入队时定值（D6）
    run_record = manager._sessions[queued_session["subagent_id"]].runs[-1]
    assert run_record.depth == 3
    assert run_record.parent_run_id is None
    # 生成 run 后父上下文已复位：worker 只能靠捕获的 context
    assert _current_depth() == 0
    assert current_bus() is None

    probe = ProbeLLM()
    manager.llm = probe
    llm.resume()
    await manager.get_subagent_run(
        subagent_id=queued_session["subagent_id"], run_id=queued["run_id"], wait=True, timeout_s=3
    )
    # blocker 先执行（depth 1），排队 run 后执行且仍看到捕获的 depth 3 与 bus
    assert manager.llm is probe
    assert run_record.status == "completed"
    assert probe.depths[-1] == 3
    assert probe.buses[-1] is bus


@pytest.mark.asyncio
async def test_get_subagent_run_wait_after_terminal_does_not_raise():
    manager = _manager(llm=StaticLLM(), max_active=2)
    created = manager.create_subagent(name="runner")
    result = await manager.run_subagent(
        subagent_id=created["subagent_id"], task="t", wait=True
    )
    again = await manager.get_subagent_run(
        subagent_id=created["subagent_id"], run_id=result["run_id"], wait=True, timeout_s=1
    )
    assert again["status"] == "completed"


# --- D7/Q8: tool flags and descriptions ---


def test_run_subagent_and_get_run_are_parallelizable():
    assert RunSubagentTool.parallelizable is True
    assert GetSubagentRunTool.parallelizable is True
    assert RunPatternTool.parallelizable is False


def test_tool_descriptions_explain_queue_semantics():
    run_desc = RunSubagentTool.description.lower()
    assert "queued" in run_desc
    assert "getsubagentrun" in run_desc
    assert "queue_full" in run_desc
    get_desc = GetSubagentRunTool.description.lower()
    assert "wait" in get_desc
    assert "queued" in get_desc


@pytest.mark.asyncio
async def test_run_subagent_calls_in_one_turn_execute_as_one_parallel_group():
    """D7 端到端：一轮多个 RunSubagent 被 loop 归入同一并行组并真并发。"""
    import json as _json

    from agent.loop import AgentLoop
    from agent.hooks.manager import HookManager
    from agent.message import Message
    from agent.tools.registry import ToolRegistry
    from agent.llm import ToolCallDelta

    class TwoCallsLLM:
        def __init__(self, manager, first_id, second_id):
            self.manager = manager
            self.first_id = first_id
            self.second_id = second_id
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallDelta(
                            id="c1",
                            name="RunSubagent",
                            arguments=_json.dumps({"subagent_id": self.first_id, "task": "a"}),
                        ),
                        ToolCallDelta(
                            id="c2",
                            name="RunSubagent",
                            arguments=_json.dumps({"subagent_id": self.second_id, "task": "b"}),
                        ),
                    ],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    manager = _manager(llm=StaticLLM(), max_active=2)
    one = manager.create_subagent(name="one")
    two = manager.create_subagent(name="two")
    loop = AgentLoop(
        llm=TwoCallsLLM(manager, one["subagent_id"], two["subagent_id"]),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        subagent_manager=manager,
        expose_subagent_tools=True,
    )
    from agent.trace_recorder import TraceRecorder

    trace = TraceRecorder(task_id="parallel-subagents")
    result = await loop.run([Message(role="user", content="fan out")], trace_recorder=trace)

    assert result.content == "done"
    parallel_steps = [s for s in trace.steps if s.type == "parallel_execution_start"]
    assert parallel_steps, "RunSubagent calls must be grouped as one parallel group"
    assert parallel_steps[0].data["tools"] == ["RunSubagent", "RunSubagent"]
    payloads = [_json.loads(call.result) for call in result.tool_calls_made]
    # 两个槽位空闲：均同步返回 running（Q8），随后各自跑到终态
    assert [p["status"] for p in payloads] == ["running", "running"]
    collected = await asyncio.gather(
        *[
            manager.get_subagent_run(
                subagent_id=call_subagent_id,
                run_id=payload["run_id"],
                wait=True,
                timeout_s=3,
            )
            for call_subagent_id, payload in zip(
                (one["subagent_id"], two["subagent_id"]), payloads
            )
        ]
    )
    assert [c["status"] for c in collected] == ["completed", "completed"]

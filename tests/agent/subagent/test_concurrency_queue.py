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
    get_desc = GetSubagentRunTool.description.lower()
    assert "wait" in get_desc
    assert "queued" in get_desc

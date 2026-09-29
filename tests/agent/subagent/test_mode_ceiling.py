"""issue #255 回归：workflow / subagent 的 mode 上限基准（change fix-issue-255-mode-ceiling）。

设计约束（全部有实证支撑，见 change 的 `diagnosis.md` / `design.md`）：

- 有效 mode = ``min(节点声明 mode, 当前执行上下文的上限)``；
- 上限走 contextvar（与 ``workflow_id`` / ``node_id`` / ``graph_distance`` / ``bus`` 同路）；
- 上限在 **run 起点** 快照（一次 run 的能力边界自始至终一致）；
- 挂载 A（run 起点）：``set(本 run 有效 mode)``，退出时用 ``set(prior)`` **恢复**
  （不是 ``reset(token)``——那会在跨 context teardown 时抛 ``ValueError``）；
- 挂载 B（调度器派发点 ``_launch_run``）：``set(min(node.mode, cur))`` + ``finally reset``；
- 执行点 ``_execute_run_in_context`` **不** reset；
- 上限缺失时回落**静态 ``parent_mode``**（保守），绝不回落 ``None``。

**测试形态硬约束**：会产生 mode 差异的用例必须经**真实 ``AgentLoop.run``** 驱动，
不得用 mock 手工 ``set`` 上限替代 run 起点——后者在缺陷实现与修复实现下取值相同（假保护）。
"""

from __future__ import annotations

import asyncio
import gc

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.loop import AgentLoop
from agent.message import Message
from agent.run_config import AgentMode, AgentRunConfig
from agent.subagent.bus import MessageBus
from agent.subagent.context import current_mode_ceiling
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.tools.registry import ToolRegistry
from agent.workspace_policy import WorkspacePolicy


class _StaticLLM:
    model = "mode-ceiling-test"

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))


def _last_user(messages) -> str:
    for message in reversed(messages):
        if getattr(message, "role", None) == "user":
            return getattr(message, "content", "") or ""
    return ""


def _manager(tmp_path, llm=None, *, parent_mode=AgentMode.BUILD) -> SubAgentManager:
    return SubAgentManager(
        llm=llm or _StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=parent_mode,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _root_loop(manager, mode: AgentMode) -> AgentLoop:
    return AgentLoop(
        llm=manager.llm,
        tool_registry=ToolRegistry(),
        subagent_manager=manager,
        expose_subagent_tools=True,
        run_config=AgentRunConfig(mode=mode),
    )


def _modes_by_name(manager: SubAgentManager) -> dict[str, str]:
    return {s["name"]: s["mode"] for s in manager.list_subagents()}


async def _dispatch_spec(manager: SubAgentManager, spec: dict) -> None:
    """在**当前调用栈**里派发一张图（由真实 run 的轮次内调用即激活挂载 A）。"""
    scheduler = WorkflowScheduler(manager, bus=MessageBus())
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(spec))


def _build_spec(node_id: str, mode: str) -> dict:
    return {
        "goal": "g",
        "nodes": [{"id": node_id, "kind": "subagent", "task": "t", "mode": mode}],
        "edges": [],
    }


#: 只有 root run 的 user 消息含该标记——子 loop 复用同一个 LLM 对象，
#: 用标记把 hook 限制在 root 轮次内，避免子 run 再次触发 hook（递归派发）。
_ROOT_MARKER = "__ROOT_GO__"
#: 子 run 的 task 文本（child 的 run 才 spawn grand）。
_CHILD_TASK = "__CHILD_SPAWN_GRAND__"


async def _run_root_with_hook(manager, mode, hook):
    """跑一轮真实 ``AgentLoop.run``，在其轮次内执行 ``hook``。

    ``hook`` 在 LLM 的 ``chat`` 里被 await——那一刻挂载 A 已按 run 起点设好上限，
    所以 hook 内的派发/嵌套都发生在真实的 run 上下文里。``hook`` 仅在 root 轮次
    触发（``_ROOT_MARKER``），子 run 直接返回。
    """
    loop = _root_loop(manager, mode)
    llm = manager.llm

    async def chat(messages, tools=None, model="gpt-4"):
        if _ROOT_MARKER in _last_user(messages):
            await hook()
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    original = llm.chat
    llm.chat = chat
    try:
        await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
    finally:
        llm.chat = original
    return loop


# --- 1. fail-open 方向 + 对照 -------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_session_clamps_build_node(tmp_path):
    """只读会话 + 声明 build 的节点 ⇒ 只读。"""
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, _build_spec("bw", "build"))

    await _run_root_with_hook(manager, AgentMode.READ_ONLY, hook)
    assert _modes_by_name(manager)["bw"] == "read_only"


@pytest.mark.asyncio
async def test_build_session_grants_build_node(tmp_path):
    """对照：build 会话 + 声明 build ⇒ build（证明不是无差别压低）。"""
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, _build_spec("bw", "build"))

    await _run_root_with_hook(manager, AgentMode.BUILD, hook)
    assert _modes_by_name(manager)["bw"] == "build"


@pytest.mark.asyncio
async def test_failopen_sequence_run_then_switch_then_dispatch_stays_readonly(tmp_path):
    """issue #255 的**原始** fail-open 时序：同一会话先 BUILD run，再切只读，再派发 build 节点。

    缺陷实现下，第一次 run 的子 loop 构造把共享基准覆写成 BUILD，之后 ``set_mode``
    只改会话自身状态、不重算基准，故第二次派发仍被授予 build（只读会话被授予写权限）。
    """
    manager = _manager(tmp_path)
    loop = _root_loop(manager, AgentMode.BUILD)
    llm = manager.llm
    payload = {"spec": _build_spec("r1-bw", "build")}

    async def chat(messages, tools=None, model="gpt-4"):
        if _ROOT_MARKER in _last_user(messages):
            await _dispatch_spec(manager, payload["spec"])
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    original = llm.chat
    llm.chat = chat
    try:
        # run 1：BUILD 会话跑一张含 build 节点的图（真实 run → 构造子 loop）
        await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
        assert _modes_by_name(manager)["r1-bw"] == "build"

        # 用户把会话切到只读（只改会话自身状态，不重算任何基准）
        loop.runtime_state.set_mode("read_only", source="test")

        # run 2：同一会话再派发一个 build 节点 ⇒ 必须收窄
        payload["spec"] = _build_spec("r2-bw", "build")
        await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
    finally:
        llm.chat = original

    assert _modes_by_name(manager)["r2-bw"] == "read_only", "只读会话被授予了写权限（fail-open）"


# --- 2. 静默降级方向 + 对照 ---------------------------------------------------


@pytest.mark.asyncio
async def test_build_node_is_not_demoted_by_a_preceding_readonly_node(tmp_path):
    """BUILD 会话：先只读节点、后 build 节点 ⇒ 后者仍 build；对照：前者仍只读。"""
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "ro", "kind": "subagent", "task": "t", "mode": "read_only"},
            {"id": "bw", "kind": "subagent", "task": "t", "mode": "build"},
        ],
        "edges": [],
    }
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, spec)

    await _run_root_with_hook(manager, AgentMode.BUILD, hook)
    modes = _modes_by_name(manager)
    assert modes["ro"] == "read_only"
    assert modes["bw"] == "build", "build 节点被前面的 read_only 节点静默降级了"


# --- 3. 并发：兄弟互不覆盖 + 构造序不变性 -------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [("bw", "ro"), ("ro", "bw")])
async def test_parallel_siblings_keep_their_own_modes_regardless_of_order(tmp_path, order):
    """并行 A(build)/B(read_only) 各得其所，且构造序反转结果一致。

    注：默认配置下每节点经 ``create_task`` 各自成 task，本用例是**护栏**——
    它挡「实现把两个兄弟写回同一标量」这类退化；真正的区分点是跨图/跨 run 污染。
    """
    spec = {
        "goal": "g",
        "nodes": [
            {
                "id": node_id,
                "kind": "subagent",
                "task": "t",
                "mode": "build" if node_id == "bw" else "read_only",
            }
            for node_id in order
        ],
        "edges": [],
    }
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, spec)

    await _run_root_with_hook(manager, AgentMode.BUILD, hook)
    modes = _modes_by_name(manager)
    assert modes["bw"] == "build"
    assert modes["ro"] == "read_only"


# --- 4. 嵌套：两条路径（O1 订正：用可达例子） ---------------------------------


@pytest.mark.asyncio
async def test_direct_spawn_chain_inherits_parent_effective_mode(tmp_path):
    """路径 (b) 直接 spawn 链：root=bypass → child(声明 build) → grand(不声明)。

    grand 必须继承 child 的**有效** mode（build），而不是 root 的上限（bypass）。
    只做派发点挂载时 grand 会读到 root 的 bypass——这正是新 fail-open。
    """
    manager = _manager(tmp_path)

    # 让 child 的 run 在它的轮次里 spawn grand（不声明 mode）
    loop = _root_loop(manager, AgentMode.BYPASS)
    llm = manager.llm

    async def chat(messages, tools=None, model="gpt-4"):
        text = _last_user(messages)
        if _CHILD_TASK in text:
            manager.create_subagent(name="grand")
        elif _ROOT_MARKER in text:
            child = manager.create_subagent(name="child", mode="build")
            await manager.run_subagent(
                subagent_id=child["subagent_id"], task=_CHILD_TASK, wait=True
            )
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    original = llm.chat
    llm.chat = chat
    try:
        await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
    finally:
        llm.chat = original

    modes = _modes_by_name(manager)
    assert modes["child"] == "build"
    assert modes["grand"] == "build", "grand 越过父辈有效 mode（fail-open）"


@pytest.mark.asyncio
async def test_workflow_node_effective_mode_bounds_the_node_itself(tmp_path):
    """路径 (a) workflow 节点内派生：root=bypass，节点声明 read_only ⇒ 节点自身收窄。"""
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, _build_spec("ro", "read_only"))

    await _run_root_with_hook(manager, AgentMode.BYPASS, hook)
    assert _modes_by_name(manager)["ro"] == "read_only"


# --- 5. 快照：run 中途切 mode 不影响本次 run；下一次 run 用新 mode -------------


@pytest.mark.asyncio
async def test_run_start_snapshot_survives_mid_run_mode_switch(tmp_path):
    """run 起点是 build；run 中途切到 read_only；本次 run 内派发的 build 节点仍得 build。"""
    manager = _manager(tmp_path)
    loop = _root_loop(manager, AgentMode.BUILD)
    llm = manager.llm

    async def chat(messages, tools=None, model="gpt-4"):
        if _ROOT_MARKER in _last_user(messages):
            # 已进入真实 run（挂载 A 已按 run 起点 build 设好上限）
            loop.runtime_state.set_mode("read_only", source="test")
            await _dispatch_spec(manager, _build_spec("bw", "build"))
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    original = llm.chat
    llm.chat = chat
    try:
        await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
    finally:
        llm.chat = original

    assert _modes_by_name(manager)["bw"] == "build", "本次 run 的上限被中途切换改写"


@pytest.mark.asyncio
async def test_next_run_after_switch_uses_new_mode(tmp_path):
    """对照：切换后**新起**的 run（read_only 会话 + build 节点）⇒ 只读。"""
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, _build_spec("bw", "build"))

    await _run_root_with_hook(manager, AgentMode.READ_ONLY, hook)
    assert _modes_by_name(manager)["bw"] == "read_only"


# --- 6. 跨图污染：同会话顺序两张图互不影响 -----------------------------------


@pytest.mark.asyncio
async def test_second_graph_is_not_polluted_by_first_graph(tmp_path):
    """同会话（全程 BUILD）顺序两张图：图 1 含只读节点，图 2 是 build ⇒ 图 2 仍 build。"""
    graph_one = _build_spec("g1-ro", "read_only")
    graph_two = _build_spec("g2-bw", "build")
    manager = _manager(tmp_path)

    async def hook():
        await _dispatch_spec(manager, graph_one)
        await _dispatch_spec(manager, graph_two)

    await _run_root_with_hook(manager, AgentMode.BUILD, hook)
    modes = _modes_by_name(manager)
    assert modes["g1-ro"] == "read_only"
    assert modes["g2-bw"] == "build", "图 2 被图 1 的只读节点污染（静默降级）"


# --- 7. 通道：可读 + 保守回落（不得无界） -------------------------------------


@pytest.mark.asyncio
async def test_scheduler_direct_drive_falls_back_to_static_parent_mode(tmp_path):
    """不经任何 ``AgentLoop.run`` 直驱调度器：上限回落静态 ``parent_mode``（保守）。

    parent_mode=read_only ⇒ 声明 build 的节点得 read_only（不是 build，也不是 bypass）。
    """
    manager = _manager(tmp_path, parent_mode=AgentMode.READ_ONLY)

    # 直驱：无 loop、无挂载 A
    await _dispatch_spec(manager, _build_spec("bw", "build"))

    granted = _modes_by_name(manager)["bw"]
    assert granted == "read_only", f"上限缺失时应回落静态 parent_mode（保守），实际 {granted}"


def test_current_mode_ceiling_defaults_to_none_never_unbounded():
    """通道本体：未 set 时返回 None（调用方须回落静态值），不是 bypass。"""
    assert current_mode_ceiling() is None


@pytest.mark.asyncio
async def test_cancelled_run_does_not_raise_and_restores_ceiling(tmp_path):
    """取消路径：子 run 被取消时不得因上限 token 抛 ``ValueError``，且 run 退出后上限复原。

    执行点（``_execute_run_in_context``）刻意**不**对上限 token 做 reset——跨 context
    teardown 的 ``reset`` 会抛 ``ValueError``（既有注释 ``manager.py`` 已说明）。
    """
    import asyncio

    started = asyncio.Event()

    class _RootSpawnsThenHangsLLM(_StaticLLM):
        """root 轮次里 spawn 一个子 run 并取消它；子 run 的 ``chat`` 挂住直到被取消。

        单个 LLM 对象按「是否 root 轮次」分流——避免用 patch 覆盖它（那会同时
        改掉子 run 的行为，使子 run 不挂住、取消路径测不到）。
        """

        def __init__(self, manager):
            self.manager = manager

        async def chat(self, messages, tools=None, model="gpt-4"):
            if _ROOT_MARKER in _last_user(messages):
                child = self.manager.create_subagent(name="hang", mode="build")
                assert child["mode"] == "read_only"  # 只读会话收窄
                payload = await self.manager.run_subagent(
                    subagent_id=child["subagent_id"], task="hang", wait=False
                )
                await asyncio.wait_for(started.wait(), timeout=5)
                await self.manager.cancel_subagent_run(
                    subagent_id=child["subagent_id"], run_id=payload["run_id"]
                )
                return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))
            started.set()
            await asyncio.sleep(30)
            return LLMResponse(content="late", stop_reason="end_turn", usage=Usage(1, 1))

    manager = _manager(tmp_path)
    llm = _RootSpawnsThenHangsLLM(manager)
    manager.llm = llm
    loop = _root_loop(manager, AgentMode.READ_ONLY)

    await loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None)
    assert current_mode_ceiling() is None, "run 退出后上限未复原"


@pytest.mark.asyncio
async def test_mode_ceiling_channel_contract_used_by_asset_path(tmp_path):
    """``mode_ceiling()`` 是 #245 消费的公共通道：scheduler 只持 manager 也能读到。

    契约：读到的值 = 当前执行单元上限；缺失时回落静态 ``parent_mode``（保守），
    且 ``effective_mode(declared) == min(declared, ceiling)``。
    """
    manager = _manager(tmp_path, parent_mode=AgentMode.READ_ONLY)

    # 无 ceiling：回落静态 parent_mode（不是 None、不是 bypass）
    assert manager.mode_ceiling() is AgentMode.READ_ONLY
    # 节点有效 mode = min(声明, 上限)
    assert manager.effective_mode("build") is AgentMode.READ_ONLY
    assert manager.effective_mode(None) is AgentMode.READ_ONLY

    # 安装一个更宽的上限（模拟 build 会话 run 起点）：取 min 后仍是声明值
    from agent.subagent.context import reset_mode_ceiling, set_mode_ceiling

    token = set_mode_ceiling(AgentMode.BUILD)
    try:
        assert manager.mode_ceiling() is AgentMode.BUILD
        assert manager.effective_mode("build") is AgentMode.BUILD
        assert manager.effective_mode("read_only") is AgentMode.READ_ONLY
    finally:
        reset_mode_ceiling(token)


# --- 8. 挂载 A 的 set 恢复：同 task 跨会话不泄漏 -------------------------------


@pytest.mark.asyncio
async def test_run_exit_restores_ceiling_so_later_direct_drive_stays_conservative(tmp_path):
    """同 task 内：先跑 build 会话的 loop.run，再直驱 read_only 会话的调度器。

    若挂载 A 退出时不恢复上限，第二次直驱会读到上一个会话的 build（跨会话 fail-open）。
    """
    # 第一步：build 会话跑一轮真实 run（挂载 A 设 build；退出必须恢复）
    build_manager = _manager(tmp_path)
    build_loop = _root_loop(build_manager, AgentMode.BUILD)
    await build_loop.run([Message(role="user", content="noop")], on_event=None)
    assert current_mode_ceiling() is None, "run 退出后上限未恢复（泄漏给后续同 task 操作）"

    # 第二步：同一 task 内直驱 read_only 会话的调度器（不经 loop）
    ro_manager = _manager(tmp_path, parent_mode=AgentMode.READ_ONLY)
    await _dispatch_spec(ro_manager, _build_spec("bw", "build"))

    assert _modes_by_name(ro_manager)["bw"] == "read_only", "读到上一个会话的上限（跨会话 fail-open）"


# --- 9. 已知残留的边界锁 ------------------------------------------------------


@pytest.mark.asyncio
async def test_resubmitting_an_existing_session_does_not_reclamp(tmp_path):
    """文档锁：mode 在 ``create_subagent`` 期冻结，``RunSubagent`` 重跑不重新钳制。

    这是**既有设计**（非本 change 的缺陷面），锁住现状以免将来被误当回归。
    """
    manager = _manager(tmp_path)
    created = manager.create_subagent(name="frozen", mode="build")
    assert created["mode"] == "build"

    # 会话内 mode 已冻结；随后 manager 的静态下限变化也不改写既有 session
    manager.parent_mode = AgentMode.READ_ONLY
    await manager.run_subagent(subagent_id=created["subagent_id"], task="t", wait=True)
    assert manager.get_subagent(created["subagent_id"])["mode"] == "build"


# --- 10. 挂载 A 的跨上下文恢复（issue #261） ---------------------------------


_CHILD_TASK = "__CHILD_HANG__"


class _HangingChildLLM(_StaticLLM):
    """子 run（task 文本含 ``_CHILD_TASK``）挂住，其余轮次立即返回。

    让子 run 停在 ``AgentLoop.run`` 内部的 await 上——这正是它日后被 GC 终结时
    会展开挂载 A ``finally`` 的挂起点。
    """

    async def chat(self, messages, tools=None, model="gpt-4"):
        if _CHILD_TASK in _last_user(messages):
            await asyncio.sleep(9999)
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))


def _plant_abandoned_pending_run(tmp_path) -> None:
    """在一个**独立 event loop** 上跑一个会挂住的子 run，然后关闭该 loop。

    loop 关闭后 task 仍 pending——CI 日志 ``Task was destroyed but it is pending!``
    描述的就是这一状态。丢弃全部本地引用后，task 会在日后被 GC 终结：终结会把
    ``GeneratorExit`` 抛进协程并展开 ``AgentLoop.run`` 的 ``finally``（挂载 A 的
    恢复），而该恢复运行在**当时正在运行的**上下文里。
    """
    manager = SubAgentManager(
        llm=_HangingChildLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    loop = asyncio.new_event_loop()

    async def plant():
        child = manager.create_subagent(name="abandoned", mode="build")
        await manager.run_subagent(
            subagent_id=child["subagent_id"], task=_CHILD_TASK, wait=False
        )
        await asyncio.sleep(0.05)  # 让子 run 进入 AgentLoop.run 并挂起

    loop.run_until_complete(plant())
    loop.close()  # 不 cancel：task 保持 pending
    # 丢弃全部引用（manager 与 task 经 ``_active_tasks`` 互引，构成可回收的环）。
    del loop, plant


def _run_live_readonly_session(tmp_path) -> dict[str, str]:
    """跑 read_only 会话的真实 run，并在其**派发点**强制 GC 后返回各节点 mode。

    派发点的 ``gc.collect()`` 让「先前遗留 task 的迟后终结」确定性地落在
    本 run 的上限生效窗口内——即 issue #261 在 CI 负载下偶发命中的那一时刻。
    """
    manager = _manager(tmp_path)  # 静态 parent_mode=BUILD
    loop = _root_loop(manager, AgentMode.READ_ONLY)
    llm = manager.llm
    spec = _build_spec("bw", "build")

    async def chat(messages, tools=None, model="gpt-4"):
        if _ROOT_MARKER in _last_user(messages):
            gc.collect()  # 终结遗留 task —— 就在本 run 的上下文里
            await _dispatch_spec(manager, spec)
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    original = llm.chat
    llm.chat = chat
    try:
        asyncio.run(loop.run([Message(role="user", content=_ROOT_MARKER)], on_event=None))
    finally:
        llm.chat = original
    return _modes_by_name(manager)


def test_abandoned_pending_run_teardown_does_not_clobber_live_ceiling(tmp_path):
    """issue #261 回归：遗留 pending 子 run 的迟后终结不得清空**当前活跃**的上限。

    机制（详见 change 的 ``diagnosis.md`` 的 ``## Root Cause``）：子 run 是独立
    ``Task``；其所属 event loop 关闭后，遗留的 pending task 被 GC 终结时，
    ``GeneratorExit`` 会展开该协程**所有嵌套的** ``finally``——包括
    ``AgentLoop.run`` 里挂载 A 的恢复。该恢复跑在**当时正在运行的**上下文里；
    若它用普通 ``set_mode_ceiling(previous)``，就会把后续用例正在使用的只读上限
    清成 ``None``，使节点回落静态 ``parent_mode``（BUILD）而被授予 ``build``
    （fail-open）——这正是 CI 里 ``assert 'build' == 'read_only'`` 的来源。

    **变异验证**：把实现改回 ``set_mode_ceiling(previous_ceiling)``，本用例必须变红。
    """
    _plant_abandoned_pending_run(tmp_path)

    modes = _run_live_readonly_session(tmp_path)

    assert modes["bw"] == "read_only", (
        "遗留 run 的跨上下文收尾把活跃的只读上限清空了（节点被授予 build，fail-open）"
    )

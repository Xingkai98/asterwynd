"""foreach 并行可见性（change ``enhance-workflow-graph-ux``，M2.1/M2.2/M2.3）。

覆盖 G1/G2/G7：

- **G1**：计数必须在**每项完成那一刻**前进。若记账点落在 ``await asyncio.gather``
  **之后**的结果循环里，整个运行期 ``items_completed`` 恒为 0、全部跑完才跳到 N
  ——D5 的立项动机（「看到并行」）在时间维度上完全落空。
- **G2**：项级迁移要推帧（调度器侧限频，只合并构建不丢尾帧）。
- **G7**：``item_states`` 是 per-item 状态的权威来源；``items_running`` 必须从
  run record 的 ``status == "running"`` 取——「已派发未终态」会把 20 个排队项
  也画成「在跑」。
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

#: ``item_states`` 的合法取值（``pending`` 未派发 / ``queued`` 已派发等 slot /
#: ``running`` 真正在跑 / 其余为终态）。
ITEM_STATES = frozenset(
    {"pending", "queued", "running", "completed", "failed", "cancelled", "budget_exceeded"}
)


class SlowLLM:
    """每个 run 睡 ``delay`` 秒——给「运行中取快照」留出观察窗口。"""

    def __init__(self, delay: float = 0.05, content: str = "worker result"):
        self.delay = delay
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=SlowLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _manager_with_active(tmp_path, max_active: int) -> SubAgentManager:
    """``max_active`` 只能在构造期定：它决定许可池（``_ExecutionPermits``）的大小，
    事后改属性不会改变真实并发——用它会写出「假设 1 项在跑、实际 5 项」的假测试。"""
    return SubAgentManager(
        llm=SlowLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=max_active,
    )


def _foreach_spec(count: int = 6) -> dict:
    return {
        "goal": "fan",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "item {item}",
             "items": [f"item-{i}" for i in range(count)]},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }


def _scheduler(manager, raw: dict) -> WorkflowScheduler:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(raw)
    return scheduler


def _fan(snapshot: dict) -> dict:
    return next(node for node in snapshot["nodes"] if node["id"] == "fan")


async def _observed_fan_states(scheduler, run_task, *, samples: int = 400):
    """在 workflow 跑完之前反复取快照，返回每次观测到的 fan 节点投影。"""
    observed = []
    for _ in range(samples):
        if run_task.done():
            break
        observed.append(_fan(scheduler.workflow_graph_snapshot()))
        await asyncio.sleep(0.005)
    return observed


# --- G1：计数是渐进的，不是 0 → N 的跳变 ------------------------------------


@pytest.mark.asyncio
async def test_items_completed_is_progressive_not_zero_until_end(tmp_path):
    """G1 回归：运行期必须出现**中间值**的 ``items_completed``。

    记账点若在 ``gather`` 之后（唯一不可能产生中间值的时刻），这条断言必红：
    整个运行期恒为 0，跑完才一次跳到 6。
    """
    manager = _manager_with_active(tmp_path, 1)
    manager.llm = SlowLLM(delay=0.05)
    scheduler = _scheduler(manager, _foreach_spec(count=6))

    run_task = asyncio.create_task(scheduler.run(scheduler.spec))
    observed = await _observed_fan_states(scheduler, run_task)
    await run_task

    seen = [node.get("items_completed") for node in observed if node.get("items_completed")]
    assert seen, "运行期一次都没有观测到 items_completed 前进"
    # 记账点落在 gather 之后时，运行期只会出现「6」（0 被过滤掉）——唯一取值。
    assert len(set(seen)) >= 3, (
        f"计数只出现了 0/N → N/N 的跳变，没有中间值：{sorted(set(seen))}"
    )
    assert min(seen) < 6, f"计数没有渐进：{sorted(set(seen))}"


@pytest.mark.asyncio
async def test_items_completed_ends_at_total(manager):
    """收敛后计数必须等于项数（不是超过、也不是停在中间）。"""
    manager.max_active = 2
    manager.llm = SlowLLM(delay=0.01)
    scheduler = _scheduler(manager, _foreach_spec(count=4))
    await scheduler.run(scheduler.spec)

    fan = _fan(scheduler.workflow_graph_snapshot())
    assert fan["items"] == 4
    assert fan["items_completed"] == 4
    assert fan["items_failed"] == 0


@pytest.mark.asyncio
async def test_items_failed_counts_non_completed_envelopes(manager):
    """失败项进 ``items_failed``（口径与既有 ``failures`` 对齐）。"""

    class BoomLLM(SlowLLM):
        async def chat(self, messages, tools=None, model="gpt-4"):
            raise RuntimeError("model exploded")

    manager.llm = BoomLLM(delay=0.0)
    manager.max_active = 2
    scheduler = _scheduler(manager, _foreach_spec(count=3))
    await scheduler.run(scheduler.spec)

    fan = _fan(scheduler.workflow_graph_snapshot())
    assert fan["items_failed"] == 3
    assert fan["items_completed"] == 0


# --- G7：per-item 状态与 running/queued 细分 --------------------------------


@pytest.mark.asyncio
async def test_item_states_track_every_index_during_run(tmp_path):
    """``item_states`` 长度恒等于项数，取值恒在合法集内——含中途态。"""
    manager = _manager_with_active(tmp_path, 1)
    manager.llm = SlowLLM(delay=0.05)
    scheduler = _scheduler(manager, _foreach_spec(count=6))

    run_task = asyncio.create_task(scheduler.run(scheduler.spec))
    observed = await _observed_fan_states(scheduler, run_task)
    await run_task

    # 容器派发（项被解析出来）之前不发项级字段——否则前端会显示「0/0 完成」。
    expanded = [node for node in observed if node.get("item_states") is not None]
    assert expanded, "一次都没观测到项级字段"
    for node in expanded:
        assert len(node["item_states"]) == 6
        assert set(node["item_states"]) <= ITEM_STATES, set(node["item_states"]) - ITEM_STATES

    # 中途必须真的出现过「非 pending」的项，否则堆叠条永远是全灰。
    assert any(
        any(state != "pending" for state in node["item_states"]) for node in expanded
    )


@pytest.mark.asyncio
async def test_items_running_excludes_queued_items(tmp_path):
    """``items_running`` 只数真正在跑的 run，不把排队项算进去。

    ``_dispatch_capacity`` 是 ``max_active + max_queued_runs``（默认 25），所以 6 项
    会被**一次性派发**——若用「已派发未终态」当在跑，6 项会全画成蓝的；而
    ``max_active=1`` 时真正在跑的永远只有 1 项。
    """
    manager = _manager_with_active(tmp_path, 1)
    manager.llm = SlowLLM(delay=0.05)
    scheduler = _scheduler(manager, _foreach_spec(count=6))

    run_task = asyncio.create_task(scheduler.run(scheduler.spec))
    observed = await _observed_fan_states(scheduler, run_task)
    await run_task

    expanded = [node for node in observed if node.get("item_states") is not None]
    running = [node["items_running"] for node in expanded]
    assert any(value > 0 for value in running), "运行期一次都没有观测到 items_running > 0"
    assert max(running) <= 1, f"max_active=1 却报出同时在跑 {max(running)} 项"

    # 同时必须观测到「已派发但在排队」的项（否则 running/queued 的区分没意义）。
    assert any("queued" in node["item_states"] for node in expanded), (
        "没有观测到任何排队项——items_running 口径无法被验证"
    )


@pytest.mark.asyncio
async def test_item_states_absent_for_auto_aggregate_nodes(manager):
    """计数与 ``item_states`` 只对 ``kind == "foreach"`` 输出。

    自动插层节点从不经过 ``_execute_foreach``——给它输出计数会恒定显示「0/3 完成」。
    """
    spec = {
        "goal": "wide",
        "nodes": [
            {"id": f"l{i}", "kind": "subagent", "task": f"t{i}"} for i in range(13)
        ] + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [
            {"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(13)
        ],
        "terminal": ["root"],
    }
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    auto = [node for node in snapshot["nodes"] if node["id"].startswith("__auto_agg__")]
    assert auto, "这张图必须真的插了自动层节点，否则本用例什么都没验证"
    for node in auto:
        assert "items_completed" not in node
        assert "items_failed" not in node
        assert "items_running" not in node
        assert "item_states" not in node


# --- 重跑：计数与 per-item 状态必须一并清零 --------------------------------


@pytest.mark.asyncio
async def test_foreach_counts_reset_on_route_loop_back(manager):
    """route 回边重跑同一个 foreach 容器不能累加成 ``M > N``（grill 决策 3）。

    构造是 peer-review 形状：``fan -> reviewer -> gate``，gate 的 default 指向
    ``fan``（review 循环）。第一轮 reviewer 给 CRITIQUE → 回边重跑整个 fan；
    第二轮给 APPROVED → 收敛。回边重跑走的就是 ``_execute_foreach`` 的第二次展开。
    """

    class _LoopLLM:
        """按任务首行分派：reviewer 第一轮 CRITIQUE、第二轮 APPROVED。"""

        def __init__(self):
            self.reviews = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            first = messages[-1].content.splitlines()[0].strip().lower()
            if first.startswith("review"):
                self.reviews += 1
                verdict = "APPROVED looks good" if self.reviews >= 2 else "CRITIQUE needs work"
                return LLMResponse(content=verdict, stop_reason="end_turn", usage=Usage(5, 5))
            return LLMResponse(content="item done", stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = _LoopLLM()
    spec = {
        "goal": "loop",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "item {item}", "items": ["a", "b"]},
            {"id": "reviewer", "kind": "subagent", "task": "review the drafts"},
            {"id": "gate", "kind": "route", "max_routes": 3,
             "cases": [{"when": "APPROVED", "to": "done"}], "default": "fan"},
            {"id": "done", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "fan", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "fan"},
        ],
        # 回边目标（fan）必须显式声明入口——隐式入口推不出来。
        "entry": ["fan"],
        "terminal": ["done"],
    }
    scheduler = _scheduler(manager, spec)

    # 在每个**项完成回调**处采样：这是计数的真实推进点（M2.1 的记账点）。
    seen_totals = []
    original_done = scheduler._on_foreach_item_done

    def _spy(state, index, task):
        original_done(state, index, task)
        seen_totals.append(
            (state.items_completed, state.items_failed, list(state.item_states),
             len(state.item_runs))
        )

    scheduler._on_foreach_item_done = _spy  # type: ignore[method-assign]
    await scheduler.run(scheduler.spec)

    # 回边重跑 = 第二次展开 = 4 次项完成回调（2 项 × 2 轮）。
    assert len(seen_totals) >= 4, f"回边没有触发第二次展开：{len(seen_totals)} 次回调"
    for completed, failed, item_states, slot_count in seen_totals:
        assert completed + failed <= 2, (
            f"计数在回边重跑时累加了：completed={completed} failed={failed}"
        )
        assert len(item_states) == 2
        assert slot_count == 2, "item_runs 必须在重新展开时重置为新的槽列表"
    # 第二轮的第一项完成时计数必须从 1 开始（不是 3）——这才是「归零」的直接证据。
    assert seen_totals[2][0] == 1, seen_totals


# --- G2：项级推帧 + 调度器侧限频 -------------------------------------------


@pytest.mark.asyncio
async def test_item_transitions_emit_frames(manager):
    """项级迁移要推帧，否则计数对了前端仍收不到（G2）。

    推帧还必须**在调度器侧限频**：``workflow_graph_snapshot()`` 是全量重建，
    0.1s 合并窗只合并发送、不合并构建。所以帧数要远少于项数。
    """
    manager.max_active = 2
    manager.llm = SlowLLM(delay=0.002)
    scheduler = _scheduler(manager, _foreach_spec(count=12))

    frames = []
    manager.graph_sink = lambda event_type, data: frames.append((event_type, data))

    await scheduler.run(scheduler.spec)

    snapshots = [data for event_type, data in frames if event_type == "workflow_snapshot"]
    assert len(snapshots) > 3, f"项级迁移没有推帧（只有 {len(snapshots)} 帧）"
    # 12 项 × 2 次迁移 = 24 次潜在构建；限频后必须显著少于它。
    assert len(snapshots) < 24, f"项级推帧没有限频：{len(snapshots)} 帧"


@pytest.mark.asyncio
async def test_final_frame_has_final_counts(manager):
    """限频只合并构建、不能吞掉尾帧：收敛帧必须带最终计数。"""
    manager.max_active = 4
    manager.llm = SlowLLM(delay=0.001)
    scheduler = _scheduler(manager, _foreach_spec(count=5))

    frames = []
    manager.graph_sink = lambda event_type, data: frames.append((event_type, data))
    await scheduler.run(scheduler.spec)

    last = [data for event_type, data in frames if event_type == "workflow_snapshot"][-1]
    fan = next(node for node in last["nodes"] if node["id"] == "fan")
    assert fan["items_completed"] == 5
    assert fan["items_running"] == 0

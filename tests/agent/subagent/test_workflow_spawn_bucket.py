"""D8 计数桶：workflow run = 一个 spawn 桶（grill Q6）。

- 桶键 = ``workflow_id``（不是 root_run_id —— 该字段无载体）；
- 一个 workflow run 一个桶：两个 foreach 共享同一上限；
- 嵌套 workflow 各自独立桶（B 的消耗不影响 A）；
- 无 workflow 的主 loop 沿用 C1 的 manager 生命周期保守语义。
"""
import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.context import reset_workflow_id, set_workflow_id
from agent.subagent.manager import SubAgentManager
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))


def _manager(tmp_path, **kwargs) -> SubAgentManager:
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        **kwargs,
    )


def test_no_workflow_context_keeps_manager_lifetime_semantics(tmp_path):
    manager = _manager(tmp_path, max_spawns=2)
    manager.create_subagent(name="one")  # 1
    manager.create_subagent(name="two")  # 2
    assert manager.spawn_count() == 2
    with pytest.raises(RuntimeError, match="spawn budget"):
        manager.create_subagent(name="three")


def test_workflow_bucket_is_keyed_by_workflow_id(tmp_path):
    manager = _manager(tmp_path, max_spawns=200)
    manager.register_workflow_bucket("wf_a", limit=3)
    manager.register_workflow_bucket("wf_b", limit=3)

    token = set_workflow_id("wf_a")
    try:
        manager.create_subagent(name="a1")
        manager.create_subagent(name="a2")
        assert manager.spawn_count() == 2
    finally:
        reset_workflow_id(token)
    # b 的桶不受 a 消耗影响（嵌套 workflow 独立桶）
    token = set_workflow_id("wf_b")
    try:
        assert manager.spawn_count() == 0
        manager.create_subagent(name="b1")
        assert manager.spawn_count() == 1
    finally:
        reset_workflow_id(token)
    # 回到 a：桶继续累计
    token = set_workflow_id("wf_a")
    try:
        manager.create_subagent(name="a3")  # 3/3
        with pytest.raises(RuntimeError, match="wf_a"):
            manager.create_subagent(name="a4")
    finally:
        reset_workflow_id(token)


def test_bucket_is_released_after_the_workflow_run(tmp_path):
    manager = _manager(tmp_path, max_spawns=1)
    manager.register_workflow_bucket("wf_x", limit=1)
    token = set_workflow_id("wf_x")
    try:
        manager.create_subagent(name="one")
        with pytest.raises(RuntimeError, match="spawn budget"):
            manager.create_subagent(name="two")
    finally:
        reset_workflow_id(token)
    # 桶释放后同名 workflow 重新起算（不污染其它 workflow / 主 loop）
    manager.release_workflow_bucket("wf_x")
    assert manager.spawn_count() == 0
    manager.create_subagent(name="main-loop")  # 落在 manager 生命周期桶


@pytest.mark.asyncio
async def test_two_foreach_in_one_workflow_share_one_bucket(tmp_path):
    """Q6 场景 B：一个 workflow run = 一个桶，两个 foreach 共享上限。

    判别方式是「只注册了一个桶」+「两个 foreach 的 spawn 都记在它名下」：
    若每个 foreach 各开一个桶，第二次 register 会覆盖计数、上限被放大到 2 倍。
    """
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec

    manager = _manager(tmp_path, max_spawns=1000)
    registered: list[tuple[str, int]] = []
    original_register = manager.register_workflow_bucket

    def _spy(workflow_id: str, limit: int) -> None:
        registered.append((workflow_id, limit))
        original_register(workflow_id, limit)

    manager.register_workflow_bucket = _spy  # type: ignore[method-assign]
    peak_used = 0
    original_count = manager._count_spawn

    def _counting() -> None:
        nonlocal peak_used
        original_count()
        peak_used = max(peak_used, manager.spawn_count())

    manager._count_spawn = _counting  # type: ignore[method-assign]

    spec = parse_workflow_spec(
        {
            "goal": "two foreach",
            "nodes": [
                {
                    "id": "first",
                    "kind": "foreach",
                    "task": "a {item}",
                    "items": ["1", "2"],
                    "outputs": ["items"],
                },
                {
                    "id": "second",
                    "kind": "foreach",
                    "task": "b {item}",
                    "items": ["1", "2"],
                    "outputs": ["items"],
                },
                {
                    "id": "join",
                    "kind": "aggregate",
                    "join": "all_required",
                    "strategy": "collect",
                },
            ],
            "edges": [
                {"from": "first", "to": "second"},
                {"from": "first", "to": "join", "reducer": "concat"},
                {"from": "second", "to": "join", "reducer": "concat"},
            ],
            "max_runs": 100,
        }
    )
    scheduler = WorkflowScheduler(manager)
    envelope = await scheduler.run(spec)
    assert envelope["status"] == "completed"
    assert envelope["completed"] == 4
    # 整张图只开了一个桶（两个 foreach 共享），键是 workflow_id
    assert len(registered) == 1
    assert registered[0][0] == envelope["workflow_id"]
    # 4 个展开项 × (create 1 + run 1) = 8 次 spawn，全部记在这一个桶里
    assert peak_used == 8
    # 桶已释放，主 loop 计数未被污染
    assert manager.spawn_count() == 0


@pytest.mark.asyncio
async def test_workflow_bucket_limit_is_calibrated_above_max_runs(tmp_path):
    """桶上限 = max_runs * 2，避免「图还没跑完 spawn 预算先耗尽」。"""
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec

    manager = _manager(tmp_path, max_spawns=2)  # 故意设得很低
    spec = parse_workflow_spec(
        {
            "goal": "g",
            "nodes": [
                {"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(3)
            ],
            "edges": [],
            "max_runs": 10,
        }
    )
    envelope = await WorkflowScheduler(manager).run(spec)
    # workflow 桶（20）远高于 manager 的 max_spawns（2），所以不会误伤
    assert envelope["status"] == "completed"
    assert envelope["completed"] == 3

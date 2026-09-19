"""三模式端到端（change ``benchmark-workflow-replay``，tasks 1.2/1.3/5.1/5.2）。

覆盖 template / dynamic-record / dynamic-replay 三条运行路径的 round-trip 与
record→replay 可比性断言（grill Q6 乙：fake 全等、真实 LLM 只断 spec_hash）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy
from benchmarks.agent_runner import AsterwyndRunner
from benchmarks.models import TaskResult
from benchmarks.task_schema import TaskSpec
from benchmarks.workflow_e2e import (
    MODE_FAKE,
    MODE_NOT_EXECUTED,
    MODE_REAL_LLM,
    compare_record_and_replay,
    e2e_fields,
)
from benchmarks.workflow_replay import (
    COLLECTION_STATUS_MISSING,
    COLLECTION_STATUS_OK,
    read_workflow_record,
    write_workflow_record,
)


class CountingLLM:
    def __init__(self, content="worker result", latency: float = 0.0):
        self.content = content
        self.calls = 0
        self.latency = latency

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        if self.latency:
            # 真实 LLM 必然在此让出事件循环；并发路径的竞态只有让出后才暴露。
            await asyncio.sleep(self.latency)
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


def _task(task_id: str = "t1") -> TaskSpec:
    return TaskSpec(
        id=task_id,
        repo="local",
        base_commit="abc",
        problem_statement_file="issue.md",
        test_command="true",
    )


def _manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=CountingLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- template 模式（Q8 读法 1） --------------------------------------------


@pytest.mark.asyncio
async def test_template_mode_runs_pattern_and_reports_orchestration(tmp_path):
    runner = AsterwyndRunner(
        llm=CountingLLM(),
        workflow_mode="template",
        template_pattern="orchestrator-worker",
        config=AsterwyndConfig(),
    )
    from agent.trace_recorder import TraceRecorder

    result = await runner.run(
        task=_task(),
        problem_statement="Do the thing",
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        trace=TraceRecorder(task_id="t1"),
    )

    assert result.workflow_mode == "template"
    assert result.workflow_spec_hash  # pattern 编译出的 spec 是可哈希的
    assert result.scheduler_version == "workflow.v1"
    assert result.workflow_node_count and result.workflow_node_count >= 1
    assert result.workflow_collection_status == "ok"
    # template 走既有 verifier 判分（Q8 读法 1）：agent 侧状态**不是** replayed
    assert result.status == "completed"


# --- dynamic-record 旁路采集 ------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_record_writes_record_and_does_not_interrupt(tmp_path):
    """记录是旁路：模型自由生成不被阻断，落盘 schema 是 workflows 列表。"""
    manager = _manager(tmp_path)
    runner = AsterwyndRunner(
        llm=CountingLLM(),
        workflow_mode="dynamic-record",
        config=AsterwyndConfig(),
        model="deepseek-v4-flash",
        temperature=0.0,
        seed=7,
    )
    # 模拟「模型自由生成并跑完一张图」：直接驱动调度器，等价于工具层做的那件事。
    await _drive_fanout(manager)

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    fields = runner._collect_workflow_fields(manager, output_dir)

    record = read_workflow_record(output_dir)
    assert record is not None
    assert record["workflow_mode"] == "dynamic-record"
    assert record["collection_status"] == COLLECTION_STATUS_OK
    assert len(record["workflows"]) == 1
    entry = record["workflows"][0]
    assert entry["model"] == "deepseek-v4-flash"
    assert entry["temperature"] == 0.0
    assert entry["seed"] == 7
    assert entry["observed"]["run_count"] == 3
    assert entry["observed"]["node_count"] == 4
    assert entry["observed"]["status"] == "completed"
    # 采集出的字段与记录同源
    assert fields["workflow_spec_hash"] == entry["workflow_spec_hash"]
    assert fields["workflow_run_count"] == 3
    assert fields["workflow_redundancy"] == pytest.approx(3 / 6)


@pytest.mark.asyncio
async def test_dynamic_record_without_workflow_reports_no_workflow(tmp_path):
    runner = AsterwyndRunner(
        llm=CountingLLM(), workflow_mode="dynamic-record", config=AsterwyndConfig()
    )
    manager = _manager(tmp_path)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    fields = runner._collect_workflow_fields(manager, output_dir)

    assert fields["workflow_collection_status"] == "no_workflow"
    assert fields["workflow_count"] == 0
    assert read_workflow_record(output_dir)["workflows"] == []


# --- dynamic-replay 离线重放 ------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_replay_reproduces_spec_hash_and_skips_planner(tmp_path):
    """replay 不跑规划模型，但 spec_hash 必然相等（Q6：唯一可硬断言的字段）。"""
    from agent.trace_recorder import TraceRecorder

    record_dir = tmp_path / "record-run"
    task_dir = record_dir / "tasks" / "t1"
    task_dir.mkdir(parents=True)
    source = _manager(tmp_path)
    envelope = await _drive_fanout(source)
    write_workflow_record(
        task_dir,
        {
            "workflow_mode": "dynamic-record",
            "collection_status": COLLECTION_STATUS_OK,
            "workflows": [
                {
                    "workflow_id": envelope["workflow_id"],
                    "workflow_spec_hash": envelope["spec_hash"],
                    "scheduler_version": "workflow.v1",
                    "spec": parse_workflow_spec(_fanout_spec()).to_dict(),
                    # issue #196：预算默认不限，合成记录用 0 与新默认口径一致
                    "budget_config": {"max_total_runs": 0},
                    "seed": 7,
                    "model": "deepseek-v4-flash",
                    "temperature": 0.0,
                    "observed": {
                        "node_count": 4,
                        "run_count": 3,
                        "status": "completed",
                    },
                }
            ],
        },
    )

    llm = CountingLLM()
    runner = AsterwyndRunner(
        llm=llm,
        workflow_mode="dynamic-replay",
        workflow_record=record_dir,
        config=AsterwyndConfig(),
    )
    result = await runner.run(
        task=_task(),
        problem_statement="ignored: replay does not run the planner",
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        trace=TraceRecorder(task_id="t1"),
    )

    assert result.workflow_mode == "dynamic-replay"
    assert result.workflow_spec_hash == envelope["spec_hash"]
    assert result.scheduler_version == "workflow.v1"
    assert result.workflow_collection_status == COLLECTION_STATUS_OK
    # replay 只比编排、不判分（Q10 读法 A）
    assert result.status == "replayed"
    # 每条节点 run 仍真实调用 LLM（replay 只省掉规划那一次调用）
    assert llm.calls == 3


@pytest.mark.asyncio
async def test_dynamic_replay_missing_record_is_reported_not_silent(tmp_path):
    from agent.trace_recorder import TraceRecorder

    runner = AsterwyndRunner(
        llm=CountingLLM(),
        workflow_mode="dynamic-replay",
        workflow_record=tmp_path / "empty-run",
        config=AsterwyndConfig(),
    )
    result = await runner.run(
        task=_task(),
        problem_statement="x",
        workspace=tmp_path,
        output_dir=tmp_path / "out",
        trace=TraceRecorder(task_id="t1"),
    )

    assert result.status == "replayed"
    assert result.workflow_collection_status == COLLECTION_STATUS_MISSING


def _nodes(n: int, prefix: str) -> list[dict]:
    return [
        {"id": f"{prefix}{i}", "kind": "subagent", "task": f"{prefix}-task-{i}"}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_parallel_replay_does_not_cross_contaminate_spec_hash(tmp_path):
    """回归：并发重放时每个任务必须报**自己的** spec_hash。

    ``BenchmarkRunner`` 只持有一个 ``AsterwyndRunner``，而 ``run_all`` 用
    ``asyncio.gather`` 并发跑任务——把「本任务的记录」放在 runner 实例属性上，先起
    但跑得久的那个任务会在自己的采集点上读到兄弟任务刚写进去的记录，报出别人的
    hash。

    这里让 taskA（3 个节点）比 taskB（1 个节点）慢，制造「A 先起、B 先完、A 才读」
    的交错——正是实例属性方案会读到 B 的那条路径。节点的 LLM 调用带固定延时，
    交错由事件循环的 await 点保证，不依赖真实网络。
    """
    from agent.trace_recorder import TraceRecorder

    record_dir = tmp_path / "record-run"
    # taskA 的记录里有**两张**图、taskB 只有一张：「本任务的记录」被兄弟任务覆盖时，
    # workflow_count 立刻暴露（甲读到 1 而非 2）。
    specs = {
        "taskA": [
            {"goal": "goal-A1", "nodes": _nodes(2, "a"), "edges": []},
            {"goal": "goal-A2", "nodes": _nodes(1, "c"), "edges": []},
        ],
        "taskB": [{"goal": "goal-B", "nodes": _nodes(1, "b"), "edges": []}],
    }
    expected: dict[str, str] = {}
    for task_id, spec_dicts in specs.items():
        parsed = [parse_workflow_spec(s) for s in spec_dicts]
        expected[task_id] = parsed[0].spec_hash
        write_workflow_record(
            record_dir / "tasks" / task_id,
            {
                "workflow_mode": "dynamic-record",
                "collection_status": COLLECTION_STATUS_OK,
                "workflows": [
                    {
                        "workflow_spec_hash": p.spec_hash,
                        "scheduler_version": "workflow.v1",
                        "spec": p.to_dict(),
                        "observed": {},
                    }
                    for p in parsed
                ],
            },
        )

    runner = AsterwyndRunner(
        llm=CountingLLM(latency=0.05),
        workflow_mode="dynamic-replay",
        workflow_record=record_dir,
        config=AsterwyndConfig(),
    )

    async def one(task_id: str):
        return await runner.run(
            task=_task(task_id),
            problem_statement="x",
            workspace=tmp_path,
            output_dir=tmp_path / f"out-{task_id}",
            trace=TraceRecorder(task_id=task_id),
        )

    results = dict(zip(("taskA", "taskB"), await asyncio.gather(one("taskA"), one("taskB"))))

    for task_id, spec_hash in expected.items():
        assert results[task_id].workflow_spec_hash == spec_hash, task_id
    # 「本任务的记录」必须按任务隔离：taskA 两张图、taskB 一张。
    assert results["taskA"].workflow_count == 2
    assert results["taskB"].workflow_count == 1


# --- 回归：declared 态图不得顶掉真实图的编排指标 --------------------------


@pytest.mark.asyncio
async def test_declared_graph_does_not_shadow_metrics_of_the_graph_that_ran(tmp_path):
    """回归：注册顺序里排第一的 ``declared`` 图不能顶掉真正跑过那张图的指标。

    ``DeclareWorkflow`` 只注册不执行（grill Q1 场景里这很常见），而
    ``_envelope_fields`` 按注册顺序取「第一张」——不过滤 ``declared`` 会让全部
    编排字段静默变 ``None``，尽管同一份记录里数据是完整的。
    """
    from agent.subagent.scheduler import WorkflowScheduler

    manager = _manager(tmp_path)
    declared = WorkflowScheduler(manager)  # 只注册、不 run
    manager.register_workflow(declared)
    await _drive_fanout(manager)

    runner = AsterwyndRunner(
        llm=CountingLLM(), workflow_mode="dynamic-record", config=AsterwyndConfig()
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    fields = runner._collect_workflow_fields(manager, output_dir)

    assert len(read_workflow_record(output_dir)["workflows"]) == 1
    assert fields["workflow_node_count"] == 4
    assert fields["workflow_run_count"] == 3
    assert fields["workflow_envelope"]["status"] == "completed"


@pytest.mark.asyncio
async def test_template_mode_does_not_write_a_replay_record(tmp_path):
    """template 的编排由 pattern 名唯一确定、无重放需求 → 不落盘记录。

    运行协议文档与模块 docstring 都这么写；实现若顺手落盘会留下没人读的
    ``workflow_record.json``，且让人误以为 template 也能 replay。
    """
    from agent.trace_recorder import TraceRecorder

    runner = AsterwyndRunner(
        llm=CountingLLM(), workflow_mode="template", config=AsterwyndConfig()
    )
    output_dir = tmp_path / "out"
    await runner.run(
        task=_task(),
        problem_statement="do the thing",
        workspace=tmp_path,
        output_dir=output_dir,
        trace=TraceRecorder(task_id="t1"),
    )

    assert not (output_dir / "workflow_record.json").exists()


@pytest.mark.asyncio
async def test_run_task_seed_reaches_the_record(tmp_path):
    """回归：``--seeds`` 的 seed 必须进 ``workflow_record.json``（D2 schema 必填项）。

    ``AgentRunner.run`` 的五参签名按 Q8 不动，seed 只能由 ``BenchmarkRunner``
    在每次 run 前交给 agent runner——走完整的 ``run_task`` 路径才测得到这条接线；
    只调 ``set_run_seed`` 会漏掉「没人调用它」这个真实缺陷（schema 里的 seed 恒为
    None）。
    """
    from benchmarks.runner import BenchmarkRunner

    source_repo = _git_repo(tmp_path / "source")
    task_dir = tmp_path / "tasks" / "t1"
    task_dir.mkdir(parents=True)
    head = _git(source_repo, "rev-parse", "HEAD")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "t1",
                "repo": "local",
                "base_commit": head,
                "problem_statement_file": "issue.md",
                "test_command": "true",
            }
        )
    )
    (task_dir / "issue.md").write_text("do it")

    agent_runner = AsterwyndRunner(
        llm=CountingLLM(), workflow_mode="dynamic-record", config=AsterwyndConfig()
    )
    runner = BenchmarkRunner(
        agent_runner=agent_runner,
        source_repo=source_repo,
        runs_dir=tmp_path / "runs",
        agent_name="fake",
        workflow_mode="dynamic-record",
    )

    assert agent_runner.seed is None
    await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "r1", seed=5)

    # seed 必须由 BenchmarkRunner 经 set_run_seed 落到 agent runner 上（它随后进
    # workflow_record.json 的 seed 字段）。
    assert agent_runner.seed == 5


# --- 回归：两个真实 LLM e2e 跑出来的 bug ---------------------------------


def test_counting_llm_delegates_model_so_cost_is_not_a_fake_zero():
    """回归（CD14「假 0」）：包装层必须把 ``model`` 透出去。

    不透传时 ledger 记 ``model="unknown"`` → 2 档 ``compute_cost`` 返回 None →
    ``CostLedger.total()`` 恒 0，``workflow_cost_usd`` 是假数据。
    """
    from benchmarks.agent_runner import CountingLLM

    class PricedLLM:
        model = "deepseek-v4-flash"

    counting = CountingLLM(PricedLLM())

    assert counting.model == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_replay_task_result_status_is_replayed(tmp_path):
    """回归：replay 的 ``TaskResult.status`` 必须是 ``replayed`` 而不是默认 error。

    走完整 ``run_task`` 路径（不是只调 ``_annotate_e2e_verification``），否则
    "结果对象没被标成 replayed" 这类缺陷测不出来。
    """
    from benchmarks.runner import BenchmarkRunner

    spec = parse_workflow_spec(_fanout_spec())
    record_dir = tmp_path / "record-run"
    write_workflow_record(
        record_dir / "tasks" / "t1",
        {
            "workflow_mode": "dynamic-record",
            "collection_status": COLLECTION_STATUS_OK,
            "workflows": [
                {
                    "workflow_spec_hash": spec.spec_hash,
                    "scheduler_version": "workflow.v1",
                    "spec": spec.to_dict(),
                    "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
                }
            ],
        },
    )
    source_repo = _git_repo(tmp_path / "source")
    task_dir = tmp_path / "tasks" / "t1"
    task_dir.mkdir(parents=True)
    head = _git(source_repo, "rev-parse", "HEAD")
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "t1",
                "repo": "local",
                "base_commit": head,
                "problem_statement_file": "issue.md",
                "test_command": "true",
            }
        )
    )
    (task_dir / "issue.md").write_text("do it")

    runner = BenchmarkRunner(
        agent_runner=AsterwyndRunner(
            llm=CountingLLM(),
            workflow_mode="dynamic-replay",
            workflow_record=record_dir,
        ),
        source_repo=source_repo,
        runs_dir=tmp_path / "runs",
        agent_name="fake",
        workflow_mode="dynamic-replay",
        workflow_record_dir=record_dir,
    )

    result = await runner.run_task(task_dir, run_dir=tmp_path / "runs" / "r1")

    assert result.status == "replayed"
    assert result.workflow_mode == "dynamic-replay"
    assert result.workflow_spec_hash == spec.spec_hash


# --- 5.1 record → replay 可比性断言（Q6） -----------------------------------


def test_fake_round_trip_asserts_full_equality():
    record_entry = {
        "workflow_spec_hash": "abc",
        "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
    }
    replay = {
        "workflow_spec_hash": "abc",
        "node_count": 4,
        "run_count": 3,
        # 图级状态（不是 benchmark 的 ``replayed`` 专值）：见
        # ``test_fake_status_assertion_compares_workflow_status_not_task_status``。
        "workflow_status": "completed",
        "peak_active": 9,  # wall-clock/并发噪声：fake 场景也不进硬断言
        "cost_usd": 0.0,
        "critical_path_s": 999.0,
    }

    assertions = compare_record_and_replay(record_entry, replay, fake_llm=True)

    assert assertions["all_hard_assertions_passed"]
    assert "node_count" in assertions["hard_asserted"]
    assert "run_count" in assertions["hard_asserted"]
    assert "status" in assertions["hard_asserted"]
    # 真实 LLM 侧只报不判的字段在 fake 场景同样只报
    assert "peak_active" in assertions["reported_only"]


def test_fake_status_assertion_compares_workflow_status_not_task_status():
    """回归：``status`` 硬断言必须比**图级状态**，不能比 benchmark 的 ``replayed``。

    replay 侧的 ``TaskResult.status`` 被 Q10 读法 A 固定成 ``replayed``，与 record
    侧 envelope 的 ``completed`` 永远不可能等值——拿它做全等断言则断言恒假。真实
    run 喂进来的就正是这两个值。
    """
    record_entry = {
        "workflow_spec_hash": "abc",
        "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
    }
    replay = {
        "workflow_spec_hash": "abc",
        "node_count": 4,
        "run_count": 3,
        "workflow_status": "completed",
    }

    assertions = compare_record_and_replay(record_entry, replay, fake_llm=True)

    assert assertions["comparisons"]["status"]["equal"] is True
    assert assertions["all_hard_assertions_passed"]


def test_fake_status_assertion_fails_when_replay_did_not_reproduce_record():
    """回归：record 正常完成而 replay 异常时，status 断言必须失败（不能恒真）。"""
    record_entry = {
        "workflow_spec_hash": "abc",
        "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
    }
    replay = {
        "workflow_spec_hash": "abc",
        "node_count": 4,
        "run_count": 3,
        "workflow_status": "graph_recursion_exceeded",
    }

    assertions = compare_record_and_replay(record_entry, replay, fake_llm=True)

    assert assertions["comparisons"]["status"]["equal"] is False
    assert not assertions["all_hard_assertions_passed"]


def test_real_llm_round_trip_only_hard_asserts_spec_hash():
    record_entry = {
        "workflow_spec_hash": "abc",
        "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
    }
    replay = {
        "workflow_spec_hash": "abc",
        "node_count": 4,
        "run_count": 5,  # 真实 LLM 下 route/预算会让 run 数漂移
        "status": "completed",
        "cost_usd": 1.23,
    }

    assertions = compare_record_and_replay(record_entry, replay, fake_llm=False)

    assert assertions["hard_asserted"] == ["workflow_spec_hash"]
    assert assertions["all_hard_assertions_passed"]
    assert assertions["reported_only"]["run_count"] == {"record": 3, "replay": 5}


def test_spec_hash_mismatch_fails_the_assertion():
    assertions = compare_record_and_replay(
        {"workflow_spec_hash": "abc", "observed": {}},
        {"workflow_spec_hash": "def"},
        fake_llm=True,
    )
    assert not assertions["all_hard_assertions_passed"]


# --- 5.2 降级策略（Q7 落点 A） ----------------------------------------------


def test_e2e_fields_record_degradation_without_claiming_verification():
    fields = e2e_fields(llm_available=False, skip_reason="no ANTHROPIC_API_KEY")

    assert fields["e2e_llm_verified"] is False
    assert fields["e2e_verification_mode"] == MODE_FAKE
    assert "no ANTHROPIC_API_KEY" in fields["e2e_skip_reason"]


def test_e2e_fields_verified_on_real_llm_and_label_fake_mode():
    real = e2e_fields(llm_available=True, assertions={"all_hard_assertions_passed": True})
    assert real["e2e_llm_verified"] is True
    assert real["e2e_verification_mode"] == MODE_REAL_LLM

    fake = e2e_fields(llm_available=True, fake_llm=True)
    assert fake["e2e_llm_verified"] is False
    assert fake["e2e_verification_mode"] == MODE_FAKE


@pytest.mark.asyncio
async def test_replay_without_record_dir_marks_not_executed(tmp_path):
    """降级不静默：没配 --workflow-record 时写「未执行 + 原因」而不是假装通过。"""
    from benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner(
        agent_runner=AsterwyndRunner(llm=CountingLLM(), workflow_mode="dynamic-replay"),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        agent_name="asterwynd",
        workflow_mode="dynamic-replay",
        workflow_record_dir=None,
    )
    result = TaskResult(task_id="t1", agent="asterwynd", workflow_mode="dynamic-replay")

    annotated = runner._annotate_e2e_verification(result)

    assert annotated.e2e_llm_verified is False
    assert annotated.e2e_verification_mode == MODE_NOT_EXECUTED
    assert annotated.e2e_skip_reason


@pytest.mark.asyncio
async def test_replay_annotates_assertions_from_the_record_run(tmp_path):
    from benchmarks.runner import BenchmarkRunner

    record_dir = tmp_path / "record-run"
    write_workflow_record(
        record_dir / "tasks" / "t1",
        {
            "workflow_mode": "dynamic-record",
            "collection_status": COLLECTION_STATUS_OK,
            "workflows": [
                {
                    "workflow_spec_hash": "abc",
                    "observed": {"node_count": 4, "run_count": 3, "status": "completed"},
                }
            ],
        },
    )
    runner = BenchmarkRunner(
        agent_runner=AsterwyndRunner(llm=CountingLLM()),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        agent_name="fake",
        workflow_mode="dynamic-replay",
        workflow_record_dir=record_dir,
    )
    result = TaskResult(
        task_id="t1",
        agent="fake",
        status="replayed",
        workflow_mode="dynamic-replay",
        workflow_spec_hash="abc",
        workflow_collection_status=COLLECTION_STATUS_OK,
        workflow_node_count=4,
        workflow_run_count=3,
        # 图级状态来自采集到的 envelope（不是 TaskResult.status 的 replayed）。
        workflow_envelope={"status": "completed"},
    )

    annotated = runner._annotate_e2e_verification(result)

    assert annotated.e2e_verification_mode == MODE_FAKE
    assert annotated.e2e_assertions["all_hard_assertions_passed"] is True


def test_unclean_real_llm_replay_is_recorded_as_unverified(tmp_path):
    """降级不静默（Q7）：真实 LLM 侧回放没跑完时不标「已验证」。

    这是「真实 LLM 不可用」在 run 里的唯一可观测形态——replay 会照常为每个节点
    发起真实调用，拿不到 provider 就就地失败。断言不变量：**只有真正无异常完成
    的真实 LLM 回放才配 e2e_llm_verified=True**。
    """
    from benchmarks.runner import BenchmarkRunner, _replay_completed_cleanly

    runner = BenchmarkRunner(
        agent_runner=AsterwyndRunner(llm=CountingLLM()),
        source_repo=tmp_path,
        runs_dir=tmp_path / "runs",
        agent_name="asterwynd",
        workflow_mode="dynamic-replay",
        workflow_record_dir=tmp_path,
    )
    unhealthy = TaskResult(
        task_id="t1",
        agent="asterwynd",
        status="replayed",
        workflow_mode="dynamic-replay",
        workflow_spec_hash="abc",
        workflow_collection_status=COLLECTION_STATUS_OK,
        workflow_envelope={"status": "graph_recursion_exceeded"},
    )

    annotated = runner._annotate_e2e_verification(unhealthy)

    assert annotated.e2e_llm_verified is False
    assert annotated.e2e_verification_mode == MODE_FAKE
    assert "did not complete cleanly" in annotated.e2e_skip_reason
    assert _replay_completed_cleanly(unhealthy) is False
    # envelope 缺失（采集失败）同样保守判未验证
    assert _replay_completed_cleanly(TaskResult(task_id="t", agent="x")) is False
    # 正常完成才算验证过
    healthy = TaskResult(
        task_id="t1", agent="asterwynd", workflow_envelope={"status": "completed"}
    )
    assert _replay_completed_cleanly(healthy) is True


# --- helpers ---------------------------------------------------------------


def _fanout_spec(**overrides) -> dict:
    base = {
        "goal": "research",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "c", "kind": "subagent", "task": "task c"},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "a", "to": "join", "reducer": "concat"},
            {"from": "b", "to": "join", "reducer": "concat"},
            {"from": "c", "to": "join", "reducer": "concat"},
        ],
    }
    base.update(overrides)
    return base


async def _drive_fanout(manager: SubAgentManager) -> dict:
    from agent.subagent.scheduler import WorkflowScheduler

    return await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))


def _git(repo: Path, *args: str) -> str:
    import subprocess

    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _git_repo(path: Path) -> Path:
    """A tiny real git repo: ``run_task`` creates worktrees from it."""
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README.md").write_text("hi\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=path, check=True
    )
    return path

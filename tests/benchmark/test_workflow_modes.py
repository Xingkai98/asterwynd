"""三模式端到端（change ``benchmark-workflow-replay``，tasks 1.2/1.3/5.1/5.2）。

覆盖 template / dynamic-record / dynamic-replay 三条运行路径的 round-trip 与
record→replay 可比性断言（grill Q6 乙：fake 全等、真实 LLM 只断 spec_hash）。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(self, content="worker result"):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
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
    from agent.trace_recorder import TraceRecorder

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
    from agent.trace_recorder import TraceRecorder

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
                    "budget_config": {"max_total_runs": 300},
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
        "status": "completed",
        "peak_active": 9,  # wall-clock/并发噪声：fake 场景也不进硬断言
        "cost_usd": 0.0,
        "critical_path_s": 999.0,
    }

    assertions = compare_record_and_replay(record_entry, replay, fake_llm=True)

    assert assertions["all_hard_assertions_passed"]
    assert "node_count" in assertions["hard_asserted"]
    assert "run_count" in assertions["hard_asserted"]
    # 真实 LLM 侧只报不判的字段在 fake 场景同样只报
    assert "peak_active" in assertions["reported_only"]


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

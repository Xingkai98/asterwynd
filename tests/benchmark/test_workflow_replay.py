"""benchmark 三模式与 workflow 可重放（change ``benchmark-workflow-replay``）。

覆盖 tasks 1.1-1.3 / 2.0-2.3 / 3.1-3.4 / 4.1-4.2 / 5.1-5.2 / 6.1-6.2。
口径以 ``reviews/grill-design.md`` 的 14 条 Confirmed Decisions 与 10 条
``## User Confirmation`` 为准（实现铁律），不是 design.md 的原文。
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
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import SCHEMA_VERSION, parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy
from benchmarks.models import AgentRunResult, TaskResult
from benchmarks.workflow_replay import (
    COLLECTION_STATUS_FAILED,
    COLLECTION_STATUS_NO_WORKFLOW,
    COLLECTION_STATUS_OK,
    WORKFLOW_RECORD_FILENAME,
    collect_workflow_records,
    read_workflow_record,
    write_workflow_record,
)

RECORD_KEYS = {
    "workflow_id",
    "workflow_spec_hash",
    "scheduler_version",
    "spec",
    "budget_config",
    "seed",
    "model",
    "temperature",
}


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


def _manager(tmp_path, llm=None, **kwargs) -> SubAgentManager:
    return SubAgentManager(
        llm=llm or StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        **kwargs,
    )


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


# --- 1.1 workflow_record 落盘 / 读取 ---------------------------------------


def test_record_written_per_task_with_workflows_list(tmp_path):
    """Q1 写法 B：一任务一份文件，顶层是 ``workflows`` 列表（不是单对象）。"""
    task_output = tmp_path / "tasks" / "asterwynd-009"
    task_output.mkdir(parents=True)
    record = {
        "workflow_mode": "dynamic-record",
        "collection_status": COLLECTION_STATUS_OK,
        "workflows": [],
    }

    path = write_workflow_record(task_output, record)

    assert path.name == WORKFLOW_RECORD_FILENAME
    assert path.parent == task_output
    assert json.loads(path.read_text())["workflows"] == []
    assert read_workflow_record(task_output) == record


def test_read_workflow_record_missing_file_returns_none(tmp_path):
    assert read_workflow_record(tmp_path) is None


def test_collect_records_only_running_workflows(tmp_path):
    """``DeclareWorkflow`` 只注册不执行：``declared`` 态的图不得进列表（Q1）。"""
    manager = _manager(tmp_path)
    declared = WorkflowScheduler(manager)
    declared.spec = parse_workflow_spec(_fanout_spec())
    manager.register_workflow(declared)

    records, status, error = collect_workflow_records(manager)

    assert records == []
    assert status == COLLECTION_STATUS_NO_WORKFLOW
    assert error is None


@pytest.mark.asyncio
async def test_collect_records_normalises_spec_and_metadata(tmp_path):
    manager = _manager(tmp_path)
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_fanout_spec()))

    records, status, error = collect_workflow_records(
        manager, model="deepseek-v4-flash", temperature=0.0, seed=42
    )

    assert status == COLLECTION_STATUS_OK
    assert error is None
    assert len(records) == 1
    record = records[0]
    assert RECORD_KEYS <= set(record)
    assert record["workflow_id"] == scheduler.workflow_id
    assert record["scheduler_version"] == SCHEMA_VERSION
    assert record["model"] == "deepseek-v4-flash"
    assert record["temperature"] == 0.0
    assert record["seed"] == 42
    assert record["budget_config"]["max_total_cost_usd"] == pytest.approx(5.0)
    # spec 用 WorkflowSpec.to_dict()，可被 parse_workflow_spec 还原出同一 hash
    restored = parse_workflow_spec(record["spec"])
    assert restored.spec_hash == record["workflow_spec_hash"]


@pytest.mark.asyncio
async def test_collect_records_keeps_declaration_order_for_multiple_workflows(tmp_path):
    """一任务多图：按注册顺序落盘，replay 按序重放（Q1）。"""
    manager = _manager(tmp_path)
    first = WorkflowScheduler(manager)
    await first.run(parse_workflow_spec(_fanout_spec()))
    second = WorkflowScheduler(manager)
    await second.run(parse_workflow_spec(_fanout_spec(goal="second")))

    records, status, _ = collect_workflow_records(manager)

    assert status == COLLECTION_STATUS_OK
    assert [r["workflow_id"] for r in records] == [first.workflow_id, second.workflow_id]
    assert records[0]["workflow_spec_hash"] != records[1]["workflow_spec_hash"]


@pytest.mark.asyncio
async def test_collect_records_reports_failure_with_partial_list(tmp_path):
    """采集异常记 ``failed`` + 原因 + 已采到的部分列表（Q1）。"""
    manager = _manager(tmp_path)
    good = WorkflowScheduler(manager)
    await good.run(parse_workflow_spec(_fanout_spec()))

    class Exploding:
        workflow_id = "wf_boom"
        started = True

        @property
        def spec(self):
            raise RuntimeError("spec unavailable")

    manager._workflows["wf_boom"] = Exploding()

    records, status, error = collect_workflow_records(manager)

    assert status == COLLECTION_STATUS_FAILED
    assert error and "spec unavailable" in error
    assert [r["workflow_id"] for r in records] == [good.workflow_id]


# --- 2.0 CostLedger 注入前提（Confirmed Decision 14） ----------------------


def test_scheduler_reports_zero_cost_without_ledger(tmp_path):
    """未挂 ledger 时成本恒 0——报告必须能区分「没挂 ledger」与「真 0 成本」。"""
    manager = _manager(tmp_path)
    assert manager.cost_ledger is None


# --- 2.1 / 2.2 报告字段 -----------------------------------------------------


def test_task_and_agent_run_result_carry_paired_workflow_fields():
    """两个 dataclass 必须成对增字段，且全部默认 None（三个 runner 不建 manager）。"""
    task = TaskResult(task_id="t", agent="fake")
    run = AgentRunResult()
    for field in (
        "workflow_mode",
        "workflow_spec_hash",
        "scheduler_version",
        "workflow_node_count",
        "workflow_run_count",
        "workflow_peak_active",
        "workflow_queue_wait_s",
        "workflow_critical_path_s",
        "workflow_cost_usd",
    ):
        assert hasattr(task, field) and getattr(task, field) is None, field
        assert hasattr(run, field) and getattr(run, field) is None, field


def test_agent_run_result_workflow_fields_survive_task_result_rebuild():
    """``runner.py`` 的 4 处完整重建点必须带上 workflow_*（CD3）。"""
    agent_result = AgentRunResult(
        status="completed",
        workflow_mode="dynamic-record",
        workflow_spec_hash="abc123",
        scheduler_version="workflow.v1",
        workflow_node_count=4,
        workflow_run_count=3,
        workflow_peak_active=3,
        workflow_queue_wait_s=0.5,
        workflow_critical_path_s=1.25,
        workflow_cost_usd=0.03,
        workflow_collection_status="ok",
        workflow_redundancy=0.5,
    )
    rebuilt = TaskResult(task_id="t", agent="asterwynd")

    rebuilt.apply_agent_run(agent_result)

    assert rebuilt.workflow_mode == "dynamic-record"
    assert rebuilt.workflow_spec_hash == "abc123"
    assert rebuilt.scheduler_version == "workflow.v1"
    assert rebuilt.workflow_node_count == 4
    assert rebuilt.workflow_run_count == 3
    assert rebuilt.workflow_cost_usd == pytest.approx(0.03)
    assert rebuilt.workflow_collection_status == "ok"
    # to_dict 省略 None，但非 None 的 workflow 字段必须落进 result.json
    assert rebuilt.to_dict()["workflow_node_count"] == 4


def test_task_result_from_dict_ignores_unknown_workflow_keys():
    """旧 artifact 向后兼容：未知键静默忽略、缺字段回落默认 None。"""
    parsed = TaskResult.from_dict(
        {"task_id": "t", "agent": "fake", "workflow_unknown_key": 1}
    )
    assert parsed.workflow_mode is None


@pytest.mark.asyncio
async def test_scheduler_envelope_exposes_run_count_and_spawn_snapshot(tmp_path):
    """``run_count`` / spawn 快照必须进 envelope（桶在 finally 释放，事后取不到）。"""
    manager = _manager(tmp_path)
    envelope = await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))

    assert envelope["run_count"] == 3
    # 每个 run 一次 create + 一次 run = 2 次 spawn（manager._count_spawn 口径）
    assert envelope["workflow_spawn_count"] == 6
    assert envelope["queue_wait_s"] is not None
    assert envelope["queue_wait_s"] >= 0.0
    # 桶已释放：事后从 envelope 取不到，必须靠 run() 内快照
    assert manager.spawn_count() == 0


# --- 3.1 冗余度（消费口径） ------------------------------------------------


@pytest.mark.asyncio
async def test_redundancy_counts_only_consumed_runs(tmp_path):
    """分母 = spawn 快照（含 create），分子 = 被下游消费的 run（Q2 消费口径）。"""
    manager = _manager(tmp_path)
    envelope = await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))

    # a/b/c 三个 run 都被 join 的 _collect_slots 读走 → 3 个有用产出
    assert envelope["useful_runs"] == 3
    assert envelope["redundancy"] == pytest.approx(3 / 6)


@pytest.mark.asyncio
async def test_redundancy_is_none_without_spawns(tmp_path):
    """spawn 总数为 0 时记 None 而不是 0（Q2）。"""
    manager = _manager(tmp_path)
    spec = parse_workflow_spec(
        {
            "goal": "pure logic",
            "nodes": [
                {"id": "only", "kind": "aggregate", "join": "all_required", "strategy": "collect"}
            ],
            "edges": [],
        }
    )
    envelope = await WorkflowScheduler(manager).run(spec)

    assert envelope["workflow_spawn_count"] == 0
    assert envelope["redundancy"] is None


# --- 3.2 / 3.3 图级步数与拒绝降级计数 --------------------------------------


@pytest.mark.asyncio
async def test_graph_steps_exposed(tmp_path):
    manager = _manager(tmp_path)
    envelope = await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))
    assert envelope["steps"] == 2  # 一批 a/b/c + 一批 join


@pytest.mark.asyncio
async def test_depth_capped_runs_counted_into_rejected_total(tmp_path):
    """``depth_capped_runs`` 按构造次数计，单列 + 并入总拒绝计数（Q3）。"""
    manager = _manager(tmp_path, max_depth=1)
    envelope = await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))

    assert envelope["depth_capped_runs"] == 3
    assert envelope["rejected_runs"] == 3


@pytest.mark.asyncio
async def test_spawn_budget_rejection_counted(tmp_path):
    """spawn 预算拒绝在 ``_check_spawn_budget`` 的既有 raise 分支自增。"""
    manager = _manager(tmp_path)
    envelope = await WorkflowScheduler(manager).run(parse_workflow_spec(_fanout_spec()))
    # 正常图无拒绝：必须有显式 0，不能只靠键缺失
    assert envelope["spawn_budget_rejected"] == 0
    assert envelope["queue_full_runs"] == 0
    assert envelope["graph_recursion_exceeded"] == 0
    assert envelope["rejected_runs"] == 0


@pytest.mark.asyncio
async def test_graph_recursion_exceeded_counted(tmp_path):
    manager = _manager(tmp_path)
    spec = parse_workflow_spec(
        {
            "goal": "chain",
            "nodes": [
                {"id": "n1", "kind": "subagent", "task": "a"},
                {"id": "n2", "kind": "subagent", "task": "b"},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
            "recursion_limit": 1,
        }
    )
    envelope = await WorkflowScheduler(manager).run(spec)

    assert envelope["status"] == "graph_recursion_exceeded"
    assert envelope["graph_recursion_exceeded"] == 1
    assert envelope["rejected_runs"] == 1


@pytest.mark.asyncio
async def test_queue_wait_uses_max_and_excludes_cancelled(tmp_path):
    """``queue_wait_s`` 聚合用 max；``started_at is None`` 的取消 run 不计入（Q4）。"""
    manager = _manager(tmp_path)
    scheduler = WorkflowScheduler(manager)
    envelope = await scheduler.run(parse_workflow_spec(_fanout_spec()))

    waits = [r.started_at - r.created_at for r in scheduler._run_refs if r.started_at]
    assert waits
    assert envelope["queue_wait_s"] == pytest.approx(max(waits))
    assert envelope["queue_cancelled_runs"] == 0


@pytest.mark.asyncio
async def test_queue_cancelled_runs_counted_separately_from_rejections(tmp_path):
    """取消的排队 run 单列、**不并入**拒绝总量（Q4：两者语义相反）。"""
    manager = _manager(tmp_path)
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_fanout_spec()))

    # 模拟一个「排上队、未开跑就被取消」的 run record
    cancelled = SimpleNamespace(started_at=None, created_at=0.0, status="cancelled")
    scheduler._run_refs.append(cancelled)

    assert scheduler._queue_cancelled_runs() == 1
    assert scheduler._rejected_runs() == 0


@pytest.mark.asyncio
async def test_replay_is_deterministic_across_two_runs(tmp_path):
    """同 spec 两次重放结果可比：结构字段全等（Q6 的可重放前提）。"""
    manager = _manager(tmp_path)
    spec_dict = _fanout_spec()

    first = await WorkflowScheduler(manager).run(parse_workflow_spec(spec_dict))
    second = await WorkflowScheduler(manager).run(parse_workflow_spec(spec_dict))

    assert first["spec_hash"] == second["spec_hash"]
    assert len(first["nodes"]) == len(second["nodes"])
    assert first["run_count"] == second["run_count"]
    assert first["status"] == second["status"]
    assert first["useful_runs"] == second["useful_runs"]
    assert first["redundancy"] == second["redundancy"]


def test_parse_spec_for_manager_is_the_replay_parse_path(tmp_path):
    """replay 必须走 ``parse_spec_for_manager``：否则三闸退回模块常量（CD13）。"""
    from agent.config import SubagentsConfig, WorkflowLimitsConfig
    from agent.subagent.workflow import DEFAULT_MAX_RUNS
    from agent.tools.builtin.subagents import parse_spec_for_manager

    config = AsterwyndConfig(
        subagents=SubagentsConfig(
            workflow=WorkflowLimitsConfig(recursion_limit=7, max_nodes=9, max_runs=11)
        )
    )
    manager = _manager(tmp_path)
    manager.config = config

    spec = parse_spec_for_manager(manager, _fanout_spec())

    assert spec.max_runs == 11
    assert spec.max_nodes == 9
    assert spec.recursion_limit == 7
    assert spec.max_runs != DEFAULT_MAX_RUNS
    # 与裸 parse 的差异正是 replay 必须注入 bounds 的理由
    assert parse_workflow_spec(_fanout_spec()).max_runs == DEFAULT_MAX_RUNS


# --- 报告渲染（Q9 选项 α） --------------------------------------------------


def test_report_renders_workflow_section_separately():
    from benchmarks.report import AggregateRun, render_report

    run = AggregateRun(
        agent="asterwynd",
        model="deepseek-v4-flash",
        repeat=1,
        results=[
            TaskResult(
                task_id="wf-task",
                agent="asterwynd",
                status="passed",
                workflow_mode="dynamic-record",
                workflow_spec_hash="deadbeef",
                scheduler_version="workflow.v1",
                workflow_node_count=4,
                workflow_run_count=3,
                workflow_peak_active=3,
                workflow_queue_wait_s=0.02,
                workflow_critical_path_s=1.5,
                workflow_cost_usd=0.04,
                workflow_collection_status="ok",
                workflow_steps=2,
                workflow_redundancy=0.5,
                workflow_rejected_runs=0,
            ),
            TaskResult(task_id="plain-task", agent="asterwynd", status="passed"),
        ],
    )

    report = render_report(run)

    assert "## Workflow Orchestration" in report
    assert "deadbeef" in report
    # 主表只加一列 workflow_mode，workflow 字段不污染主表
    assert "workflow_mode |" in report
    assert "plain-task" in report


def test_report_renders_without_workflow_results():
    """兼容回归：既有无 workflow 的 benchmark 任务字段为 None，报告不崩。"""
    from benchmarks.report import AggregateRun, render_html, render_report

    run = AggregateRun(
        agent="fake",
        model="",
        repeat=1,
        results=[TaskResult(task_id="plain", agent="fake", status="passed")],
    )
    report = render_report(run)
    assert "## Workflow Orchestration" not in report
    assert "plain" in report
    assert "plain" in render_html(run)


# --- 4.1 比较口径 -----------------------------------------------------------


def test_compare_summary_includes_orchestration_metrics():
    from benchmarks.compare import build_summary

    runs = [
        (
            "asterwynd (dynamic-record)",
            {
                "t1": {
                    "status": "passed",
                    "duration_seconds": 10.0,
                    "model": "deepseek-v4-flash",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "workflow_mode": "dynamic-record",
                    "workflow_node_count": 4,
                    "workflow_peak_active": 3,
                    "workflow_critical_path_s": 8.5,
                    "workflow_cost_usd": 0.02,
                    "workflow_run_count": 3,
                }
            },
        ),
        (
            "asterwynd (template)",
            {
                "t1": {
                    "status": "failed",
                    "duration_seconds": 20.0,
                    "model": "deepseek-v4-flash",
                    "reason": "test_failure",
                    "workflow_mode": "template",
                    "workflow_node_count": 2,
                }
            },
        ),
    ]

    summary = build_summary(runs)

    assert "## Orchestration Metrics" in summary
    assert "$/resolved-task" in summary


def test_compare_html_matches_markdown_orchestration_section():
    """回归：``compare.py`` 一次写 markdown + HTML 两份报告，两份必须都有编排段。

    markdown 侧加了编排段、HTML 侧漏掉的话，同一份 run 的两份报告会互相矛盾
    （HTML 看起来像没跑过 workflow）。两边的表头也必须来自同一份声明。
    """
    from benchmarks.compare import build_html, build_summary

    runs = [
        (
            "arm-small-k",
            {
                "t1": {
                    "status": "passed",
                    "duration_seconds": 1.0,
                    "model": "deepseek-v4-flash",
                    "workflow_mode": "dynamic-record",
                    "workflow_node_count": 4,
                    "workflow_peak_active": 3,
                    "workflow_redundancy": 0.5,
                    "workflow_critical_path_s": 1.2,
                }
            },
        )
    ]

    summary = build_summary(runs)
    page = build_html(runs)

    assert "## Orchestration Metrics" in summary
    assert "Orchestration Metrics" in page
    for column in ("Redundancy (mean)", "$/resolved-task", "Peak concurrency (mean)"):
        assert column in summary, column
        assert f"<th>{column}</th>" in page, column


def test_compare_reads_old_artifacts_without_workflow_keys():
    """raw-dict 宽松读：旧 artifact 缺 workflow 键不得 KeyError。"""
    from benchmarks.compare import build_html, build_summary

    runs = [("legacy", {"t1": {"status": "passed", "duration_seconds": 1.0}})]
    assert "legacy" in build_summary(runs)
    assert "legacy" in build_html(runs)


def test_cost_per_resolved_reuses_pass_statuses():
    """``$/resolved-task`` 分母复用 PASS_STATUSES + is_valid_round（CD9）。"""
    from benchmarks.report import PASS_STATUSES, cost_per_resolved_summary

    results = [
        TaskResult(task_id="a", agent="x", status="passed", input_tokens=1000, output_tokens=0),
        TaskResult(task_id="b", agent="x", status="passed_with_warnings", input_tokens=1000, output_tokens=0),
        TaskResult(task_id="c", agent="x", status="failed", input_tokens=1000, output_tokens=0),
        TaskResult(task_id="d", agent="x", status="unsupported", input_tokens=1000, output_tokens=0),
        TaskResult(task_id="e", agent="x", status="replayed", input_tokens=1000, output_tokens=0),
    ]

    per_resolved, total_cost, resolved = cost_per_resolved_summary(results, model="deepseek-v4-flash")

    assert resolved == 2
    assert per_resolved == pytest.approx(total_cost / 2)
    assert PASS_STATUSES == {"passed", "passed_with_warnings"}


def test_compare_resolved_count_tracks_invalid_round_reasons(monkeypatch):
    """回归（CD9）：compare 侧分母必须**跟着** ``INVALID_ROUND_REASONS`` 走。

    CD9 要求「复用 ``PASS_STATUSES`` + ``is_valid_round``，不得自造」。手抄一份
    原因集在今天是等价的（两边都是那三个），但会在新增无效原因时**静默漂移**——
    compare 的 ``$/resolved-task`` 与 report 的 pass@k 会对不上。这条断言用
    monkeypatch 扩展原因集，验证 compare 自动跟随。
    """
    from benchmarks import compare, statistics
    from benchmarks.statistics import INVALID_ROUND_REASONS

    values = [{"status": "passed", "reason": "boom"}]

    assert compare._resolved_counts(values) == 1
    monkeypatch.setattr(
        statistics, "INVALID_ROUND_REASONS", INVALID_ROUND_REASONS | {"boom"}
    )
    # 归因到新原因后，同一份数据必须不再计入分母（说明它在跟随共享定义）。
    assert statistics.is_valid_round("passed", "boom") is False
    assert compare._resolved_counts(values) == 0



# --- 4.2 对照臂 config ------------------------------------------------------


def test_arm_configs_express_small_k_and_large_n():
    from agent.config import load_config

    small = load_config(config_path=Path("configs/workflow-arm-small-k.yaml"))
    large = load_config(config_path=Path("configs/workflow-arm-large-n.yaml"))

    assert small.subagents.max_active == 3
    assert small.subagents.max_spawns == 60
    assert large.subagents.max_active == 16
    assert large.subagents.max_spawns == 24


# --- 6.2 兼容回归 -----------------------------------------------------------


def test_legacy_task_result_round_trip_adds_no_workflow_keys():
    """旧 artifact 往返：workflow/e2e 字段全部为 None，不新增任何键。"""
    legacy = {"task_id": "t", "agent": "fake", "status": "passed"}
    parsed = TaskResult.from_dict(legacy)
    round_tripped = parsed.to_dict()
    assert {k: v for k, v in round_tripped.items() if k not in legacy} == {
        "mode": "build",
        "model": "",
        "duration_seconds": 0.0,
        "iterations": 0,
        "tool_calls": 0,
        "edit_count": 0,
        "test_runs": 0,
    }
    assert not any(k.startswith("workflow_") or k.startswith("e2e_") for k in round_tripped)

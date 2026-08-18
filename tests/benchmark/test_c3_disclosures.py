"""C3 protocol-reporting disclosure tests.

Covers the spec-mandated disclosure sections on the result page: report
tuple, SWE-bench pollution note, anti-cheat leak disclosure, reason x
fault_owner cross-tab, $/resolved-task + cache hit rate + pricing table
version, f2p/p2p partial success tiers, sampling parameters, small-N
disclaimer, process efficiency (trace contract), and the capability coverage
matrix. Also locks the backward-compat fallback (old run.json -> placeholders,
no crash).
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.disclosure import (
    DisclosureContext,
    collect_trace_events,
    markdown_disclosure_sections,
)
from benchmarks.models import RunMetadata, TaskResult
from benchmarks.report import AggregateRun, render_html, render_report


def _result(
    task_id: str,
    status: str,
    *,
    reason: str | None = None,
    category: str | None = None,
    run_round: int = 0,
    task_family: str | None = None,
    fault_owner: str | None = None,
    partial: dict | None = None,
    temperature: float | None = None,
    seed: int | None = None,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        agent="fake",
        model="deepseek-v4-flash",
        status=status,
        reason=reason,
        category=category,
        run_round=run_round,
        task_family=task_family,
        fault_owner=fault_owner,
        partial=partial,
        temperature=temperature,
        seed=seed,
    )


def _metadata(**overrides) -> RunMetadata:
    base = dict(
        run_id="run-1",
        agent="fake",
        model="deepseek-v4-flash",
        task_set_hash="abc123def456",
        adapter_version="1",
        prompt_version="default",
        network="on",
        max_iterations=20,
        timeout_seconds=600,
        pricing_table_version="2026-08-17",
        temperature=0.2,
        seed=0,
        model_version="v4-flash-20260817",
        swebench_package_version="4.1.0",
        provider="anthropic",
    )
    base.update(overrides)
    return RunMetadata(**base)


# ---------------------------------------------------------------------------
# Report tuple
# ---------------------------------------------------------------------------

def test_report_tuple_section_renders_metadata() -> None:
    ctx = DisclosureContext(metadata=_metadata())
    sections = dict(markdown_disclosure_sections(ctx))
    body = sections["## 报告元组"]
    assert "deepseek-v4-flash" in body
    assert "abc123def456" in body
    assert "pricing_table=2026-08-17" in body
    assert "network=on" in body


def test_report_tuple_falls_back_when_metadata_missing() -> None:
    ctx = DisclosureContext(metadata=None)
    sections = dict(markdown_disclosure_sections(ctx))
    body = sections["## 报告元组"]
    # old run.json: every tuple row renders a placeholder, no crash
    assert "| model | - |" in body
    assert "| task_set_hash | - |" in body


# ---------------------------------------------------------------------------
# Pollution note + anti-cheat
# ---------------------------------------------------------------------------

def test_pollution_note_for_swebench_tasks() -> None:
    results = [
        _result("swebench-1", "passed", task_family="swebench"),
        _result("swebench-2", "failed", reason="test_failure", task_family="swebench"),
    ]
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=results)))
    body = sections["## SWE-bench 污染注记"]
    assert "138" in body
    assert "59.4%" in body
    assert "2026-02" in body
    assert "KNOWN_BAD" in body


def test_pollution_note_placeholder_for_local_only() -> None:
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=[_result("t1", "passed")])))
    assert "不涉及 SWE-bench" in sections["## SWE-bench 污染注记"]


def test_anti_cheat_disclosure_from_manifest() -> None:
    manifest = {
        "anti_cheat_disclosure": {
            "track_a_note": "A 轨历史重建回归基线，非公平评测",
            "source": "本仓库 git 历史",
            "time_range": "2026-06 前",
            "training_cutoff": "未知",
            "positioning": "回归基线",
        }
    }
    sections = dict(markdown_disclosure_sections(DisclosureContext(manifest=manifest)))
    body = sections["## 反作弊泄漏披露"]
    assert "非公平评测" in body
    assert "回归基线" in body


# ---------------------------------------------------------------------------
# Fault owner cross-tab + cost
# ---------------------------------------------------------------------------

def test_fault_owner_cross_section() -> None:
    results = [
        _result("t1", "failed", reason="test_failure", fault_owner="task"),
        _result("t2", "failed", reason="test_failure", fault_owner="agent"),
        _result("t3", "failed", reason="test_failure", fault_owner="task"),
    ]
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=results)))
    body = sections["## reason × fault_owner 交叉表"]
    assert "test_failure" in body
    assert "task" in body
    assert "agent" in body
    assert "2" in body


def test_cost_metrics_section() -> None:
    results = [
        TaskResult(
            task_id="t1", agent="fake", model="deepseek-v4-flash",
            status="passed", input_tokens=1000, output_tokens=500,
            cache_read_tokens=200, cache_write_tokens=50,
        )
    ]
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=results)))
    body = sections["## 成本与定价"]
    assert "$/resolved-task" in body
    assert "cache hit rate" in body
    assert "定价表版本" in body
    assert "仅 LLM token 计费" in body


# ---------------------------------------------------------------------------
# Partial tiers + sampling + small N
# ---------------------------------------------------------------------------

def test_partial_tiers_section() -> None:
    results = [
        _result(
            "swebench-1", "failed", reason="test_failure", task_family="swebench",
            partial={"f2p_rate": 0.5, "p2p_rate": 1.0, "reward": 0.75},
        )
    ]
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=results)))
    body = sections["## 部分成功档（f2p/p2p）"]
    assert "f2p=0.5" in body
    assert "p2p=1.0" in body
    assert "严格 resolved 口径" in body


def test_sampling_section() -> None:
    results = [_result("t1", "passed", temperature=0.2, seed=3)]
    sections = dict(markdown_disclosure_sections(DisclosureContext(metadata=_metadata(), results=results)))
    body = sections["## 采样参数"]
    assert "0.2" in body
    assert "v4-flash-20260817" in body


def test_small_n_section() -> None:
    results = [_result("t1", "passed", run_round=0)]
    sections = dict(markdown_disclosure_sections(DisclosureContext(results=results)))
    assert "小样本声明" in sections["## 小样本声明"]
    assert "N=1" in sections["## 小样本声明"]


def test_small_n_note_counts_valid_rounds_per_task() -> None:
    """Repeat=3 must report N=3, not N=1 (regression for review round 1)."""
    from benchmarks.disclosure import small_n_note

    results = [
        _result("t1", "passed", run_round=0),
        _result("t1", "passed", run_round=1),
        _result("t1", "passed", run_round=2),
        _result("t1", "unsupported", reason="docker_unavailable", run_round=3),
    ]
    assert "N=3–3" in small_n_note(results)


def test_process_efficiency_rows_deduplicated_per_task(tmp_path: Path) -> None:
    """repeat=3 must render each task once, not one identical row per round."""
    run_dir = tmp_path / "run-1"
    _write_trace(
        run_dir,
        "t1",
        [
            {"step": 1, "type": "tool_call", "data": {"tool_name": "Edit"}, "timestamp": 1.0},
            {"step": 2, "type": "tool_result", "data": {"status": "ok"}, "timestamp": 2.0},
        ],
    )
    results = [
        _result("t1", "passed", run_round=0),
        _result("t1", "passed", run_round=1),
        _result("t1", "passed", run_round=2),
    ]
    sections = dict(
        markdown_disclosure_sections(DisclosureContext(results=results, run_dirs=[run_dir]))
    )
    body = sections["## 过程效率"]
    assert body.count("| t1 |") == 1


# ---------------------------------------------------------------------------
# Process efficiency + trace contract (Q15)
# ---------------------------------------------------------------------------

def _write_trace(run_dir: Path, task_id: str, steps: list[dict]) -> Path:
    path = run_dir / "tasks" / task_id / "trace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task_id": task_id, "steps": steps}))
    return path


def test_process_efficiency_section_from_trace(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    _write_trace(
        run_dir,
        "t1",
        [
            {"step": 1, "type": "tool_call", "data": {"tool_name": "Read"}, "timestamp": 1.0},
            {"step": 2, "type": "tool_result", "data": {"status": "ok"}, "timestamp": 2.0},
            {"step": 3, "type": "edit", "data": {"tool_name": "Edit", "status": "ok"}, "timestamp": 4.0},
            {"step": 4, "type": "tool_call", "data": {"tool_name": "Edit"}, "timestamp": 4.0},
            {"step": 5, "type": "tool_result", "data": {"status": "ok"}, "timestamp": 5.0},
        ],
    )
    ctx = DisclosureContext(results=[_result("t1", "passed")], run_dirs=[run_dir])
    sections = dict(markdown_disclosure_sections(ctx))
    body = sections["## 过程效率"]
    assert "t1" in body
    assert "ttf-edit=3.0s" in body  # 4.0 - 1.0
    assert "exploration" in body


def test_process_efficiency_skips_missing_trace() -> None:
    ctx = DisclosureContext(results=[_result("t1", "passed")], run_dirs=[])
    sections = dict(markdown_disclosure_sections(ctx))
    assert "无 trace 数据" in sections["## 过程效率"]


def test_collect_trace_events_reads_recorder_shape(tmp_path: Path) -> None:
    """Lock the trace_recorder -> process_efficiency event contract (Q15)."""
    from agent.trace_recorder import TraceRecorder

    recorder = TraceRecorder(task_id="t1", run_id="agent-run")
    recorder.record("tool_call", tool_name="Read")
    recorder.record("tool_result", status="ok", content="...")
    recorder.record("edit", tool_name="Edit", status="ok", summary="patch")
    run_dir = tmp_path / "run-1"
    trace_path = run_dir / "tasks" / "t1" / "trace.json"
    trace_path.parent.mkdir(parents=True)
    recorder.write_to_file(trace_path)

    events = collect_trace_events([run_dir], "t1")
    assert events, "trace_recorder output must be consumable by collect_trace_events"
    types = {ev["type"] for ev in events}
    assert {"tool_call", "tool_result", "edit"} <= types
    # edit status must be accepted by process_efficiency ("ok"/"success")
    from benchmarks.statistics import process_efficiency

    eff = process_efficiency(events)
    assert eff["time_to_first_successful_edit"] is not None


# ---------------------------------------------------------------------------
# Coverage matrix + integration + backward compat
# ---------------------------------------------------------------------------

def test_coverage_matrix_section() -> None:
    manifest = {
        "capabilities": ["tool-usage", "context-planning"],
        "coverage": {
            "t1": ["tool-usage"],
            "t2": ["tool-usage", "context-planning"],
        },
    }
    sections = dict(markdown_disclosure_sections(DisclosureContext(manifest=manifest)))
    body = sections["## 能力覆盖矩阵"]
    assert "tool-usage" in body
    assert "t1, t2" in body
    assert "context-planning" in body


def test_render_report_aggregate_includes_disclosures() -> None:
    results = [
        _result("swebench-1", "passed", task_family="swebench", run_round=0),
        _result("swebench-1", "failed", reason="test_failure", task_family="swebench", run_round=1),
    ]
    agg = AggregateRun(
        agent="fake",
        model="deepseek-v4-flash",
        repeat=2,
        results=results,
        metadata=[_metadata()],
        manifest={"anti_cheat_disclosure": {"positioning": "回归基线"}},
    )
    md = render_report(agg)
    for heading in (
        "## 报告元组",
        "## SWE-bench 污染注记",
        "## 反作弊泄漏披露",
        "## reason × fault_owner 交叉表",
        "## 成本与定价",
        "## 采样参数",
        "## 小样本声明",
        "## 过程效率",
        "## 能力覆盖矩阵",
    ):
        assert heading in md, f"missing disclosure section {heading}"
    assert "abc123def456" in md


def test_render_report_old_run_compat_no_crash() -> None:
    """Old aggregate without metadata/manifest/run_dirs renders placeholders."""
    results = [_result("t1", "passed", run_round=0), _result("t1", "passed", run_round=1)]
    agg = AggregateRun(agent="fake", model="fake", repeat=2, results=results)
    md = render_report(agg)
    assert "| model | - |" in md
    assert "不涉及 SWE-bench" in md


def test_render_html_includes_disclosures() -> None:
    results = [_result("swebench-1", "passed", task_family="swebench")]
    agg = AggregateRun(
        agent="fake",
        model="deepseek-v4-flash",
        repeat=1,
        results=results,
        metadata=[_metadata()],
        manifest={"anti_cheat_disclosure": {"positioning": "回归基线"}},
    )
    html = render_html(agg)
    for fragment in ("报告元组", "污染注记", "反作弊", "fault_owner", "成本与定价", "采样参数", "小样本声明", "过程效率", "能力覆盖矩阵"):
        assert fragment in html, f"missing HTML disclosure {fragment}"

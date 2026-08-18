"""C3 disclosure rendering for the benchmark result page.

Spec-mandated disclosure sections (``openspec/specs/benchmark/spec.md``):
report tuple, SWE-bench pollution note, anti-cheat leak disclosure,
reason x fault_owner cross-tab, $/resolved-task + cache hit rate + pricing
table version, f2p/p2p partial success tiers, sampling parameters, small-N
disclaimer, process efficiency, and the C1 capability coverage matrix.

Every section tolerates missing fields (old run.json) and renders a fallback
placeholder instead of raising, per the backward-compat requirement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent.cost_tracker import PRICING_TABLE_VERSION, cache_hit_rate
from benchmarks.models import RunMetadata, TaskResult
from benchmarks.statistics import (
    cost_per_resolved,
    fault_owner_cross,
    is_valid_round,
    process_efficiency,
)

# SWE-bench pollution facts (R1 research, 2026-08-17). Kept in one constants
# table with a source/date annotation so a dataset revision updates one place
# instead of a value scattered through the renderers.
SWEBENCH_AUDIT_NOTE = (
    "SWE-bench 存在任务污染风险：经审计的 138 个高失败率实例中 59.4% 有实质缺陷，"
    "OpenAI 已于 2026-02 弃用 SWE-bench 作为评测基准。本结果保留条件域："
    "子集经 KNOWN_BAD 过滤、swebench 实例/包版本钉住（见报告元组），"
    "仅作参考、不当金标准。"
)
SWEBENCH_AUDIT_SOURCE = "R1 调研（2026-08-17）"


@dataclass
class DisclosureContext:
    """Everything the disclosure sections need, all optional for compat."""

    metadata: RunMetadata | None = None
    results: list[TaskResult] = field(default_factory=list)
    manifest: dict | None = None
    run_dirs: list[Path] = field(default_factory=list)


def _fmt(value: object) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _join(*parts: object) -> str:
    present = [str(p) for p in parts if p not in (None, "")]
    return " / ".join(present) if present else "-"


def has_swebench(results: list[TaskResult]) -> bool:
    return any(r.task_family == "swebench" for r in results)


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def report_tuple_rows(meta: RunMetadata | None) -> list[tuple[str, str]]:
    """(label, value) rows for the report-tuple disclosure section.

    Uses ``getattr`` so duck-typed / partial metadata objects (test fakes,
    older artifacts) render placeholders instead of raising.
    """
    if meta is None:
        return [
            ("model", "-"),
            ("harness", "-"),
            ("task_set_hash", "-"),
            ("grader", "-"),
            ("成本口径", "-"),
        ]
    model_cell = _join(
        getattr(meta, "model", None),
        getattr(meta, "model_version", None),
        getattr(meta, "provider", None),
    )
    max_turns = getattr(meta, "max_iterations", None)
    timeout = getattr(meta, "timeout_seconds", None)
    network = getattr(meta, "network", None)
    harness_cell = _join(
        getattr(meta, "adapter_version", None),
        getattr(meta, "prompt_version", None),
        f"max_turns={max_turns}" if max_turns is not None else None,
        f"timeout={timeout}s" if timeout is not None else None,
        f"network={network}" if network else None,
    )
    cost_cell = f"pricing_table={getattr(meta, 'pricing_table_version', None) or '-'}"
    rows = [
        ("model", model_cell),
        ("harness", harness_cell),
        ("task_set_hash", _fmt(getattr(meta, "task_set_hash", None))),
        ("grader", _fmt(getattr(meta, "swebench_package_version", None))),
        ("成本口径", cost_cell),
        ("date", _fmt(getattr(meta, "started_at", None))),
    ]
    if getattr(meta, "truncated", None):
        rows.append(("truncated", "true（预算超限，剩余轮次未运行）"))
    return rows


def anti_cheat_rows(manifest: dict | None) -> list[tuple[str, str]]:
    """Anti-cheat leak disclosure rows from the task-set manifest."""
    acd = (manifest or {}).get("anti_cheat_disclosure") or {}
    if not acd:
        return [("泄漏面", "-"), ("定位", "-")]
    return [
        ("泄漏面", _fmt(acd.get("track_a_note"))),
        ("来源", _fmt(acd.get("source"))),
        ("时间范围", _fmt(acd.get("time_range"))),
        ("训练 cutoff", _fmt(acd.get("training_cutoff"))),
        ("定位", _fmt(acd.get("positioning"))),
    ]


def fault_owner_cross_rows(results: list[TaskResult]) -> list[tuple[str, ...]]:
    """reason x fault_owner cross-tab rows: (reason, owner, count)."""
    cross = fault_owner_cross(results)
    rows: list[tuple[str, ...]] = []
    for reason in sorted(cross):
        for owner in sorted(cross[reason]):
            rows.append((reason, owner, str(cross[reason][owner])))
    return rows


def cost_metrics_rows(results: list[TaskResult]) -> list[tuple[str, str]]:
    per_resolved, total_cost, resolved = cost_per_resolved(results)
    fresh = sum(r.input_tokens or 0 for r in results)
    cache_read = sum(r.cache_read_tokens or 0 for r in results)
    return [
        ("$/resolved-task", f"${per_resolved:.4f}" if per_resolved is not None else "-"),
        ("resolved", _fmt(resolved)),
        ("总成本(LLM token)", f"${total_cost:.4f}"),
        ("cache hit rate", f"{cache_hit_rate(cache_read, fresh):.2%}"),
        ("定价表版本", _fmt(PRICING_TABLE_VERSION)),
        ("计费口径", "仅 LLM token 计费，不含沙箱/CI/计算"),
    ]


def partial_rows(results: list[TaskResult]) -> list[tuple[str, str]]:
    """f2p/p2p partial-success tiers for tasks that carry a ``partial`` dict."""
    rows: list[tuple[str, str]] = []
    for r in results:
        partial = r.partial
        if not partial:
            continue
        detail = _join(
            f"f2p={partial.get('f2p_rate')}" if "f2p_rate" in partial else None,
            f"p2p={partial.get('p2p_rate')}" if "p2p_rate" in partial else None,
            f"reward={partial.get('reward')}" if "reward" in partial else None,
        )
        rows.append((r.task_id, detail))
    return rows


def sampling_rows(meta: RunMetadata | None, results: list[TaskResult]) -> list[tuple[str, str]]:
    temperature = getattr(meta, "temperature", None) if meta is not None else None
    seed = getattr(meta, "seed", None) if meta is not None else None
    model_version = getattr(meta, "model_version", None) if meta is not None else None
    for r in results:
        temperature = temperature if temperature is not None else r.temperature
        seed = seed if seed is not None else r.seed
        break
    return [
        ("temperature", _fmt(temperature)),
        ("seed", _fmt(seed)),
        ("model version", _fmt(model_version)),
    ]


def _unique_task_ids(results: list[TaskResult]) -> list[str]:
    """Task ids in first-seen order, deduplicated across rounds."""
    seen: set[str] = set()
    ordered: list[str] = []
    for r in results:
        if r.task_id not in seen:
            seen.add(r.task_id)
            ordered.append(r.task_id)
    return ordered


def small_n_note(results: list[TaskResult]) -> str:
    by_task: dict[str, int] = {}
    for r in results:
        if is_valid_round(r.status, r.reason):
            by_task[r.task_id] = by_task.get(r.task_id, 0) + 1
    if not by_task:
        return "无任务样本。"
    counts = sorted(by_task.values())
    return (
        f"有效轮次范围 N={counts[0]}–{counts[-1]}；小样本声明：per-task CI 不加权，"
        "仅 layer/aggregate 层展示 CI 权重；N=3–5 时 pass^k 分辨率有限。"
    )


def collect_trace_events(run_dirs: list[Path], task_id: str) -> list[dict]:
    """Concatenate every round's ``trace.json`` steps for ``task_id``."""
    events: list[dict] = []
    for run_dir in run_dirs:
        trace_path = Path(run_dir) / "tasks" / task_id / "trace.json"
        if not trace_path.exists():
            continue
        try:
            data = json.loads(trace_path.read_text())
        except (OSError, ValueError):
            continue
        steps = data.get("steps") if isinstance(data, dict) else None
        if isinstance(steps, list):
            events.extend(s for s in steps if isinstance(s, dict))
    return events


def process_efficiency_rows(
    run_dirs: list[Path],
    task_ids: list[str],
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for task_id in task_ids:
        events = collect_trace_events(run_dirs, task_id)
        if not events:
            continue
        eff = process_efficiency(events)
        ttfe = eff.get("time_to_first_successful_edit")
        rows.append(
            (
                task_id,
                _join(
                    f"ttf-edit={ttfe:.1f}s" if ttfe is not None else "ttf-edit=-",
                    f"exploration={eff.get('exploration_fraction', 0.0):.0%}",
                ),
            )
        )
    return rows


def coverage_rows(manifest: dict | None) -> list[tuple[str, str]]:
    """Capability coverage matrix rows from the C1 manifest."""
    if not manifest:
        return []
    capabilities = manifest.get("capabilities") or []
    coverage = manifest.get("coverage") or {}
    rows: list[tuple[str, str]] = []
    for cap in capabilities:
        tasks = sorted(
            task_id for task_id, caps in coverage.items() if cap in (caps or [])
        )
        rows.append((cap, ", ".join(tasks) if tasks else "-"))
    return rows


# ---------------------------------------------------------------------------
# Markdown sections
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[tuple[str, ...]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["------"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def markdown_disclosure_sections(ctx: DisclosureContext) -> list[tuple[str, str]]:
    """(heading, body) pairs for the markdown result page."""
    sections: list[tuple[str, str]] = []

    tuple_rows = report_tuple_rows(ctx.metadata)
    sections.append(
        (
            "## 报告元组",
            _md_table(["字段", "值"], [tuple(r) for r in tuple_rows]),
        )
    )

    if has_swebench(ctx.results):
        sections.append(
            (
                "## SWE-bench 污染注记",
                f"> {SWEBENCH_AUDIT_NOTE}\n>\n> 来源: {SWEBENCH_AUDIT_SOURCE}\n",
            )
        )
    else:
        sections.append(("## SWE-bench 污染注记", "本任务集不涉及 SWE-bench，无污染披露。\n"))

    sections.append(
        (
            "## 反作弊泄漏披露",
            _md_table(
                ["项", "内容"],
                [tuple(r) for r in anti_cheat_rows(ctx.manifest)],
            ),
        )
    )

    cross = fault_owner_cross_rows(ctx.results)
    if cross:
        sections.append(
            (
                "## reason × fault_owner 交叉表",
                _md_table(["Reason", "fault_owner", "Count"], [tuple(r) for r in cross]),
            )
        )
    else:
        sections.append(("## reason × fault_owner 交叉表", "无失败样本（或未标注）。\n"))

    sections.append(
        (
            "## 成本与定价",
            _md_table(["指标", "值"], [tuple(r) for r in cost_metrics_rows(ctx.results)]),
        )
    )

    partial = partial_rows(ctx.results)
    if partial:
        sections.append(
            (
                "## 部分成功档（f2p/p2p）",
                "严格 resolved 口径 = F2P+P2P 全通过；部分成功字段保留展示。\n\n"
                + _md_table(["Task", "partial"], [tuple(r) for r in partial]),
            )
        )
    else:
        sections.append(
            ("## 部分成功档（f2p/p2p）", "无部分成功字段（旧 run.json 或非 SWE-bench 任务）。\n")
        )

    sections.append(
        (
            "## 采样参数",
            _md_table(
                ["参数", "值"],
                [tuple(r) for r in sampling_rows(ctx.metadata, ctx.results)],
            ),
        )
    )

    sections.append(("## 小样本声明", small_n_note(ctx.results)))

    eff_rows = process_efficiency_rows(ctx.run_dirs, _unique_task_ids(ctx.results))
    if eff_rows:
        sections.append(
            (
                "## 过程效率",
                _md_table(["Task", "指标"], [tuple(r) for r in eff_rows]),
            )
        )
    else:
        sections.append(("## 过程效率", "无 trace 数据（本聚合未提供 run_dirs 或缺 trace.json）。\n"))

    cov_rows = coverage_rows(ctx.manifest)
    if cov_rows:
        sections.append(
            (
                "## 能力覆盖矩阵",
                _md_table(["能力", "覆盖任务"], [tuple(r) for r in cov_rows]),
            )
        )
    else:
        sections.append(("## 能力覆盖矩阵", "无 manifest（未提供或旧格式）。\n"))

    return sections


# ---------------------------------------------------------------------------
# HTML sections
# ---------------------------------------------------------------------------

def _html_table(headers: list[str], rows: list[tuple[str, ...]]) -> str:
    thead = "".join(f"<th>{h}</th>" for h in headers)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>\n"


def html_disclosure_sections(ctx: DisclosureContext) -> list[tuple[str, str]]:
    """(heading, body) pairs for the HTML result page."""
    sections: list[tuple[str, str]] = []

    sections.append(
        ("<h2>报告元组</h2>", _html_table(["字段", "值"], [tuple(r) for r in report_tuple_rows(ctx.metadata)]))
    )
    if has_swebench(ctx.results):
        sections.append(
            ("<h2>SWE-bench 污染注记</h2>", f"<blockquote>{SWEBENCH_AUDIT_NOTE}<br>来源: {SWEBENCH_AUDIT_SOURCE}</blockquote>")
        )
    else:
        sections.append(("<h2>SWE-bench 污染注记</h2>", "<p>本任务集不涉及 SWE-bench，无污染披露。</p>"))

    sections.append(
        ("<h2>反作弊泄漏披露</h2>", _html_table(["项", "内容"], [tuple(r) for r in anti_cheat_rows(ctx.manifest)]))
    )
    cross = fault_owner_cross_rows(ctx.results)
    if cross:
        sections.append(
            ("<h2>reason × fault_owner 交叉表</h2>", _html_table(["Reason", "fault_owner", "Count"], [tuple(r) for r in cross]))
        )
    else:
        sections.append(("<h2>reason × fault_owner 交叉表</h2>", "<p>无失败样本（或未标注）。</p>"))

    sections.append(
        ("<h2>成本与定价</h2>", _html_table(["指标", "值"], [tuple(r) for r in cost_metrics_rows(ctx.results)]))
    )
    partial = partial_rows(ctx.results)
    if partial:
        sections.append(
            ("<h2>部分成功档（f2p/p2p）</h2>",
             "<p>严格 resolved 口径 = F2P+P2P 全通过；部分成功字段保留展示。</p>"
             + _html_table(["Task", "partial"], [tuple(r) for r in partial]))
        )
    else:
        sections.append(("<h2>部分成功档（f2p/p2p）</h2>", "<p>无部分成功字段（旧 run.json 或非 SWE-bench 任务）。</p>"))

    sections.append(
        ("<h2>采样参数</h2>", _html_table(["参数", "值"], [tuple(r) for r in sampling_rows(ctx.metadata, ctx.results)]))
    )
    sections.append(("<h2>小样本声明</h2>", f"<p>{small_n_note(ctx.results)}</p>"))

    eff_rows = process_efficiency_rows(ctx.run_dirs, _unique_task_ids(ctx.results))
    if eff_rows:
        sections.append(("<h2>过程效率</h2>", _html_table(["Task", "指标"], [tuple(r) for r in eff_rows])))
    else:
        sections.append(("<h2>过程效率</h2>", "<p>无 trace 数据（本聚合未提供 run_dirs 或缺 trace.json）。</p>"))

    cov_rows = coverage_rows(ctx.manifest)
    if cov_rows:
        sections.append(("<h2>能力覆盖矩阵</h2>", _html_table(["能力", "覆盖任务"], [tuple(r) for r in cov_rows])))
    else:
        sections.append(("<h2>能力覆盖矩阵</h2>", "<p>无 manifest（未提供或旧格式）。</p>"))

    return sections

"""Quantitative result-page rendering and failure attribution for a benchmark run.

Consumes one aggregated run (one task set run ``repeat`` times) and renders a
markdown report with Pass@k, mean/std, bootstrap confidence intervals, latency
percentiles and token cost, organized by capability layer. Latency and cost
follow the same conventions as ``benchmarks/compare.py``.

The primary aggregation entry points are :func:`collect_run_results` and
:func:`aggregate_results`; :func:`render_report` accepts either the resulting
``list[TaskAggregate]`` or the flattened :class:`AggregateRun` used by the
benchmark CLI.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from agent.cost_tracker import compute_cost, format_cost
from benchmarks.disclosure import (
    DisclosureContext,
    html_disclosure_sections,
    markdown_disclosure_sections,
)
from benchmarks.models import LAYERS, RunMetadata, TaskResult, resolve_layer
from benchmarks.statistics import (
    bootstrap_ci,
    is_valid_round,
    layer_pass_rate,
    mean_std,
    pass_at_k,
    pass_k_success_rate,
)

PASS_STATUSES = {"passed", "passed_with_warnings"}
# unsupported rounds carry no failure signal (invalid rounds are excluded from
# failure attribution and from the fault_owner cross-tab alike).
FAILURE_STATUSES = {"failed", "error"}


@dataclass
class TaskAggregate:
    """All rounds' results for a single task, grouped for aggregation."""

    task_id: str
    category: str
    task_family: str
    results: list[TaskResult] = field(default_factory=list)


@dataclass
class AggregateRun:
    """Flattened results of one task set repeated ``repeat`` times."""

    agent: str
    model: str
    repeat: int
    results: list[TaskResult] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    # C3 protocol-reporting: report-tuple metadata + per-round run dirs +
    # task-set manifest, all optional so older callers keep working.
    metadata: list[RunMetadata] | None = None
    run_dirs: list[Path] | None = None
    manifest: dict | None = None

    def layers(self) -> list[str]:
        present = {resolve_layer(r.category) for r in self.results}
        return [layer for layer in LAYERS if layer in present]


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = min(int(n * p), n - 1)
    return sorted_values[idx]


def _is_pass(result: TaskResult) -> bool:
    return result.status in PASS_STATUSES


def _valid_results(results: list[TaskResult]) -> list[TaskResult]:
    """Drop rounds that carry no pass/fail signal (invalid rounds).

    Invalid rounds (unsupported status / approval-unavailable) never count
    into pass-rate denominators.
    """
    return [r for r in results if is_valid_round(r.status, r.reason)]


def _infer_task_family(result: TaskResult) -> str:
    """Infer a framework family from the task id when the field is missing."""
    family = (result.task_family or "").strip()
    if family:
        return family
    if result.task_id.startswith("swebench-"):
        return "swebench"
    return "local"


def collect_run_results(run_dir: Path) -> list[TaskResult]:
    """Read every ``run_dir/tasks/*/result.json`` back into TaskResult objects.

    A missing or empty tasks directory yields an empty list.
    """
    tasks_dir = Path(run_dir) / "tasks"
    if not tasks_dir.is_dir():
        return []
    results: list[TaskResult] = []
    for task_dir in sorted(tasks_dir.iterdir()):
        result_path = task_dir / "result.json"
        if result_path.exists():
            results.append(TaskResult.from_dict(json.loads(result_path.read_text())))
    return results


def aggregate_results(round_results: list[list[TaskResult]]) -> list[TaskAggregate]:
    """Group results by task id across rounds into :class:`TaskAggregate` objects.

    The category is normalized through ``resolve_layer`` so unknown labels fall
    back to the default ``execution`` layer. The task family prefers the
    result's own ``task_family`` and otherwise infers it from the task id
    (``swebench-`` prefix -> ``swebench``, everything else -> ``local``). Each
    result's ``run_round`` is populated with its round index when unset, so
    downstream failure attribution can report (task, round) look-back samples.
    """
    by_task: dict[str, list[TaskResult]] = defaultdict(list)
    for round_index, round_results in enumerate(round_results):
        for result in round_results:
            if result.run_round is None:
                result.run_round = round_index
            by_task[result.task_id].append(result)

    aggregates: list[TaskAggregate] = []
    for task_id in sorted(by_task):
        results = by_task[task_id]
        first = results[0]
        aggregates.append(
            TaskAggregate(
                task_id=task_id,
                category=resolve_layer(first.category),
                task_family=_infer_task_family(first),
                results=results,
            )
        )
    return aggregates


def failure_attribution(
    aggregates: list[TaskAggregate],
) -> dict[str, list[tuple[str, int | None]]]:
    """Classify failures by ``reason`` into look-back samples.

    Returns ``{reason: [(task_id, round_index), ...]}`` counting only
    ``failed`` / ``error`` results that carry a non-None reason. ``unsupported``
    rounds carry no failure signal and are excluded, matching the
    ``fault_owner_cross`` failure set. Passed results are never counted.
    """
    buckets: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    for aggregate in aggregates:
        for result in aggregate.results:
            if result.status not in FAILURE_STATUSES:
                continue
            if result.reason is None:
                continue
            buckets[result.reason].append((result.task_id, result.run_round))
    return dict(buckets)


def render_report(aggregates: AggregateRun | list[TaskAggregate]) -> str:
    """Render the aggregated run as a markdown report.

    Accepts either the flattened :class:`AggregateRun` produced by the
    benchmark CLI or a ``list[TaskAggregate]`` produced by
    :func:`aggregate_results`. Output order is deterministic: tasks are sorted
    by id and layers follow the canonical ``LAYERS`` order.
    """
    if isinstance(aggregates, AggregateRun):
        return _render(
            aggregate_results([aggregates.results]),
            agent=aggregates.agent,
            model=aggregates.model,
            repeat=aggregates.repeat,
            metadata=aggregates.metadata[0] if aggregates.metadata else None,
            run_dirs=aggregates.run_dirs or [],
            manifest=aggregates.manifest,
        )
    return _render(list(aggregates))


def _render(
    aggregates: list[TaskAggregate],
    *,
    agent: str = "",
    model: str = "",
    repeat: int = 0,
    metadata: RunMetadata | None = None,
    run_dirs: list[Path] | None = None,
    manifest: dict | None = None,
) -> str:
    lines: list[str] = ["# Benchmark Evaluation Report", ""]
    if agent:
        lines.append(
            f"**Agent**: {agent} | **Model**: {model or '-'} | **Rounds**: {repeat}"
        )
        lines.append("")
    lines.append(
        "> 指标语义：**pass@1** = 有效轮经验通过率（用户实际获得）；"
        "**pass@k** = k 次任一成功（能力上限，组合估计）；"
        "**pass^k** = 全部有效轮成功（可靠性）。"
        "无效轮次（unsupported / approval-unavailable / docker-unavailable）不计入分母；"
        "n=k 时仅 pass@1 与 pass^k 有统计意义。"
    )
    lines.append("")

    # ---- Layer-level aggregation -------------------------------------------
    lines.append("## By Capability Layer")
    lines.append("")
    lines.append("| Layer | Tasks | Rounds | Pass Rate | 95% CI | Pass^k |")
    lines.append("|-------|-------|--------|-----------|--------|--------|")
    present_layers = {aggregate.category for aggregate in aggregates}
    for layer in LAYERS:
        if layer not in present_layers:
            continue
        layer_aggregates = [a for a in aggregates if a.category == layer]
        valid = [r for a in layer_aggregates for r in _valid_results(a.results)]
        rounds = [_is_pass(r) for r in valid]
        rate = layer_pass_rate(rounds)
        lo, hi = bootstrap_ci([1.0 if ok else 0.0 for ok in rounds])
        pk_summary = pass_k_success_rate(
            [
                [_is_pass(r) for r in _valid_results(a.results)]
                for a in layer_aggregates
            ]
        )
        pk_str = f"{pk_summary.rate:.2f}" if pk_summary.rate is not None else "n/a"
        lines.append(
            f"| {layer} | {len(layer_aggregates)} | {len(rounds)} | "
            f"{rate:.2f} | [{lo:.2f}, {hi:.2f}] | {pk_str} |"
        )
    lines.append("")

    # ---- Task-level table ---------------------------------------------------
    lines.append("## By Task")
    lines.append("")
    lines.append(
        "| Task | task_family | category | Pass@k | Passes | Pass^k | "
        "Mean(s) | Std(s) | 95% CI | p50 | p95 | p99 | Input Tokens | Output Tokens |"
    )
    lines.append(
        "|------|-------------|----------|--------|--------|--------|"
        "---------|--------|--------|-----|-----|-----|--------------|---------------|"
    )
    for aggregate in aggregates:
        durations = sorted(r.duration_seconds for r in aggregate.results)
        valid = _valid_results(aggregate.results)
        passes = sum(1 for r in valid if _is_pass(r))
        pk = pass_at_k(passes, len(valid))
        # pass^k at task level needs >= 3 valid rounds to be meaningful;
        # below that the cell shows an em-dash ("sample too small").
        if len(valid) >= 3:
            pk_success = "yes" if all(_is_pass(r) for r in valid) else "no"
        else:
            pk_success = "—"
        mean_v, std_v = mean_std(
            [r.duration_seconds for r in aggregate.results]
        )
        lo, hi = bootstrap_ci([r.duration_seconds for r in aggregate.results])
        total_input = sum(r.input_tokens or 0 for r in aggregate.results)
        total_output = sum(r.output_tokens or 0 for r in aggregate.results)
        lines.append(
            f"| {aggregate.task_id} | {aggregate.task_family} | {aggregate.category} | "
            f"{pk:.2f} | {passes}/{len(valid)} | "
            f"{pk_success} | "
            f"{mean_v:.1f} | {std_v:.1f} | [{lo:.1f}, {hi:.1f}] | "
            f"{_percentile(durations, 0.50):.1f} | {_percentile(durations, 0.95):.1f} | "
            f"{_percentile(durations, 0.99):.1f} | "
            f"{total_input} | {total_output} |"
        )
    lines.append("")

    # ---- Token cost summary -------------------------------------------------
    total_input = sum(r.input_tokens or 0 for a in aggregates for r in a.results)
    total_output = sum(r.output_tokens or 0 for a in aggregates for r in a.results)
    cost = compute_cost(model, total_input, total_output) if model else None
    lines.append("## Token Cost")
    lines.append("")
    lines.append("| Model | Input Tokens | Output Tokens | Est. Cost |")
    lines.append("|-------|--------------|---------------|-----------|")
    lines.append(
        f"| {model or '-'} | {total_input} | {total_output} | {format_cost(cost)} |"
    )
    lines.append("")

    # ---- Failure attribution ------------------------------------------------
    lines.append("## Failure Attribution")
    lines.append("")
    attribution = failure_attribution(aggregates)
    if not attribution:
        lines.append("(no failures)")
    else:
        total_failures = sum(len(samples) for samples in attribution.values())
        lines.append("| Reason | Count | Share | Look-back (task, round) |")
        lines.append("|--------|-------|-------|-------------------------|")
        for reason in sorted(attribution):
            samples = attribution[reason]
            share = len(samples) / total_failures if total_failures else 0.0
            lookbacks = ", ".join(
                f"{task_id}#{round_idx}" for task_id, round_idx in samples
            )
            lines.append(
                f"| {reason} | {len(samples)} | {share:.1%} | {lookbacks} |"
            )

    # ---- C3 disclosure sections ---------------------------------------------
    for heading, body in markdown_disclosure_sections(
        DisclosureContext(
            metadata=metadata,
            results=[r for a in aggregates for r in a.results],
            manifest=manifest,
            run_dirs=run_dirs or [],
        )
    ):
        lines.append("")
        lines.append(heading)
        lines.append("")
        lines.append(body.rstrip())

    return "\n".join(lines) + "\n"


def render_html(aggregates: AggregateRun | list[TaskAggregate]) -> str:
    """Render the aggregated run as a self-contained HTML page.

    Uses the same latency/cost conventions as ``compare.py`` and the same
    deterministic ordering as :func:`render_report`. Accepts the same input
    shapes (a flattened :class:`AggregateRun` or a ``list[TaskAggregate]``).
    """
    if isinstance(aggregates, AggregateRun):
        task_aggregates = aggregate_results([aggregates.results])
        agent = aggregates.agent
        model = aggregates.model
        repeat = aggregates.repeat
        metadata = aggregates.metadata[0] if aggregates.metadata else None
        run_dirs = aggregates.run_dirs or []
        manifest = aggregates.manifest
    else:
        task_aggregates = list(aggregates)
        agent = ""
        model = ""
        repeat = 0
        metadata = None
        run_dirs = []
        manifest = None

    # ---- Layer-level rows ------------------------------------------------
    layer_rows = ""
    present_layers = {a.category for a in task_aggregates}
    for layer in LAYERS:
        if layer not in present_layers:
            continue
        layer_aggregates = [a for a in task_aggregates if a.category == layer]
        valid = [r for a in layer_aggregates for r in _valid_results(a.results)]
        rounds = [_is_pass(r) for r in valid]
        rate = layer_pass_rate(rounds)
        lo, hi = bootstrap_ci([1.0 if ok else 0.0 for ok in rounds])
        pk_summary = pass_k_success_rate(
            [
                [_is_pass(r) for r in _valid_results(a.results)]
                for a in layer_aggregates
            ]
        )
        pk_str = f"{pk_summary.rate:.2f}" if pk_summary.rate is not None else "n/a"
        layer_rows += (
            f"<tr><td>{layer}</td><td>{len(layer_aggregates)}</td>"
            f"<td>{len(rounds)}</td><td>{rate:.2f}</td>"
            f"<td>[{lo:.2f}, {hi:.2f}]</td><td>{pk_str}</td></tr>"
        )

    # ---- Task-level rows -------------------------------------------------
    task_rows = ""
    for aggregate in task_aggregates:
        durations = sorted(r.duration_seconds for r in aggregate.results)
        valid = _valid_results(aggregate.results)
        passes = sum(1 for r in valid if _is_pass(r))
        pk = pass_at_k(passes, len(valid))
        if len(valid) >= 3:
            pk_success = "yes" if all(_is_pass(r) for r in valid) else "no"
        else:
            pk_success = "—"
        mean_v, std_v = mean_std([r.duration_seconds for r in aggregate.results])
        lo, hi = bootstrap_ci([r.duration_seconds for r in aggregate.results])
        total_input = sum(r.input_tokens or 0 for r in aggregate.results)
        total_output = sum(r.output_tokens or 0 for r in aggregate.results)
        cls = "passed" if pk >= 1.0 else "failed"
        task_rows += (
            f'<tr><td>{aggregate.task_id}</td><td>{aggregate.task_family}</td>'
            f'<td>{aggregate.category}</td><td class="{cls}">{pk:.2f}</td>'
            f"<td>{passes}/{len(valid)}</td>"
            f"<td>{pk_success}</td>"
            f"<td>{mean_v:.1f}</td><td>{std_v:.1f}</td>"
            f"<td>[{lo:.1f}, {hi:.1f}]</td>"
            f"<td>{_percentile(durations, 0.50):.1f}</td>"
            f"<td>{_percentile(durations, 0.95):.1f}</td>"
            f"<td>{_percentile(durations, 0.99):.1f}</td>"
            f"<td>{total_input}</td><td>{total_output}</td></tr>"
        )

    # ---- Token cost summary ---------------------------------------------
    total_input = sum(r.input_tokens or 0 for a in task_aggregates for r in a.results)
    total_output = sum(r.output_tokens or 0 for a in task_aggregates for r in a.results)
    cost = compute_cost(model, total_input, total_output) if model else None

    # ---- Failure attribution ---------------------------------------------
    attribution = failure_attribution(task_aggregates)
    if attribution:
        total_failures = sum(len(samples) for samples in attribution.values())
        attr_rows = "".join(
            f"<tr><td>{reason}</td><td>{len(samples)}</td><td>"
            f"{len(samples) / total_failures if total_failures else 0.0:.1%}</td><td>"
            + ", ".join(
                f"{task_id}#{round_idx}" for task_id, round_idx in samples
            )
            + "</td></tr>"
            for reason, samples in sorted(attribution.items())
        )
    else:
        attr_rows = "<tr><td colspan=\"4\">(no failures)</td></tr>"

    header = (
        f"<h2>Agent</h2><p>{agent or '-'} | Model: {model or '-'} | Rounds: {repeat}</p>"
        if agent
        else ""
    )

    # ---- C3 disclosure sections ---------------------------------------------
    disclosure_html = "".join(
        f"{heading}{body}"
        for heading, body in html_disclosure_sections(
            DisclosureContext(
                metadata=metadata,
                results=[r for a in task_aggregates for r in a.results],
                manifest=manifest,
                run_dirs=run_dirs,
            )
        )
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Benchmark Evaluation Report</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ color: #333; }} h2 {{ color: #333; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f5f5f5; }}
.passed {{ color: #22c55e; font-weight: bold; }}
.failed {{ color: #ef4444; }}
small {{ color: #888; font-weight: normal; }}
</style></head><body>
<h1>Benchmark Evaluation Report</h1>
{header}
<h2>By Capability Layer</h2>
<table>
<thead><tr><th>Layer</th><th>Tasks</th><th>Rounds</th><th>Pass Rate</th><th>95% CI</th><th>Pass^k</th></tr></thead>
<tbody>{layer_rows}</tbody>
</table>
<h2>By Task</h2>
<table>
<thead><tr><th>Task</th><th>task_family</th><th>category</th><th>Pass@k</th><th>Passes</th><th>Pass^k</th><th>Mean(s)</th><th>Std(s)</th><th>95% CI</th><th>p50</th><th>p95</th><th>p99</th><th>Input Tokens</th><th>Output Tokens</th></tr></thead>
<tbody>{task_rows}</tbody>
</table>
<h2>Token Cost</h2>
<table>
<thead><tr><th>Model</th><th>Input Tokens</th><th>Output Tokens</th><th>Est. Cost</th></tr></thead>
<tbody><tr><td>{model or '-'}</td><td>{total_input}</td><td>{total_output}</td><td>{format_cost(cost)}</td></tr></tbody>
</table>
<h2>Failure Attribution</h2>
<table>
<thead><tr><th>Reason</th><th>Count</th><th>Share</th><th>Look-back (task, round)</th></tr></thead>
<tbody>{attr_rows}</tbody>
</table>
{disclosure_html}
</body></html>"""

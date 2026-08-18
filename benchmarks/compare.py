#!/usr/bin/env python3
"""Comparison report generator for cross-agent benchmark runs.

Usage:
    python benchmarks/compare.py /tmp/bench-v4/<run-id> /tmp/p2-bench-claude/<run-id>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from agent.cost_tracker import compute_cost, format_cost
from benchmarks.models import TaskResult
from benchmarks.statistics import PairedComparison, paired_comparison


RESULT_ORDER = ["passed", "passed_with_warnings", "unsupported", "failed", "error"]


def _sort_key(status: str) -> int:
    try:
        return RESULT_ORDER.index(status)
    except ValueError:
        return 99


def _run_metadata_rows(metas: list[dict] | None) -> list[tuple[str, ...]]:
    """(agent, model, model_version, date, pricing_table) per run from run.json."""
    if not metas:
        return []
    rows: list[tuple[str, ...]] = []
    for meta in metas:
        rows.append(
            (
                str(meta.get("agent", "?")),
                str(meta.get("model", "") or "-"),
                str(meta.get("model_version", "") or "-"),
                str(meta.get("started_at", "") or "-"),
                str(meta.get("pricing_table_version", "") or "-"),
            )
        )
    return rows


def _build_paired_html(runs: list[tuple[str, dict[str, dict]]]) -> str:
    """HTML paired-comparison section sharing the same data as the markdown."""
    pair = _paired_data(runs)
    if pair is None:
        return ""
    name_a, name_b, comp = pair
    n_shared = len(comp.per_task_deltas)
    mean_delta = (
        sum(comp.per_task_deltas.values()) / n_shared if n_shared else 0.0
    )
    ci = comp.delta_ci
    ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
    wr = comp.win_rate
    mcnemar_html = ""
    if comp.mcnemar:
        m = comp.mcnemar
        sig = "significant" if m["significant"] else "not significant"
        mcnemar_html = (
            f"<p>McNemar (pass^k): b={m['b']}, c={m['c']}, "
            f"p={m['p_value']:.4f} ({sig})</p>"
        )
    delta_rows = "".join(
        f"<tr><td>{task_id}</td><td>{delta:.3f}</td></tr>"
        for task_id, delta in sorted(comp.per_task_deltas.items())
    )
    return f"""<h2>Paired Comparison</h2>
<p>Comparing <strong>{name_a}</strong> vs <strong>{name_b}</strong> over {n_shared} shared tasks.</p>
<table>
<thead><tr><th>Metric</th><th>Value</th></tr></thead>
<tbody>
<tr><td>Mean per-task delta (pass@1)</td><td>{mean_delta:.3f}</td></tr>
<tr><td>Difference 95% CI (paired bootstrap)</td><td>{ci_str}</td></tr>
<tr><td>Win-rate</td><td>{name_a}: {wr['a_wins']} / {name_b}: {wr['b_wins']} / ties: {wr['ties']}</td></tr>
</tbody>
</table>
{mcnemar_html}
<h3>Per-task deltas</h3>
<table>
<thead><tr><th>Task</th><th>delta</th></tr></thead>
<tbody>{delta_rows}</tbody>
</table>
"""


def load_run(run_dir: Path) -> dict[str, dict]:
    tasks = {}
    tasks_dir = run_dir / "tasks"
    if not tasks_dir.exists():
        return tasks
    for task_dir in sorted(tasks_dir.iterdir()):
        result_path = task_dir / "result.json"
        if result_path.exists():
            data = json.loads(result_path.read_text())
            tasks[task_dir.name] = data
    return tasks


def build_summary(
    runs: list[tuple[str, dict[str, dict]]],
    metas: list[dict] | None = None,
) -> str:
    """Build a markdown comparison summary table.

    ``metas`` carries each run's ``run.json`` metadata (model version / date /
    pricing-table version) for the run-metadata disclosure; optional so older
    callers keep working.
    """
    header = ["Task"]
    for name, _ in runs:
        header.append(f"{name}")
    lines = [
        "# Cross-Agent Benchmark Comparison",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["------"] * len(header)) + "|",
    ]

    all_tasks = sorted(set().union(*(r.keys() for _, r in runs)))
    stats = defaultdict(lambda: defaultdict(int))

    for task_id in all_tasks:
        row = [task_id]
        for name, results in runs:
            r = results.get(task_id, {})
            status = r.get("status", "?")
            time_s = r.get("duration_seconds", "?")
            row.append(f"{status} ({time_s}s)")
            stats[name][status] += 1
        lines.append("| " + " | ".join(row) + " |")

    # Summary rows
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    header2 = ["Agent"] + RESULT_ORDER + ["Total"]
    lines.append("| " + " | ".join(header2) + " |")
    lines.append("|" + "|".join(["------"] * len(header2)) + "|")
    for name, _ in runs:
        s = stats[name]
        total = sum(s.values())
        row = [name] + [str(s.get(k, 0)) for k in RESULT_ORDER] + [str(total)]
        lines.append("| " + " | ".join(row) + " |")

    # Latency percentiles
    lines.append("")
    lines.append("## Latency Percentiles")
    lines.append("")
    lat_header = ["Agent", "p50", "p95", "p99", "Max"]
    lines.append("| " + " | ".join(lat_header) + " |")
    lines.append("|" + "|".join(["------"] * len(lat_header)) + "|")
    for name, results in runs:
        durations = sorted(
            r["duration_seconds"]
            for r in results.values()
            if isinstance(r.get("duration_seconds"), (int, float))
        )
        if durations:
            n = len(durations)
            p50 = durations[int(n * 0.50)]
            p95 = durations[int(n * 0.95)]
            p99 = durations[int(n * 0.99)]
            max_d = durations[-1]
            row = [name, f"{p50:.1f}s", f"{p95:.1f}s", f"{p99:.1f}s", f"{max_d:.1f}s"]
        else:
            row = [name, "-", "-", "-", "-"]
        lines.append("| " + " | ".join(row) + " |")

    # Cost Estimate
    lines.append("")
    lines.append("## Cost Estimate")
    lines.append("")
    cost_header = ["Agent", "Input Tokens", "Output Tokens", "Est. Cost"]
    lines.append("| " + " | ".join(cost_header) + " |")
    lines.append("|" + "|".join(["------"] * len(cost_header)) + "|")
    for name, results in runs:
        total_input = sum(
            r.get("input_tokens", 0) or 0
            for r in results.values()
        )
        total_output = sum(
            r.get("output_tokens", 0) or 0
            for r in results.values()
        )
        model = next(
            (r.get("model", "") for r in results.values() if r.get("model")),
            "",
        )
        cost = compute_cost(model, total_input, total_output)
        lines.append(
            f"| {name} | {total_input} | {total_output} | {format_cost(cost)} |"
        )

    # Run metadata disclosure (C3): model version / date / cost basis.
    meta_rows = _run_metadata_rows(metas)
    if meta_rows:
        lines.append("")
        lines.append("## Run Metadata")
        lines.append("")
        meta_header = ["Agent", "Model", "Model Version", "Date", "Pricing Table"]
        lines.append("| " + " | ".join(meta_header) + " |")
        lines.append("|" + "|".join(["------"] * len(meta_header)) + "|")
        for row in meta_rows:
            lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


def _paired_data(
    runs: list[tuple[str, dict[str, dict]]],
) -> tuple[str, str, PairedComparison] | None:
    """Shared paired-comparison data for exactly two runs.

    Returns ``(name_a, name_b, comp)`` or None when ``runs`` does not have
    exactly two entries. Both the markdown and HTML renderers consume the same
    data so the two report formats cannot drift.
    """
    if len(runs) != 2:
        return None
    (name_a, results_a), (name_b, results_b) = runs
    comp = paired_comparison(
        [TaskResult.from_dict(d) for d in results_a.values()],
        [TaskResult.from_dict(d) for d in results_b.values()],
    )
    return name_a, name_b, comp


def build_paired_report(runs: list[tuple[str, dict[str, dict]]]) -> str:
    """Build a markdown paired-comparison section for exactly two runs.

    Returns an empty string when ``runs`` does not have exactly two entries.
    Uses the shared paired-comparison statistics (per-task pass@1 delta,
    paired-bootstrap difference CI, win-rate, exact-binomial McNemar on pass^k).
    """
    pair = _paired_data(runs)
    if pair is None:
        return ""
    (name_a, name_b, comp) = pair
    lines = ["## Paired Comparison", ""]
    n_shared = len(comp.per_task_deltas)
    lines.append(
        f"Comparing **{name_a}** vs **{name_b}** over {n_shared} shared tasks."
    )
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    mean_delta = (
        sum(comp.per_task_deltas.values()) / n_shared if n_shared else 0.0
    )
    ci = comp.delta_ci
    ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
    lines.append(f"| Mean per-task delta (pass@1) | {mean_delta:.3f} |")
    lines.append(f"| Difference 95% CI (paired bootstrap) | {ci_str} |")
    wr = comp.win_rate
    lines.append(
        f"| Win-rate | {name_a}: {wr['a_wins']} / {name_b}: {wr['b_wins']} "
        f"/ ties: {wr['ties']} |"
    )
    if comp.mcnemar:
        m = comp.mcnemar
        sig = "significant" if m["significant"] else "not significant"
        lines.append(
            f"| McNemar (pass^k) | b={m['b']}, c={m['c']}, "
            f"p={m['p_value']:.4f} ({sig}) |"
        )
    lines.append("")
    lines.append("### Per-task deltas")
    lines.append("")
    lines.append("| Task | delta |")
    lines.append("|------|-------|")
    for task_id, delta in sorted(comp.per_task_deltas.items()):
        lines.append(f"| {task_id} | {delta:.3f} |")
    return "\n".join(lines) + "\n"


def build_html(
    runs: list[tuple[str, dict[str, dict]]],
    metas: list[dict] | None = None,
) -> str:
    """Build an HTML comparison report.

    ``metas`` carries each run's ``run.json`` metadata for the run-metadata
    disclosure; optional so older callers keep working.
    """
    all_tasks = sorted(set().union(*(r.keys() for _, r in runs)))
    stats = defaultdict(lambda: defaultdict(int))
    for name, results in runs:
        for r in results.values():
            stats[name][r.get("status", "?")] += 1

    rows_html = ""
    for task_id in all_tasks:
        cells = f"<td>{task_id}</td>"
        for name, results in runs:
            r = results.get(task_id, {})
            status = r.get("status", "?")
            time_s = r.get("duration_seconds", "?")
            cls = status
            cells += f'<td class="{cls}">{status}<br><small>{time_s}s</small></td>'
        rows_html += f"<tr>{cells}</tr>"

    summary_rows = ""
    for name, _ in runs:
        s = stats[name]
        total = sum(s.values())
        cells = f"<td>{name}</td>"
        for k in RESULT_ORDER:
            cells += f"<td>{s.get(k, 0)}</td>"
        cells += f"<td><strong>{total}</strong></td>"
        summary_rows += f"<tr>{cells}</tr>"

    latency_rows = ""
    for name, results in runs:
        durations = sorted(
            r["duration_seconds"]
            for r in results.values()
            if isinstance(r.get("duration_seconds"), (int, float))
        )
        if durations:
            n = len(durations)
            p50 = durations[int(n * 0.50)]
            p95 = durations[int(n * 0.95)]
            p99 = durations[int(n * 0.99)]
            max_d = durations[-1]
            latency_rows += f"<tr><td>{name}</td><td>{p50:.1f}s</td><td>{p95:.1f}s</td><td>{p99:.1f}s</td><td>{max_d:.1f}s</td></tr>"
        else:
            latency_rows += f"<tr><td>{name}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>"

    # Cost estimate rows for HTML
    cost_rows = ""
    for name, results in runs:
        total_input = sum(
            r.get("input_tokens", 0) or 0
            for r in results.values()
        )
        total_output = sum(
            r.get("output_tokens", 0) or 0
            for r in results.values()
        )
        model = next(
            (r.get("model", "") for r in results.values() if r.get("model")),
            "",
        )
        cost = compute_cost(model, total_input, total_output)
        cost_rows += f"<tr><td>{name}</td><td>{total_input}</td><td>{total_output}</td><td>{format_cost(cost)}</td></tr>"

    meta_rows = _run_metadata_rows(metas)
    if meta_rows:
        meta_header = "<tr><th>Agent</th><th>Model</th><th>Model Version</th><th>Date</th><th>Pricing Table</th></tr>"
        meta_html = (
            "<h2>Run Metadata</h2><table>"
            f"<thead>{meta_header}</thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
                for row in meta_rows
            )
            + "</tbody></table>"
        )
    else:
        meta_html = ""

    paired_html = _build_paired_html(runs)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cross-Agent Benchmark</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f5f5f5; }}
.passed {{ color: #22c55e; font-weight: bold; }}
.passed_with_warnings {{ color: #eab308; }}
.unsupported {{ color: #64748b; }}
.failed {{ color: #ef4444; }}
.error {{ color: #a855f7; }}
small {{ color: #888; font-weight: normal; }}
.summary td {{ font-size: 1.1rem; }}
</style></head><body>
<h1>Cross-Agent Benchmark Comparison</h1>
<table>
<thead><tr><th>Task</th>{"".join(f"<th>{name}</th>" for name, _ in runs)}</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<h2>Summary</h2>
<table class="summary">
<thead><tr><th>Agent</th>{"".join(f"<th>{k}</th>" for k in RESULT_ORDER)}<th>Total</th></tr></thead>
<tbody>{summary_rows}</tbody>
</table>
<h2>Latency Percentiles</h2>
<table>
<thead><tr><th>Agent</th><th>p50</th><th>p95</th><th>p99</th><th>Max</th></tr></thead>
<tbody>{latency_rows}</tbody>
</table>
<h2>Cost Estimate</h2>
<table>
<thead><tr><th>Agent</th><th>Input Tokens</th><th>Output Tokens</th><th>Est. Cost</th></tr></thead>
<tbody>{cost_rows}</tbody>
</table>
{meta_html}
{paired_html}
</body></html>"""


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run-dir> [run-dir ...]")
        sys.exit(1)

    runs: list[tuple[str, dict[str, dict]]] = []
    metas: list[dict] = []
    for i, path in enumerate(sys.argv[1:]):
        run_dir = Path(path)
        results = load_run(run_dir)
        if not results:
            print(f"Warning: no results in {run_dir}", file=sys.stderr)
            continue
        # Try reading run.json for metadata, fall back to directory name
        run_json = run_dir / "run.json"
        if run_json.exists():
            meta = json.loads(run_json.read_text())
            name = f"{meta.get('agent', '?')}" + (f" ({meta.get('model', '')})" if meta.get('model') else "")
        else:
            meta = {}
            name = run_dir.name
        runs.append((name, results))
        metas.append(meta)

    if not runs:
        print("No runs with results found.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path("benchmarks/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "comparison.md"
    md_path.write_text(build_summary(runs, metas=metas) + build_paired_report(runs))
    print(f"Markdown: {md_path}")

    html_path = out_dir / "comparison.html"
    html_path.write_text(build_html(runs, metas=metas))
    print(f"HTML:     {html_path}")


if __name__ == "__main__":
    main()

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


RESULT_ORDER = ["passed", "passed_with_warnings", "unsupported", "failed", "error"]


def _sort_key(status: str) -> int:
    try:
        return RESULT_ORDER.index(status)
    except ValueError:
        return 99


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


def build_summary(runs: list[tuple[str, dict[str, dict]]]) -> str:
    """Build a markdown comparison summary table."""
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

    return "\n".join(lines) + "\n"


def build_html(runs: list[tuple[str, dict[str, dict]]]) -> str:
    """Build an HTML comparison report."""
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
</body></html>"""


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run-dir> [run-dir ...]")
        sys.exit(1)

    runs: list[tuple[str, dict[str, dict]]] = []
    labels = []
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
            name = run_dir.name
        runs.append((name, results))

    if not runs:
        print("No runs with results found.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path("benchmarks/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "comparison.md"
    md_path.write_text(build_summary(runs))
    print(f"Markdown: {md_path}")

    html_path = out_dir / "comparison.html"
    html_path.write_text(build_html(runs))
    print(f"HTML:     {html_path}")


if __name__ == "__main__":
    main()

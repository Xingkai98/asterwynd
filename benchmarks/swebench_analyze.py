"""Analyze SWE-bench benchmark results and print a structured report."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import sys


def analyze(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    summary = {"passed": 0, "warnings": 0, "failed": 0, "error": 0, "tasks": []}

    task_dirs = sorted(
        (run_dir / "tasks").iterdir()
        if (run_dir / "tasks").exists()
        else []
    )
    for task_dir in task_dirs:
        result_path = task_dir / "result.json"
        if not result_path.exists():
            continue
        result = json.loads(result_path.read_text())

        # Extract short task name
        short_name = result["task_id"].replace("swebench-", "").replace("__", "/")

        # Read diff size
        diff_path = task_dir / "final.diff"
        diff_lines = 0
        if diff_path.exists():
            diff_lines = len(diff_path.read_text().splitlines())

        # Read runner log
        log_path = task_dir / "runner.log"
        error_msg = ""
        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if "Error:" in line or "error" in line.lower():
                    error_msg = line.split("Error:", 1)[-1].strip()[:120]
                    break

        entry = {
            "task": short_name,
            "status": result["status"],
            "iterations": result.get("iterations", 0),
            "tool_calls": result.get("tool_calls", 0),
            "edit_count": result.get("edit_count", 0),
            "duration_s": result.get("duration_seconds", 0),
            "failure": result.get("failure_category", ""),
            "diff_lines": diff_lines,
            "error": error_msg,
        }
        summary[entry["status"]] += 1
        summary["tasks"].append(entry)

    return summary


def print_report(summary: dict) -> None:
    print("\n" + "=" * 90)
    print("  SWE-bench Benchmark Results")
    print("=" * 90)
    print(f"  Total: {len(summary['tasks'])} | "
          f"Passed: {summary['passed']} | "
          f"Warnings: {summary['warnings']} | "
          f"Failed: {summary['failed']} | "
          f"Error: {summary['error']}")
    if summary["tasks"]:
        passed = summary["passed"] + summary["warnings"]
        total_ok = passed + summary["failed"] + summary["error"]
        if total_ok > 0:
            print(f"  Pass rate: {passed}/{total_ok} ({100*passed/total_ok:.0f}%)")
    print("-" * 90)

    # Group by status
    by_status = defaultdict(list)
    for t in summary["tasks"]:
        by_status[t["status"]].append(t)

    status_order = ["passed", "passed_with_warnings", "failed", "error"]
    for status in status_order:
        tasks = by_status.get(status, [])
        if not tasks:
            continue
        emoji = {"passed": "✅", "passed_with_warnings": "⚠️", "failed": "❌", "error": "💥"}.get(status, "")
        print(f"\n  {emoji} {status.upper()} ({len(tasks)}):")
        for t in tasks:
            extra = ""
            if t["edit_count"] > 0:
                extra += f"edits={t['edit_count']}"
            if t["failure"]:
                extra += f" [{t['failure']}]"
            if t["error"]:
                extra += f" | {t['error'][:80]}"
            print(f"    {t['task']:55s} | {t['duration_s']:5.0f}s | "
                  f"iters={t['iterations']:2d} | calls={t['tool_calls']:2d} | "
                  f"diff={t['diff_lines']:3d}L {extra}")

    # Summary by repo
    print("\n  --- By Repo ---")
    by_repo = defaultdict(lambda: {"passed": 0, "total": 0})
    for t in summary["tasks"]:
        repo = t["task"].split("/")[0] if "/" in t["task"] else "?"
        by_repo[repo]["total"] += 1
        if t["status"] in ("passed", "passed_with_warnings"):
            by_repo[repo]["passed"] += 1
    for repo in sorted(by_repo):
        d = by_repo[repo]
        print(f"    {repo:20s}: {d['passed']}/{d['total']} passed")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "benchmarks/runs"
    # Find the latest run directory
    p = Path(path)
    if not p.exists() or not (p / "tasks").exists():
        # Try to find latest
        runs = sorted(p.glob("*/tasks"), reverse=True)
        if runs:
            p = runs[0].parent
            print(f"Using latest run: {p}")
    summary = analyze(p)
    print_report(summary)

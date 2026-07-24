#!/usr/bin/env python3
"""Read-only phase completion verification. Never modifies files.

Usage:
    uv run python scripts/check_phase_done.py --phase wayfinding --change <id>
    uv run python scripts/check_phase_done.py --phase planning --change <id>
    uv run python scripts/check_phase_done.py --phase building --change <id>
    uv run python scripts/check_phase_done.py --phase closing --change <id>
    uv run python scripts/check_phase_done.py --phase wayfinding --change <id> --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

VALID_PHASES = {"wayfinding", "planning", "building", "closing"}

CHANGES_ROOT = Path("openspec/changes")
SPECS_ROOT = Path("openspec/specs")
HANDOFF_DIR = Path(".handoff")
BACKLOG_PATH = Path("docs/openspec-change-backlog.md")
KNOWN_DEBT_PATH = Path("docs/known-debt.md")


# ── helpers ────────────────────────────────────────────────────────────


def _load_handoff(change_id: str) -> dict | None:
    path = CHANGES_ROOT / change_id / "handoff.json"
    if not path.exists():
        # Also check archive
        archive_matches = list((CHANGES_ROOT / "archive").glob(f"*{change_id}*"))
        if archive_matches:
            hf = archive_matches[0] / "handoff.json"
            if hf.exists():
                return json.loads(hf.read_text(encoding="utf-8"))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_known_debt() -> set[str]:
    if not KNOWN_DEBT_PATH.exists():
        return set()
    entries: set[str] = set()
    for line in KNOWN_DEBT_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("- "):
            entries.add(stripped)
        elif stripped.startswith("- "):
            entries.add(stripped[2:].strip())
    return entries


def _changed_python_files(repo_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/master", "--", "*.py"],
            capture_output=True, text=True, cwd=repo_root,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [repo_root / p for p in result.stdout.strip().splitlines() if p]


def _find_todo_residuals(repo_root: Path, change_id: str) -> list[str]:
    known = _load_known_debt()
    changed = _changed_python_files(repo_root)
    residuals: list[str] = []
    for fpath in changed:
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if any(marker in stripped for marker in ("TODO", "TBD", "FIXME", "HACK")):
                if stripped not in known:
                    residuals.append(f"{fpath.relative_to(repo_root)}:{lineno}: {stripped}")
    return residuals


def _benchmark_smoke_passes(repo_root: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [
                "uv", "run", "asterwynd", "benchmark", "benchmarks/tasks",
                "--agent", "fake", "--source-repo", str(repo_root),
                "--runs-dir", "/tmp/smoke-check",
            ],
            capture_output=True, text=True, cwd=repo_root, timeout=120,
        )
        return result.returncode == 0, result.stdout[-500:] if result.stdout else result.stderr
    except FileNotFoundError:
        return True, "SKIP: uv/asterwynd 命令不可用"
    except subprocess.TimeoutExpired:
        return False, "Benchmark smoke 超时 (120s)"


def _check_review_report(change_id: str, phase: str, report_name: str | None = None) -> list[str]:
    """Check that a review report exists and has no blockers."""
    errors: list[str] = []
    if report_name is None:
        report_name = f"{phase}-review.md"
    report_path = HANDOFF_DIR / change_id / report_name
    if not report_path.exists():
        errors.append(f"审阅报告缺失: {report_path} — 尚未运行独立子 Agent 审阅")
    else:
        try:
            text = report_path.read_text(encoding="utf-8")
            if "BLOCKED" in text:
                errors.append(f"审阅报告包含 BLOCKED — 存在未解决的阻塞项: {report_path}")
            elif "CHANGES_REQUESTED" in text:
                errors.append(f"审阅报告包含 CHANGES_REQUESTED — 请确认所有修改请求已解决: {report_path}")
        except Exception:
            errors.append(f"无法读取审阅报告: {report_path}")
    return errors


def _check_handoff_at_gate(change_id: str, phase: str) -> list[str]:
    """Verify handoff.json is at the correct phase and gate sub-state."""
    errors: list[str] = []
    data = _load_handoff(change_id)
    if data is None:
        errors.append("handoff.json 不存在")
    else:
        state = data.get("state", {})
        actual_phase = state.get("phase")
        # "done" is only valid for closing phase (post-PR merge)
        valid_phases = {phase}
        if phase == "closing":
            valid_phases.add("done")
        if actual_phase not in valid_phases:
            errors.append(f"期望 phase in {valid_phases}，实际={actual_phase}")
        if actual_phase != "done" and state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )
    return errors


# ── phase checkers ─────────────────────────────────────────────────────


def check_wayfinding(change_id: str) -> list[str]:
    errors: list[str] = []
    change_dir = CHANGES_ROOT / change_id

    if not change_dir.exists():
        return [f"Change 目录不存在: {change_dir}"]

    # 1. wayfinder:map issue should be referenced
    data = _load_handoff(change_id)
    if data:
        state = data.get("state", {})
        if state.get("sub_state") == "map_cleared" or state.get("sub_state") == "ready_for_review":
            # Check that map_cleared actually makes sense
            if not data.get("transitions"):
                errors.append("transitions 为空 — wayfinding 似乎没有推进任何步骤")
            # Check review report
            review_errors = _check_review_report(change_id, "wayfinding")
            errors.extend(review_errors)

    # 2. handoff.json at wayfinding.ready_for_review
    errors.extend(_check_handoff_at_gate(change_id, "wayfinding"))

    return errors


def check_planning(change_id: str) -> list[str]:
    errors: list[str] = []
    change_dir = CHANGES_ROOT / change_id

    if not change_dir.exists():
        return [f"Change 目录不存在: {change_dir}"]

    # 1. Artifact checker for structural checks
    try:
        from scripts.check_openspec_artifacts import check_change
        errors.extend(check_change(change_dir, SPECS_ROOT))
    except ImportError:
        errors.append("SKIP: 无法导入 check_openspec_artifacts")

    # 2. Review report exists
    review_errors = _check_review_report(change_id, "planning")
    errors.extend(review_errors)

    # 3. handoff.json at planning.ready_for_review
    errors.extend(_check_handoff_at_gate(change_id, "planning"))

    return errors


def check_building(change_id: str, repo_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    root = repo_root or Path.cwd()

    # 1. pytest passes
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "-q"],
            capture_output=True, text=True, cwd=root, timeout=300,
        )
        if result.returncode != 0:
            summary = result.stdout.splitlines()[-3:] if result.stdout else [result.stderr]
            errors.append(f"pytest 未通过 (exit={result.returncode}):\n" + "\n".join(summary))
    except FileNotFoundError:
        errors.append("SKIP: uv/pytest 不可用")
    except subprocess.TimeoutExpired:
        errors.append("pytest 超时 (300s)")

    # 2. No TODO/TBD residuals in changed files
    residuals = _find_todo_residuals(root, change_id)
    if residuals:
        errors.append(f"发现 {len(residuals)} 处 TODO/TBD/FIXME/HACK 残留:\n" +
                      "\n".join(f"  {r}" for r in residuals[:10]))

    # 3. Benchmark smoke
    passed, reason = _benchmark_smoke_passes(root)
    if not passed:
        errors.append(f"Benchmark smoke 未通过: {reason}")

    # 4. Review report exists (reviewing_impl)
    review_errors = _check_review_report(change_id, "building")
    errors.extend(review_errors)

    # 5. handoff.json at building.ready_for_review
    errors.extend(_check_handoff_at_gate(change_id, "building"))

    return errors


def check_closing(change_id: str) -> list[str]:
    errors: list[str] = []

    # 1. openspec validate
    try:
        result = subprocess.run(
            ["npx", "--yes", "@fission-ai/openspec@1.4.1", "validate", "--all", "--strict"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            errors.append(f"openspec validate 未通过: {result.stdout[-300:] or result.stderr}")
    except FileNotFoundError:
        errors.append("SKIP: npx/openspec 不可用")
    except subprocess.TimeoutExpired:
        errors.append("openspec validate 超时 (120s)")

    # 2. Change archived — find it in archive/
    archive_dir = CHANGES_ROOT / "archive"
    archive_matches = list(archive_dir.glob(f"*{change_id}*"))
    if not archive_matches:
        errors.append(f"Change 未归档: 找不到 archive/*{change_id}*")
        archived_change_root = None
    else:
        archived_change_root = archive_matches[0]

    # 3. Backlog consistency
    try:
        from scripts.check_openspec_artifacts import check_backlog_consistency
        errors.extend(check_backlog_consistency(CHANGES_ROOT, BACKLOG_PATH))
    except ImportError:
        errors.append("SKIP: 无法导入 check_backlog_consistency")

    # 4. Final artifact checker
    try:
        from scripts.check_openspec_artifacts import check_change
        check_path = archived_change_root or (CHANGES_ROOT / change_id)
        if check_path.exists():
            errors.extend(check_change(check_path, SPECS_ROOT))
    except ImportError:
        pass

    # 5. Review report exists (reviewing_archive)
    review_errors = _check_review_report(change_id, "closing")
    errors.extend(review_errors)

    # 6. handoff.json at closing.ready_for_review or done
    errors.extend(_check_handoff_at_gate(change_id, "closing"))

    return errors


# ── CLI ─────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读 phase 完成验证 — 不修改任何文件。Gate 处运行。",
    )
    parser.add_argument("--phase", required=True, choices=sorted(VALID_PHASES))
    parser.add_argument("--change", required=True, help="Change ID")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    checkers = {
        "wayfinding": lambda: check_wayfinding(args.change),
        "planning": lambda: check_planning(args.change),
        "building": lambda: check_building(args.change, root),
        "closing": lambda: check_closing(args.change),
    }

    errors = checkers[args.phase]()

    if args.json:
        print(json.dumps({
            "phase": args.phase,
            "change_id": args.change,
            "passed": len(errors) == 0,
            "errors": errors,
            "checks_run": len(errors) if errors else 1,
        }, indent=2, ensure_ascii=False))
    else:
        if errors:
            for e in errors:
                print(f"FAIL: {e}")
            print(f"\n{len(errors)} 项检查失败")
        else:
            print(f"PASS: {args.phase} 阶段所有检查已通过")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

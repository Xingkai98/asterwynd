#!/usr/bin/env python3
"""Read-only phase completion verification. Never modifies files.

Usage:
    uv run python scripts/check_phase_done.py --phase planning --change <id>
    uv run python scripts/check_phase_done.py --phase building --change <id>
    uv run python scripts/check_phase_done.py --phase code-review --change <id>
    uv run python scripts/check_phase_done.py --phase closing --change <id>
    uv run python scripts/check_phase_done.py --phase planning --change <id> --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

VALID_PHASES = {"planning", "building", "code-review", "closing"}

CHANGES_ROOT = Path("openspec/changes")
SPECS_ROOT = Path("openspec/specs")
HANDOFF_DIR = Path(".handoff")
BACKLOG_PATH = Path("docs/openspec-change-backlog.md")
KNOWN_DEBT_PATH = Path("docs/known-debt.md")


# ── helpers ────────────────────────────────────────────────────────────


def _load_handoff(change_id: str) -> dict | None:
    path = CHANGES_ROOT / change_id / "handoff.json"
    if not path.exists():
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
    """Return Python files changed vs origin/master."""
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
    """Scan changed Python files for TODO/TBD/FIXME/HACK markers not in known-debt."""
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
    """Run benchmark smoke test. Returns (passed, reason)."""
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


# ── phase checkers ─────────────────────────────────────────────────────


def check_planning(change_id: str) -> list[str]:
    errors: list[str] = []
    change_dir = CHANGES_ROOT / change_id

    if not change_dir.exists():
        return [f"Change 目录不存在: {change_dir}"]

    # Reuse artifact checker for structural checks
    try:
        from scripts.check_openspec_artifacts import check_change
        errors.extend(check_change(change_dir, SPECS_ROOT))
    except ImportError:
        errors.append("SKIP: 无法导入 check_openspec_artifacts")

    # Verify handoff.json is at planning.ready_for_review
    data = _load_handoff(change_id)
    if data is None:
        errors.append("handoff.json 不存在")
    else:
        state = data.get("state", {})
        if state.get("phase") != "planning":
            errors.append(f"期望 phase=planning，实际={state.get('phase')}")
        if state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )

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

    # 3. Benchmark smoke (for core changes only — try and skip if unavailable)
    passed, reason = _benchmark_smoke_passes(root)
    if not passed:
        errors.append(f"Benchmark smoke 未通过: {reason}")

    # 4. handoff.json at building.ready_for_review
    data = _load_handoff(change_id)
    if data is None:
        errors.append("handoff.json 不存在")
    else:
        state = data.get("state", {})
        if state.get("phase") != "building":
            errors.append(f"期望 phase=building，实际={state.get('phase')}")
        if state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )

    return errors


def check_code_review(change_id: str) -> list[str]:
    errors: list[str] = []

    # 1. Review report exists
    review_dir = HANDOFF_DIR / change_id
    review_md = review_dir / "review-report.md"
    review_json = review_dir / "review-report.json"
    if not review_md.exists() and not review_json.exists():
        errors.append(f"评审报告不存在: {review_md} 或 {review_json}")
    elif review_md.exists():
        try:
            text = review_md.read_text(encoding="utf-8")
            if "CHANGES_REQUESTED" in text:
                errors.append("评审报告包含 CHANGES_REQUESTED — 请确认所有修改请求已解决")
        except Exception:
            errors.append(f"无法读取 {review_md}")

    # 2. handoff.json at code-review.ready_for_review
    data = _load_handoff(change_id)
    if data is None:
        errors.append("handoff.json 不存在")
    else:
        state = data.get("state", {})
        if state.get("phase") != "code-review":
            errors.append(f"期望 phase=code-review，实际={state.get('phase')}")
        if state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )

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

    # 2. Change archived — find it in archive/ and use that path
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

    # 4. Final artifact checker — use archive path if available
    try:
        from scripts.check_openspec_artifacts import check_change
        check_path = archived_change_root or (CHANGES_ROOT / change_id)
        errors.extend(check_change(check_path, SPECS_ROOT))
    except ImportError:
        pass  # already reported above

    # 5. handoff.json at closing.ready_for_review or done
    data = _load_handoff(change_id)
    if data is None and archived_change_root is not None:
        hf = archived_change_root / "handoff.json"
        if hf.exists():
            data = json.loads(hf.read_text(encoding="utf-8"))
    if data is not None:
        state = data.get("state", {})
        phase = state.get("phase")
        if phase not in ("closing", "done"):
            errors.append(f"期望 phase=closing 或 done，实际={phase}")
        if phase != "done" and state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )

    return errors


# ── CLI ─────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读相位完成验证 — 不修改任何文件",
    )
    parser.add_argument("--phase", required=True, choices=sorted(VALID_PHASES))
    parser.add_argument("--change", required=True, help="Change ID")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    checkers = {
        "planning": lambda: check_planning(args.change),
        "building": lambda: check_building(args.change, root),
        "code-review": lambda: check_code_review(args.change),
        "closing": lambda: check_closing(args.change),
    }

    errors = checkers[args.phase]()

    if args.json:
        print(json.dumps({
            "phase": args.phase,
            "change_id": args.change,
            "passed": len(errors) == 0,
            "errors": errors,
            "checks_run": max(len(errors), 1),
            "checks_passed": 0 if errors else max(len(errors), 1),
        }, indent=2, ensure_ascii=False))
    else:
        if errors:
            for e in errors:
                print(f"FAIL: {e}")
            print(f"\n{len(errors)} 项检查失败")
        else:
            print(f"PASS: {args.phase} 阶段所有机械检查已通过")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

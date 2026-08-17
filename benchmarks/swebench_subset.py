"""SWE-bench Verified 精选子集工具：配比选择 + 元数据校验 + L3 金补丁自检。

D6/OQ-V1：从轻量+中等池（requests/flask/pytest/sympy/seaborn/pylint）逐条过滤
KNOWN_BAD 与重实例后补齐至 50（保留现有 10 fixture），不含 django/sphinx 重
实例。数据集访问不可用（如无 huggingface 网络）时，本模块提供选择逻辑与
校验规则，实际 fixture 生成在数据可访问环境执行；生成后可用
``validate_fixture`` 机械校验、``gold_check`` 做 L3 金补丁自检。
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# OQ-V1 确认：40 条补齐配比（平衡现有 requests 6/10 偏置）。
SUBSET_TARGETS: dict[str, int] = {
    "psf/requests": 4,
    "pallets/flask": 6,
    "pytest-dev/pytest": 8,
    "sympy/sympy": 8,
    "mwaskom/seaborn": 6,
    "pylint-dev/pylint": 8,
}

# 重实例：不纳入子集（测试慢、权重失真）。KNOWN_BAD 实例集需在数据集
# 可访问时从 R2 审计清单/数据集标注读取，此处提供注入入口。
HEAVY_REPOS = {
    "django/django",
    "scikit-learn/scikit-learn",
    "sphinx-doc/sphinx",
    "matplotlib/matplotlib",
    "pydata/xarray",
    "astropy/astropy",
}

KNOWN_BAD_ENTRIES: set[str] = set()  # 由 build_subset 调用方注入（数据环境）。


@dataclass
class SubsetPlan:
    """一次子集选择的结果。"""

    selected: list[dict] = field(default_factory=list)
    skipped_known_bad: int = 0
    skipped_heavy: int = 0
    skipped_no_test_patch: int = 0
    skipped_missing_instance_id: int = 0
    pool_remaining: int = 0

    def summary(self) -> str:
        by_repo = Counter(ex.get("repo", "?") for ex in self.selected)
        parts = ", ".join(f"{repo}: {n}" for repo, n in sorted(by_repo.items()))
        return (
            f"selected={len(self.selected)} ({parts}) | "
            f"skipped: known_bad={self.skipped_known_bad}, heavy={self.skipped_heavy}, "
            f"no_test_patch={self.skipped_no_test_patch}, "
            f"missing_instance_id={self.skipped_missing_instance_id}, "
            f"pool_remaining={self.pool_remaining}"
        )


def _has_test_patch(ex: dict) -> bool:
    return bool(ex.get("test_patch", "").strip())


def build_subset(
    instances: list[dict],
    targets: dict[str, int] | None = None,
    known_bad: set[str] | None = None,
    heavy_repos: set[str] | None = None,
) -> SubsetPlan:
    """按配比从候选实例挑选子集。

    过滤顺序：KNOWN_BAD → 重 repo → 空 test_patch；随后按 repo 配比挑选。
    实例 dict 至少含 ``instance_id``/``repo``/``test_patch``。
    """
    targets = targets or SUBSET_TARGETS
    known_bad = known_bad or KNOWN_BAD_ENTRIES
    heavy_repos = heavy_repos or HEAVY_REPOS
    plan = SubsetPlan()

    by_repo: dict[str, list[dict]] = {}
    for ex in instances:
        repo = ex.get("repo", "")
        if not ex.get("instance_id"):
            plan.skipped_missing_instance_id += 1
            continue
        if ex["instance_id"] in known_bad:
            plan.skipped_known_bad += 1
            continue
        if repo in heavy_repos:
            plan.skipped_heavy += 1
            continue
        if not _has_test_patch(ex):
            plan.skipped_no_test_patch += 1
            continue
        by_repo.setdefault(repo, []).append(ex)

    pool_remaining = 0
    for repo, want in targets.items():
        candidates = sorted(
            by_repo.get(repo, []),
            key=lambda ex: ex.get("instance_id", ""),
        )
        take = candidates[:want]
        plan.selected.extend(take)
        pool_remaining += max(0, len(candidates) - want)
    plan.pool_remaining = pool_remaining + sum(
        len(v) for k, v in by_repo.items() if k not in targets
    )
    return plan


def validate_fixture(task: dict) -> list[str]:
    """校验单个 Verified fixture 元数据，返回错误列表（空=合法）。"""
    errors: list[str] = []
    if not task.get("instance_id"):
        errors.append("missing instance_id")
    if not task.get("dataset_name"):
        errors.append("missing dataset_name")
    if not task.get("dataset_split"):
        errors.append("missing dataset_split")
    if task.get("track") != "verified":
        errors.append("track must be 'verified'")
    if task.get("scenario") != "bug-fix":
        errors.append("scenario must be 'bug-fix' for verified fixtures")
    if task.get("difficulty") not in {"easy", "medium", "hard"}:
        errors.append(f"difficulty not normalized: {task.get('difficulty')!r}")
    if task.get("task_family") != "swebench":
        errors.append("task_family must be 'swebench'")
    if task.get("execution_environment") not in {"local", "docker"}:
        errors.append("execution_environment must be 'local' or 'docker'")
    return errors


def validate_fixtures_dir(tasks_dir: str | Path) -> list[tuple[str, list[str]]]:
    """校验目录下全部 swebench fixture，返回 (task_id, errors) 列表。"""
    root = Path(tasks_dir)
    problems: list[tuple[str, list[str]]] = []
    for task_json in sorted(root.glob("swebench-*/task.json")):
        task = json.loads(task_json.read_text())
        errors = validate_fixture(task)
        if errors:
            problems.append((task.get("id", task_json.parent.name), errors))
    return problems


def gold_check(
    task_dir: str | Path,
    *,
    timeout: int = 600,
) -> int:
    """L3 金补丁自检：检出 base_commit → 应用 gold.patch → 跑 test_command。

    返回 0 表示 gold.patch 应用 + 验证命令通过（实例可复现）；非 0 表示
    不可复现（flaky/坏实例，应剔除）。
    """
    from benchmarks.task_schema import load_task

    root = Path(task_dir).resolve()
    loaded = load_task(root)
    task = loaded.task
    if not loaded.gold_patch_path:
        raise SystemExit(f"{task.id}: no gold.patch to self-check")
    if task.external_repo:
        raise SystemExit(
            f"{task.id}: external_repo 实例需先 clone 到工作区后再跑 gold_check"
        )

    base_worktree = root / ".gold-check"
    if base_worktree.exists():
        subprocess.run(["git", "-C", str(base_worktree), "checkout", "-q", task.base_commit], check=False)
    else:
        subprocess.run(
            ["git", "worktree", "add", "-q", str(base_worktree), task.base_commit],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(base_worktree), "apply", "--check", str(loaded.gold_patch_path)],
        check=True,
    )
    subprocess.run(["git", "-C", str(base_worktree), "apply", str(loaded.gold_patch_path)], check=True)
    if loaded.test_patch_path:
        subprocess.run(
            ["git", "-C", str(base_worktree), "apply", "--check", str(loaded.test_patch_path)],
            check=True,
        )
        subprocess.run(["git", "-C", str(base_worktree), "apply", str(loaded.test_patch_path)], check=True)
    proc = subprocess.run(
        task.test_command,
        shell=True,
        cwd=base_worktree,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SWE-bench Verified 子集工具")
    parser.add_argument("--validate-dir", metavar="TASKS_DIR", help="校验目录下 swebench fixture 元数据")
    parser.add_argument("--gold-check", metavar="TASK_DIR", help="对单个任务做 L3 金补丁自检")
    args = parser.parse_args()

    if args.validate_dir:
        problems = validate_fixtures_dir(args.validate_dir)
        if problems:
            for task_id, errors in problems:
                print(f"INVALID {task_id}: {'; '.join(errors)}")
            sys.exit(1)
        print("all fixtures valid")
    elif args.gold_check:
        sys.exit(gold_check(args.gold_check))
    else:
        parser.print_help()

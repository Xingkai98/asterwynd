"""SWE-bench Verified 精选子集工具：配比选择 + 元数据校验 + L3 金补丁自检。

D6/OQ-V1：从轻量+中等池（requests/flask/pytest/sympy/seaborn/pylint）逐条过滤
KNOWN_BAD 与重实例后补齐至 50（保留现有 10 fixture），不含 django/sphinx 重
实例。数据集访问不可用（如无 huggingface 网络）时，本模块提供选择逻辑与
校验规则，实际 fixture 生成在数据可访问环境执行；生成后可用
``validate_fixture`` 机械校验、``gold_check`` 做 L3 金补丁自检。
"""
from __future__ import annotations

import datetime
import json
import os
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
    skipped_existing: int = 0
    pool_remaining: int = 0

    def summary(self) -> str:
        by_repo = Counter(ex.get("repo", "?") for ex in self.selected)
        parts = ", ".join(f"{repo}: {n}" for repo, n in sorted(by_repo.items()))
        return (
            f"selected={len(self.selected)} ({parts}) | "
            f"skipped: known_bad={self.skipped_known_bad}, existing={self.skipped_existing}, "
            f"heavy={self.skipped_heavy}, "
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
    exclude_ids: set[str] | None = None,
) -> SubsetPlan:
    """按配比从候选实例挑选子集。

    过滤顺序：缺 instance_id → 既有 fixture（exclude_ids）→ KNOWN_BAD → 重 repo
    → 空 test_patch；随后按 repo 配比挑选。实例 dict 至少含
    ``instance_id``/``repo``/``test_patch``。
    """
    targets = targets or SUBSET_TARGETS
    known_bad = known_bad or KNOWN_BAD_ENTRIES
    heavy_repos = heavy_repos or HEAVY_REPOS
    exclude_ids = exclude_ids or set()
    plan = SubsetPlan()

    by_repo: dict[str, list[dict]] = {}
    for ex in instances:
        repo = ex.get("repo", "")
        if not ex.get("instance_id"):
            plan.skipped_missing_instance_id += 1
            continue
        if ex["instance_id"] in exclude_ids:
            plan.skipped_existing += 1
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
    install_deps: bool = False,
) -> int:
    """L3 金补丁自检：检出 base_commit → 应用 gold.patch → 跑 test_command。

    返回 0 表示 gold.patch 应用 + 验证命令通过（实例可复现）；非 0 表示
    不可复现（flaky/坏实例，应剔除）。external_repo 实例（swebench fixture）
    走 clone→checkout→apply→（可选装依赖）→run 路径（grill OQ-V2）。
    """
    from benchmarks.task_schema import load_task

    root = Path(task_dir).resolve()
    loaded = load_task(root)
    task = loaded.task
    if not loaded.gold_patch_path:
        raise SystemExit(f"{task.id}: no gold.patch to self-check")
    if task.external_repo:
        return _gold_check_external(
            root, loaded, task, timeout=timeout, install_deps=install_deps
        )

    base_worktree = root / ".gold-check"
    if base_worktree.exists():
        subprocess.run(["git", "-C", str(base_worktree), "checkout", "-q", task.base_commit], check=False)
    else:
        subprocess.run(
            ["git", "worktree", "add", "-q", str(base_worktree), task.base_commit],
            check=True,
        )
    _apply_patches(base_worktree, loaded)
    proc = subprocess.run(
        task.test_command,
        shell=True,
        cwd=base_worktree,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode


def _gold_check_external(
    root: Path,
    loaded,
    task,
    *,
    timeout: int,
    install_deps: bool,
) -> int:
    """external_repo 实例的 L3 自检：clone→checkout base_commit→apply→(venv 装依赖)→run。"""
    worktree = root / ".gold-check"
    if not (worktree / ".git").is_dir():
        subprocess.run(
            ["git", "clone", "-q", task.external_repo, str(worktree)],
            check=True,
            timeout=timeout,
        )
    subprocess.run(
        ["git", "-C", str(worktree), "checkout", "-q", task.base_commit],
        check=False,
    )
    _apply_patches(worktree, loaded)
    env = None
    if install_deps:
        env = _install_repo_deps(root, worktree, timeout)
    proc = subprocess.run(
        task.test_command,
        shell=True,
        cwd=worktree,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode


def _apply_patches(worktree: Path, loaded) -> None:
    """按序 apply gold.patch 与 test.patch（先 --check 验证）。"""
    for patch in (loaded.gold_patch_path, loaded.test_patch_path):
        if not patch:
            continue
        subprocess.run(
            ["git", "-C", str(worktree), "apply", "--check", str(patch)],
            check=True,
        )
        subprocess.run(["git", "-C", str(worktree), "apply", str(patch)], check=True)


def _install_repo_deps(root: Path, worktree: Path, timeout: int) -> dict | None:
    """在隔离 venv 装依赖，返回让 ``python`` 解析到该 venv 的 env；装失败返回 None。

    旧 base_commit 的依赖 pin 可能装不上——装不上就继续裸跑 test_command，
    结果由调用方记录（坏实例只记录不删除，grill OQ-V2③）。
    """
    venv_dir = root / ".gold-check-venv"
    if not (venv_dir / "bin" / "python").exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python = venv_dir / "bin" / "python"
    # py3.12 venv 默认无 setuptools，老 setup.py 的 repo 需先装 setuptools/wheel。
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "setuptools", "wheel"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    for spec in (".", ".[test]"):
        proc = subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "-e", spec],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            break
    return {**os.environ, "PATH": f"{venv_dir / 'bin'}:{os.environ.get('PATH', '')}"}


# -- build-subset 子命令的辅助函数 --------------------------------------------

# OQ-V5②：--targets 用逗号分隔短名，短名→完整 repo 键。
REPO_SHORT_NAMES = {
    "requests": "psf/requests",
    "flask": "pallets/flask",
    "pytest": "pytest-dev/pytest",
    "sympy": "sympy/sympy",
    "seaborn": "mwaskom/seaborn",
    "pylint": "pylint-dev/pylint",
}


def parse_targets(spec: str | None) -> dict[str, int]:
    """解析逗号分隔短名配比，如 ``requests+4,flask+6`` → {``psf/requests``: 4, ...}。

    repo 键自带 ``/``，故配比间用逗号分隔（grill OQ-V5②）。
    """
    if not spec:
        return dict(SUBSET_TARGETS)
    targets: dict[str, int] = {}
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "+" not in chunk:
            raise ValueError(f"target 需形如 <短名>+<数量>，得到 {chunk!r}")
        name, _, count_s = chunk.partition("+")
        repo = REPO_SHORT_NAMES.get(name)
        if repo is None:
            raise ValueError(
                f"未知短名 {name!r}（可用: {', '.join(sorted(REPO_SHORT_NAMES))}）"
            )
        targets[repo] = int(count_s)
    return targets


def load_known_bad(path: str | None) -> set[str]:
    """从文件加载 KNOWN_BAD instance_id 清单（每行一个）；None 或缺失→空集。

    OQ-V4：本 change 接受空集（Verified 500 人工验证过，坏实例靠 L2 兜底），
    保留 ``--known-bad-file`` 接口供未来注入 R2 审计清单。
    """
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"KNOWN_BAD 文件不存在: {p}")
    return {line.strip() for line in p.read_text().splitlines() if line.strip()}


def collect_existing_instance_ids(tasks_dir: str | Path) -> set[str]:
    """扫描输出目录下既有 swebench fixture 的 instance_id（OQ-V3 排除用）。"""
    root = Path(tasks_dir)
    ids: set[str] = set()
    for task_json in root.glob("swebench-*/task.json"):
        task = json.loads(task_json.read_text())
        iid = task.get("instance_id")
        if iid:
            ids.add(iid)
    return ids


def _probe_dataset(ds) -> None:
    """首拉后打印字段名/size/difficulty 分布，字段缺失早暴露（grill OQ-V1②）。"""
    try:
        if hasattr(ds, "features") and ds.features:
            fields = sorted(ds.features)
        else:
            first = next(iter(ds), None)
            fields = sorted(first.keys()) if first else []
    except Exception:
        fields = []
    print(f"[probe] dataset fields: {fields}")
    try:
        print(f"[probe] dataset size: {len(ds)}")
    except Exception as exc:
        print(f"[probe] dataset size: 未知（{exc}）")
    try:
        dist = Counter((ex.get("difficulty") or "(missing)") for ex in ds)
    except Exception:
        dist = Counter()
    print(f"[probe] difficulty 分布: {dict(dist)}")


def _sample_task_dirs(created: list[Path], per_repo: int = 1) -> list[Path]:
    """抽样自检目录：每 repo 取前 ``per_repo`` 条（OQ-V2①）。"""
    by_repo: dict[str, list[Path]] = {}
    for d in created:
        task = json.loads((Path(d) / "task.json").read_text())
        by_repo.setdefault(task.get("repo", "?"), []).append(Path(d))
    sample: list[Path] = []
    for repo in sorted(by_repo):
        sample.extend(sorted(by_repo[repo])[:per_repo])
    return sample


def update_manifest_verified(tasks_dir: str | Path) -> dict:
    """统计目录下 track=verified 的 swebench fixture，更新 manifest verified 摘要段。

    OQ-V6①：摘要计数（count/by_repo/by_difficulty），不登记明细数组；不占
    coverage 矩阵（既有消费方只读固定键，新增顶层键安全）。
    """
    root = Path(tasks_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        print(f"[manifest] 未找到 {manifest_path}，跳过 verified 登记")
        return {}
    data = json.loads(manifest_path.read_text())
    by_repo: Counter = Counter()
    by_difficulty: Counter = Counter()
    count = 0
    for task_json in sorted(root.glob("swebench-*/task.json")):
        task = json.loads(task_json.read_text())
        if task.get("track") != "verified":
            continue
        count += 1
        by_repo[task.get("repo", "?")] += 1
        by_difficulty[task.get("difficulty", "?")] += 1
    verified = {
        "count": count,
        "by_repo": dict(by_repo),
        "by_difficulty": dict(by_difficulty),
        "updated_at": datetime.date.today().isoformat(),
        "note": "Verified 精选子集摘要（track=verified 计数，不占能力覆盖矩阵）",
    }
    data["verified"] = verified
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"[manifest] verified 段已更新: count={count}")
    return verified


def cmd_build_subset(args) -> int:
    """build-subset：加载（HF_ENDPOINT 镜像）→ 字段探针 → 排除既有 → 选 40 → 落盘 → validate → 抽样自检 → manifest。"""
    from benchmarks.swebench_convert import (
        GITEE_PREFERRED_URLS,
        generate_tasks,
        load_verified,
    )

    print("[load] 加载 Verified 数据集（HF_ENDPOINT 走镜像，直连不可达环境自动 fallback 需设环境变量）...")
    ds = load_verified()
    _probe_dataset(ds)
    instances = list(ds)

    targets = parse_targets(args.targets)
    print(f"[targets] 配比: {targets}")

    known_bad = load_known_bad(args.known_bad_file)
    if args.known_bad_file:
        print(f"[known_bad] 从 {args.known_bad_file} 加载 {len(known_bad)} 条")
    else:
        print("[known_bad] 未指定 --known-bad-file，接受空集（OQ-V4；坏实例靠 L2 兜底）")

    existing_ids = collect_existing_instance_ids(args.output)
    if existing_ids:
        print(f"[exclude] 选择池排除既有 {len(existing_ids)} 条 instance_id（OQ-V3）")

    plan = build_subset(
        instances, targets=targets, known_bad=known_bad, exclude_ids=existing_ids
    )
    print(f"[select] {plan.summary()}")
    if not plan.selected:
        print("未选中任何实例，退出")
        return 1

    iids = [ex["instance_id"] for ex in plan.selected]

    if args.resume:
        existing_dirs = {
            p.parent.name[len("swebench-"):]
            for p in Path(args.output).glob("swebench-*/task.json")
        }
        skip = [iid for iid in iids if iid in existing_dirs]
        iids = [iid for iid in iids if iid not in existing_dirs]
        print(f"[resume] 跳过已存在 {len(skip)} 条（续跑）：{sorted(skip)}")

    print(f"[generate] 落盘 {len(iids)} 条 fixture 到 {args.output}")
    created = generate_tasks(iids, args.output, dataset=ds, repo_urls=GITEE_PREFERRED_URLS)

    problems = validate_fixtures_dir(args.output)
    if problems:
        for task_id, errors in problems:
            print(f"INVALID {task_id}: {'; '.join(errors)}")
        return 1
    print("[validate] 全部 swebench fixture 元数据校验通过")

    if args.skip_gold_check:
        print("[gold-check] --skip-gold-check：跳过 L3 自检（结果页/文档标注未自检）")
    else:
        if args.full_gold_check:
            sample = list(created)
            print(f"[gold-check] 全量自检 {len(sample)} 条（--full-gold-check）")
        else:
            sample = _sample_task_dirs(created)
            print(f"[gold-check] 抽样自检 {len(sample)} 条（每 repo 1 条，OQ-V2①）")
        gold_results = []
        for d in sample:
            name = Path(d).name
            try:
                rc = gold_check(d, install_deps=True)
                status = "PASS" if rc == 0 else f"FAIL rc={rc}"
            except SystemExit as exc:
                status = f"SYSTEMEXIT {exc}"
            except Exception as exc:  # noqa: BLE001 - 单条自检失败只记录不中断
                status = f"ERROR {type(exc).__name__}: {exc}"
            gold_results.append((name, status))
            print(f"[gold-check] {name}: {status}")
        pass_count = sum(1 for _, s in gold_results if s == "PASS")
        print(
            f"[gold-check] 自检完成：PASS {pass_count}/{len(gold_results)}；"
            "其余记录未自检/失败，fixture 不删除（OQ-V2③，40 可略少）"
        )

    update_manifest_verified(args.output)
    return 0


def cmd_validate_dir(args) -> int:
    problems = validate_fixtures_dir(args.tasks_dir)
    if problems:
        for task_id, errors in problems:
            print(f"INVALID {task_id}: {'; '.join(errors)}")
        return 1
    print("all fixtures valid")
    return 0


def cmd_gold_check(args) -> int:
    return gold_check(args.task_dir, timeout=args.timeout, install_deps=args.install_deps)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SWE-bench Verified 子集工具")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build-subset", help="加载 Verified → 选子集 → 落盘 fixture → 校验 → 抽样自检")
    b.add_argument("--output", default="benchmarks/tasks", help="输出目录（默认 benchmarks/tasks）")
    b.add_argument("--targets", default=None, help="逗号分隔短名配比，如 requests+4,flask+6（默认 SUBSET_TARGETS）")
    b.add_argument("--skip-gold-check", action="store_true", help="跳过 L3 抽样自检")
    b.add_argument("--full-gold-check", action="store_true", help="全量跑 L3 自检（默认抽样每 repo 1 条）")
    b.add_argument("--resume", action="store_true", help="续跑：跳过输出目录已存在的 instance_id")
    b.add_argument("--known-bad-file", metavar="FILE", help="每行一个 instance_id 的 KNOWN_BAD 清单")
    b.set_defaults(func=cmd_build_subset)

    v = sub.add_parser("validate-dir", help="校验目录下 swebench fixture 元数据")
    v.add_argument("tasks_dir", metavar="TASKS_DIR")
    v.set_defaults(func=cmd_validate_dir)

    g = sub.add_parser("gold-check", help="对单个任务做 L3 金补丁自检")
    g.add_argument("task_dir", metavar="TASK_DIR")
    g.add_argument("--install-deps", action="store_true", help="自检前在隔离 venv 装依赖（external_repo 实例需要）")
    g.add_argument("--timeout", type=int, default=600)
    g.set_defaults(func=cmd_gold_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

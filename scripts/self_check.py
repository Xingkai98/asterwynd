#!/usr/bin/env python3
"""结果自洽性五门禁检查（C3 evaluation-protocol-reporting）。

用法:
    uv run python scripts/self_check.py <run_dir> [--skip <n>]...

``run_dir`` 可以是单轮目录（含 run.json + tasks/）或聚合 runs 目录（含轮次子目录与
evaluation-report.md）。门禁：

1. 同模型同 harness 复现（报告元组存在；多轮时跨轮一致）
2. seed 复现（采样参数 temperature/seed/model_version 记录完整）
3. 失败归因闭环（failed/error 均有 fault_owner；reason×owner 交叉表可渲染）
4. 披露段齐全（结果页含 spec 披露清单全部段：报告元组/污染注记/反作弊/fault_owner
   交叉表/成本定价/采样参数/小N/过程效率/能力覆盖矩阵）
5. 报告元组完整（model/harness/task_set_hash/成本口径字段齐全）

任一缺失项输出具体项并以非零退出码表达；``--skip <n>`` 可跳过指定门禁（可重复）。
全部通过 exit 0。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Gate 4 disclosure headings — the spec-delta "披露段齐全" list is the single
# source of truth (Q11); the capability coverage matrix is checked alongside
# (independent Requirement, the renderer always emits the heading).
DISCLOSURE_HEADINGS: tuple[str, ...] = (
    "## 报告元组",
    "## SWE-bench 污染注记",
    "## 反作弊泄漏披露",
    "## reason × fault_owner 交叉表",
    "## 成本与定价",
    "## 采样参数",
    "## 小样本声明",
    "## 过程效率",
    "## 能力覆盖矩阵",
)

FAILURE_STATUSES = {"failed", "error"}
TUPLE_FIELDS = (
    "model",
    "adapter_version",
    "prompt_version",
    "task_set_hash",
    "pricing_table_version",
)


@dataclass
class GateResult:
    gate: str
    name: str
    ok: bool
    issues: list[str]

    def render(self) -> str:
        if not self.ok:
            details = "; ".join(self.issues) if self.issues else "未知原因"
            return f"GATE {self.gate} FAIL [{self.name}]: {details}"
        return f"GATE {self.gate} PASS [{self.name}]"


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _collect_run_jsons(run_dir: Path) -> list[dict]:
    """Return one run.json dict per round (single round or aggregate dir)."""
    run_json = run_dir / "run.json"
    if run_json.exists():
        return [_load_json(run_json)]
    found: list[dict] = []
    for sub in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        candidate = sub / "run.json"
        if candidate.exists():
            found.append(_load_json(candidate))
    return found


def _collect_results(run_dir: Path) -> list[dict]:
    """Every result.json across rounds (aggregate) or the single round."""
    tasks_roots: list[Path] = []
    if (run_dir / "tasks").is_dir():
        tasks_roots.append(run_dir / "tasks")
    for sub in run_dir.iterdir():
        if sub.is_dir() and (sub / "tasks").is_dir():
            tasks_roots.append(sub / "tasks")
    results: list[dict] = []
    for tasks_root in tasks_roots:
        for task_dir in sorted(tasks_root.iterdir()):
            result_path = task_dir / "result.json"
            if result_path.exists():
                results.append(_load_json(result_path))
    return results


def _find_report(run_dir: Path) -> Path | None:
    """Locate the aggregate result page for disclosure checks."""
    direct = run_dir / "evaluation-report.md"
    if direct.exists():
        return direct
    parent = run_dir.parent / "evaluation-report.md"
    if parent.exists():
        return parent
    return None


def gate1(run_jsons: list[dict]) -> GateResult:
    """同模型同 harness 复现：报告元组存在；多轮时跨轮一致。"""
    issues: list[str] = []
    if not run_jsons:
        return GateResult("1", "复现", False, ["未找到 run.json"])
    for i, meta in enumerate(run_jsons):
        if not meta.get("model"):
            issues.append(f"round {i}: model 缺失")
        if not meta.get("adapter_version"):
            issues.append(f"round {i}: harness.adapter_version 缺失")
        if not meta.get("prompt_version"):
            issues.append(f"round {i}: harness.prompt_version 缺失")
    if len(run_jsons) > 1:
        first = (
            run_jsons[0].get("model"),
            run_jsons[0].get("adapter_version"),
            run_jsons[0].get("prompt_version"),
        )
        for i, meta in enumerate(run_jsons[1:], start=1):
            cur = (
                meta.get("model"),
                meta.get("adapter_version"),
                meta.get("prompt_version"),
            )
            if cur != first:
                issues.append(f"round {i}: 模型/harness 元组与 round 0 不一致")
    return GateResult("1", "复现", not issues, issues)


def gate2(run_jsons: list[dict]) -> GateResult:
    """seed 复现：采样参数记录完整。"""
    if not run_jsons:
        return GateResult("2", "seed 复现", False, ["未找到 run.json"])
    issues: list[str] = []
    for i, meta in enumerate(run_jsons):
        for field in ("temperature", "seed", "model_version"):
            if meta.get(field) is None:
                issues.append(f"round {i}: 采样参数 {field} 缺失")
    return GateResult("2", "seed 复现", not issues, issues)


def gate3(run_dir: Path) -> GateResult:
    """失败归因闭环：failed/error 均有 fault_owner（无 κ artifact，Q9 降级）。"""
    results = _collect_results(run_dir)
    failures = [r for r in results if r.get("status") in FAILURE_STATUSES]
    if not failures:
        return GateResult("3", "失败归因", True, [])
    missing = [r.get("task_id", "?") for r in failures if not r.get("fault_owner")]
    if missing:
        preview = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
        return GateResult(
            "3", "失败归因", False,
            [f"{len(missing)} 个失败样本缺 fault_owner: {preview}"],
        )
    return GateResult("3", "失败归因", True, [])


def gate4(run_dir: Path) -> GateResult:
    """披露段齐全：结果页含 spec 披露清单全部段。"""
    report = _find_report(run_dir)
    if report is None:
        return GateResult("4", "披露段", False, ["未找到结果页 evaluation-report.md"])
    text = report.read_text(encoding="utf-8")
    missing = [h for h in DISCLOSURE_HEADINGS if h not in text]
    if missing:
        return GateResult("4", "披露段", False, [f"缺失披露段: {', '.join(missing)}"])
    return GateResult("4", "披露段", True, [])


def gate5(run_jsons: list[dict]) -> GateResult:
    """报告元组完整：model/harness/task_set_hash/成本口径字段齐全。"""
    if not run_jsons:
        return GateResult("5", "报告元组", False, ["未找到 run.json"])
    issues: list[str] = []
    for i, meta in enumerate(run_jsons):
        for field in TUPLE_FIELDS:
            if not meta.get(field):
                issues.append(f"round {i}: 报告元组 {field} 缺失")
    return GateResult("5", "报告元组", not issues, issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="结果自洽性五门禁检查")
    parser.add_argument("run_dir", type=Path, help="单轮 run 目录或聚合 runs 目录")
    parser.add_argument(
        "--skip",
        type=int,
        action="append",
        default=[],
        help="跳过指定门禁（可重复：--skip 3 --skip 4）",
    )
    args = parser.parse_args(argv)

    skipped = set(args.skip)
    run_dir: Path = args.run_dir
    if not run_dir.exists():
        print(f"error: run_dir 不存在: {run_dir}", file=sys.stderr)
        return 1

    run_jsons = _collect_run_jsons(run_dir)
    gates: list[tuple[str, str, callable]] = [
        ("1", "复现", lambda: gate1(run_jsons)),
        ("2", "seed 复现", lambda: gate2(run_jsons)),
        ("3", "失败归因", lambda: gate3(run_dir)),
        ("4", "披露段", lambda: gate4(run_dir)),
        ("5", "报告元组", lambda: gate5(run_jsons)),
    ]

    failed: list[str] = []
    for number, _name, fn in gates:
        if int(number) in skipped:
            print(f"GATE {number} SKIPPED")
            continue
        result = fn()
        print(result.render())
        if not result.ok:
            failed.append(number)

    if failed:
        print(f"self_check FAIL: 门禁 {', '.join(failed)} 未通过")
        return 1
    print("self_check PASS：五门禁全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

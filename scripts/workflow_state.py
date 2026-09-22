#!/usr/bin/env python3
"""Workflow state management CLI — 事件投影查询、受保护写通道与策略源更新。

Usage:
    uv run python scripts/workflow_state.py flow status [--change <id>|--all]
    uv run python scripts/workflow_state.py disable --reason <reason>
    uv run python scripts/workflow_state.py enable --reconcile-change <id>
    uv run python scripts/workflow_state.py resume-audit
    uv run python scripts/workflow_state.py artifact-event --change <id> --event-type <type> ...
    uv run python scripts/workflow_state.py review-manifest --change <id> --phase <phase> ...
    uv run python scripts/workflow_state.py policy-show | policy-validate | policy-set

四阶段状态机的 legacy 子命令（`discover` / `current` / `validate` / `spawn`）与 gate 家族
（`flow approve` / `advance` / `block` / `confirm`）已随子系统退役删除——它们无生产调用方，
且 `flow approve` 对当代 change 必报错。开发流程推进由 OpenSpec 主干承担。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Import shared workflow constants from the canonical source
sys.path.insert(0, str(_PROJECT_ROOT))
from agent.workflow.event_log import (  # noqa: E402
    ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES,
    append_protected_artifact_event,
    event_log_path,
    project_workflow_state,
    replay_handoff_projection,
    verify_projection,
    workflow_state_path,
)
from agent.workflow.review_manifest import change_dir_for, write_review_manifest  # noqa: E402
from agent.workflow.routing import is_workflow_enabled  # noqa: E402
from agent.workflow.resume_audit import (  # noqa: E402
    record_resume_reconciliation,
    run_resume_audit,
    write_resume_baseline,
)
from agent.workflow.state_machine import StateMachineError  # noqa: E402

METHODS_PATH = _SCRIPT_DIR / "workflow_methods.json"


def _resolve_changes_root() -> Path:
    """Resolve the changes directory from workflow_methods.json doc_artifact config."""
    methods_path = _SCRIPT_DIR / "workflow_methods.json"
    try:
        if methods_path.exists():
            methods = json.loads(methods_path.read_text(encoding="utf-8"))
            doc_artifact = methods.get("doc_artifact", {})
            paths = doc_artifact.get("paths", {})
            tmpl = paths.get("change_dir_template", "openspec/changes/{change_id}")
            base = tmpl.split("/{")[0] if "/{" in tmpl else tmpl.rsplit("/", 1)[0]
            return Path(base)
    except (json.JSONDecodeError, OSError):
        pass
    return Path("openspec/changes")


CHANGES_ROOT = _resolve_changes_root()

# ── Methods loading ──

_methods_cache: dict | None = None


def _load_methods() -> dict:
    global _methods_cache
    if _methods_cache is not None:
        return _methods_cache
    if METHODS_PATH.exists():
        try:
            _methods_cache = json.loads(METHODS_PATH.read_text(encoding="utf-8"))
            return _methods_cache
        except Exception:
            pass
    _methods_cache = {}
    return _methods_cache


def _write_methods(methods: dict) -> None:
    global _methods_cache
    with METHODS_PATH.open("w", encoding="utf-8") as f:
        json.dump(methods, f, indent=2, ensure_ascii=False)
        f.write("\n")
    _methods_cache = methods


def _set_workflow_enabled(enabled: bool) -> None:
    methods = dict(_load_methods())
    workflow = methods.get("workflow", {})
    if not isinstance(workflow, dict):
        workflow = {}
    workflow["enabled"] = enabled
    methods["workflow"] = workflow
    _write_methods(methods)


# ── Helpers ──

def _all_change_ids(root: Path = CHANGES_ROOT) -> list[str]:
    """List active change ids: handoff.json 或 workflow-state.json 或 workflow-events.jsonl。

    代码层修正 6：原实现只列「有 handoff.json」的目录，当代 change（change_created 开头、
    无 handoff.json）会被 flow status --all / discover 漏掉。
    """
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir()
        and d.name != "archive"
        and (
            (d / "handoff.json").exists()
            or (d / "workflow-state.json").exists()
            or (d / "workflow-events.jsonl").exists()
        )
    )


def _save_handoff(change_id: str, data: dict, root: Path = CHANGES_ROOT) -> None:
    path = root / change_id / "handoff.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    Path(tmp).replace(path)


def _resolve_review_base_sha(repo_root: Path) -> str | None:
    for args in (
        ["git", "merge-base", "HEAD", "origin/master"],
        ["git", "merge-base", "HEAD", "master"],
        ["git", "rev-parse", "HEAD~1"],
    ):
        result = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value:
                return value
    return None


# ── Commands ──

def cmd_disable(args: argparse.Namespace) -> int:
    baseline = write_resume_baseline(
        _PROJECT_ROOT,
        created_by=args.who or "human",
        reason=args.reason or "workflow disabled",
    )
    _set_workflow_enabled(False)
    print(f"workflow 已禁用，resume baseline 已写入: {baseline}")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    audit = run_resume_audit(_PROJECT_ROOT)
    if audit.needs_reconciliation and not args.reconcile_change:
        for error in audit.errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print("workflow 保持禁用；请先完成 resume-audit reconciliation。", file=sys.stderr)
        return 1

    if args.reconcile_change:
        try:
            event_log = record_resume_reconciliation(
                _PROJECT_ROOT,
                args.reconcile_change,
                approved_by=args.who or "human",
                reason=args.reason or "workflow resume reconciled",
                audit_result=audit,
                clear_baseline=True,
            )
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1
        print(f"已记录 workflow resume reconciliation: {event_log}")
    elif audit.baseline_present and audit.baseline_path.exists():
        audit.baseline_path.unlink()

    _set_workflow_enabled(True)
    print("workflow 已启用。")
    return 0


def cmd_resume_audit(args: argparse.Namespace) -> int:
    audit = run_resume_audit(_PROJECT_ROOT)
    if args.reconcile_change:
        try:
            event_log = record_resume_reconciliation(
                _PROJECT_ROOT,
                args.reconcile_change,
                approved_by=args.approved_by,
                reason=args.reason,
                audit_result=audit,
                clear_baseline=not args.keep_baseline,
            )
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1
        print(f"已记录 workflow resume reconciliation: {event_log}")
        return 0

    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, ensure_ascii=False))
    else:
        if not audit.baseline_present:
            print(f"无 workflow resume baseline: {audit.baseline_path}")
        elif audit.needs_reconciliation:
            for error in audit.errors:
                print(f"FAIL: {error}")
        else:
            print("PASS: workflow resume audit 已通过")
        for warning in audit.warnings:
            print(f"WARN: {warning}")
    return 1 if audit.needs_reconciliation else 0


def cmd_flow_status(args: argparse.Namespace) -> int:
    if args.all:
        result: dict = {}
        had_error = 0
        for cid in _all_change_ids():
            projection, error = _flow_status_projection(cid)
            if error:
                result[cid] = {"error": error}
                had_error = 1
            else:
                result[cid] = projection
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return had_error
    if not args.change:
        print("错误：flow status 需要 --change <id> 或 --all", file=sys.stderr)
        return 1
    projection, error = _flow_status_projection(args.change)
    if error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(projection, indent=2, ensure_ascii=False))
    return 0


# ── flow status helpers ───────────────────────────────────────────────

def _flow_is_gen1(change_dir: Path) -> bool:
    """True 当事件日志首事件为 initialized（老世代，handoff.json 驱动）。"""
    events_path = event_log_path(change_dir)
    if not events_path.exists():
        return False
    for line in events_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            return json.loads(stripped).get("event_type") == "initialized"
        except json.JSONDecodeError:
            return False
    return False


def _flow_resolve_change_dir(change_id: str) -> Path | None:
    """解析 change 目录：active 目录优先；归档目录（openspec/changes/archive/<date>-<id>）只读可查。"""
    change_dir = CHANGES_ROOT / change_id
    if change_dir.exists():
        return change_dir
    archive_dir = CHANGES_ROOT / "archive" / change_id
    if archive_dir.exists():
        return archive_dir
    return None


def _flow_status_projection(change_id: str) -> tuple[dict | None, str | None]:
    """投影 + 自愈重建（Q3/Q6）：投影缺失/损坏/stale 时用事件 replay 重建并落盘。"""
    change_dir = _flow_resolve_change_dir(change_id)
    if change_dir is None:
        return None, f"错误：change '{change_id}' 不存在"
    events_path = event_log_path(change_dir)
    if not events_path.exists():
        return None, f"错误：change '{change_id}' 没有 workflow-events.jsonl"
    try:
        projection = project_workflow_state(change_dir)
    except StateMachineError as exc:
        return None, f"错误：事件不完整，检查 seq（{exc}）"
    is_archived = "archive" in change_dir.parts
    if _flow_is_gen1(change_dir) or is_archived:
        # 老世代/归档：handoff.json 即投影，只读不落盘 workflow-state.json（Q13）
        return {**projection, "stale": False}, None
    stale = False
    ws_path = workflow_state_path(change_dir)
    if ws_path.exists():
        try:
            disk = json.loads(ws_path.read_text(encoding="utf-8"))
        except Exception:
            disk = None
        if disk != projection:
            stale = True
    else:
        stale = True
    if stale:
        # 自愈重建：写新鲜投影（不再映射写 handoff.json）
        _refresh_workflow_state(change_dir, projection)
    return {**projection, "stale": stale}, None


def _is_archived_change_dir(change_dir: Path) -> bool:
    """change 目录是否位于 `CHANGES_ROOT/archive/` 之下（用路径前缀判定，不猜目录名）。

    active 优先解析下，本判据与「active 目录不存在」等价（`change_dir_for(archived=True)`
    的返回值恒在 archive 下）；取路径前缀更直接，且不依赖调用方记得在哪一步置位。
    """
    return CHANGES_ROOT / "archive" in change_dir.parents


def _archive_dir_matches_change_id(change_dir: Path, change_id: str) -> bool:
    """归档目录名是否**就是**该 change（裸 `<id>` 或 `<date>-<id>`，不允许更长前缀）。

    `review_manifest.change_dir_for` 的前缀正则用 `re.match` 且无 `$` 锚点
    （`review_manifest.py:47`），`alpha` 会命中 `2026-09-22-alpha-beta`——**另一个
    change** 的目录，且结果依赖 `iterdir()` 顺序。本处做调用侧事后断言，不一致时
    fail-closed（宁可不写也不写错 change）。修复该正则属独立决策，记在
    `docs/known-debt.md`。
    """
    name = change_dir.name
    if name == change_id:
        return True
    return re.fullmatch(rf"\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(change_id)}", name) is not None


def _require_change_target(change_id: str) -> tuple[Path, bool] | None:
    """受保护写通道的目标合法性判定（issue #199）+ 归档回退（issue #232 盲区 A）。

    返回 `(change_dir, is_archived)`；失败打印错误并返回 `None`。

    前置为「change 目录存在 且（`proposal.md` 或 `handoff.json` 存在）」：

    - 当代 change 立项即产出 `proposal.md`，它是合法目标的最低配置锚点；
      不要求 `workflow-events.jsonl`——首次 `artifact-event` 恰是创建该文件的动作，
      以事件日志为前置会自锁。
    - `handoff.json` 分支保留老世代目标的可写性：历史 spawn 子 change（由已退役的
      `cmd_spawn` 产生）只有 `handoff.json` 而**没有** `proposal.md`，只认
      `proposal.md` 会把它们从「可写」打回 exit 1。

    目标解析为 **active 优先 → 归档回退**。归档回退委托
    `review_manifest.change_dir_for(archived=True)`：回退拼裸 id 的实现
    （`archive/<id>`）对仓库全部带 `YYYY-MM-DD-` 前缀的归档目录是死代码（实测返回
    `None`）。委托它还保证「事件落点」与「manifest 落点」由同一算法决定，避免
    两个解析入口再次漂移（issue #232）。
    """
    # change_id 必须是单段目录名：`CHANGES_ROOT / change_id` 对绝对路径会整体替换
    # 根（可指向仓库外），对含 `/` 的相对路径会解析到子目录，而下游按
    # `change_dir.name` 重拼路径（`_save_handoff`）会落到不存在的位置抛裸 traceback。
    # 仓库内所有调用方都传裸 id，故直接拒绝（issue #199 R2 审阅 New-1 / 问题 4）。
    if Path(change_id).is_absolute() or "/" in change_id or "\\" in change_id:
        print(f"错误：change id '{change_id}' 非法（应为单段目录名）", file=sys.stderr)
        return None
    # 归档目录带日期前缀，查询串必须是裸 id：否则写入事件的 `change_id` 字段会带
    # 日期，CI 的 `_change_id_for_event_log` 剥前缀后比对不上（`change_id mismatch`），
    # PR 门禁红且难查（issue #232 Q4）。
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}-.+", change_id):
        print(
            f"错误：change id '{change_id}' 非法（请用不含日期前缀的裸 change id）",
            file=sys.stderr,
        )
        return None
    change_dir = CHANGES_ROOT / change_id
    if not change_dir.exists():
        # 归档回退：委托 change_dir_for。repo_root 由 CHANGES_ROOT.parent.parent 推导，
        # **不能**用 _PROJECT_ROOT——后者是仓库绝对路径，会让测试/子进程在别处解析。
        archived_dir = change_dir_for(CHANGES_ROOT.parent.parent, change_id, archived=True)
        if not archived_dir.exists():
            print(f"错误：change '{change_id}' 不存在", file=sys.stderr)
            return None
        if not _archive_dir_matches_change_id(archived_dir, change_id):
            print(
                f"错误：change '{change_id}' 解析到归档目录 '{archived_dir.name}'，"
                "目录名与 change id 不匹配（拒绝写入以避免污染其它 change）",
                file=sys.stderr,
            )
            return None
        change_dir = archived_dir
    if not (change_dir / "proposal.md").exists() and not (change_dir / "handoff.json").exists():
        print(
            f"错误：change '{change_id}' 不是合法 change（缺 proposal.md 且无 handoff.json）",
            file=sys.stderr,
        )
        return None
    # 归档与否由**解析结果**决定（路径前缀），不由「走了哪条分支」决定：调用方无法
    # 忘记置位，也避免将来新增解析路径时漏判。
    return change_dir, _is_archived_change_dir(change_dir)


def _after_protected_write(change_dir: Path, is_archived: bool) -> None:
    """受保护写通道成功写入后的收尾（issue #232 盲区 A）。

    - active 目标：刷新投影，使写入结果可立即被校验（#199 行为不变）。
    - 归档目标：**不刷新**——归档目录是已提交的历史，`_flow_refresh_after_event` 会
      在其中写出 `handoff.json` + `workflow-state.json` 等未跟踪产物（#228 类污染，
      落在归档目录比 active 更严重）。改为做一次**只读**一致性校验：若归档目录里
      已有投影且与事件日志不一致（仓库实测 1/89 命中），仅告警、不落盘、不失败——
      既点亮盲区，又不阻断收尾。
    """
    if not is_archived:
        _flow_refresh_after_event(change_dir)
        return
    try:
        errors = verify_projection(change_dir)
    except Exception as exc:  # 只读校验不得影响写入结果
        print(f"警告：归档投影校验未能完成（{exc}）", file=sys.stderr)
        return
    if errors:
        print(
            "警告：归档投影与事件日志不一致（只读校验，未落盘）：" + "；".join(errors),
            file=sys.stderr,
        )


def _flow_refresh_after_event(change_dir: Path) -> None:
    """写事件后刷新投影：gen-1 同步 handoff.json，gen-2 写 workflow-state.json。"""
    if _flow_is_gen1(change_dir):
        # gen-1 的 handoff.json 是它**唯一**的投影载体（不是 gen-2 的映射写），保留。
        try:
            _save_handoff(change_dir.name, replay_handoff_projection(change_dir))
        except StateMachineError as exc:
            print(f"错误：handoff.json 同步失败：{exc}", file=sys.stderr)
    else:
        _refresh_workflow_state(change_dir)


def _refresh_workflow_state(change_dir: Path, projection: dict | None = None) -> None:
    """写 workflow-state.json（gen-2 投影，issue #228 层 1：不再映射写 handoff.json）。"""
    if projection is None:
        try:
            projection = project_workflow_state(change_dir)
        except StateMachineError:
            return
    _atomic_write_json(workflow_state_path(change_dir), projection)


def cmd_artifact_event(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        print(
            "错误：workflow 已在 workflow_methods.json 中禁用，artifact-event 不可用",
            file=sys.stderr,
        )
        return 1
    target = _require_change_target(args.change)
    if target is None:
        return 1
    change_dir, is_archived = target

    try:
        append_protected_artifact_event(
            change_dir,
            args.change,
            args.event_type,
            args.artifact_path,
            args.reason,
            args.approved_by,
        )
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    _after_protected_write(change_dir, is_archived)
    print(f"已记录 artifact 事件: {args.event_type} ({args.artifact_path})")
    return 0


def cmd_review_manifest(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        print(
            "错误：workflow 已在 workflow_methods.json 中禁用，review-manifest 不可用",
            file=sys.stderr,
        )
        return 1
    target = _require_change_target(args.change)
    if target is None:
        return 1
    change_dir, is_archived = target

    repo_root = Path.cwd()
    base_sha = args.base_sha or _resolve_review_base_sha(repo_root)
    if not base_sha:
        print("错误：无法推导 review manifest 的 base sha", file=sys.stderr)
        return 1

    try:
        path = write_review_manifest(
            repo_root,
            args.change,
            args.phase,
            reviewer_run_id=args.reviewer_run_id,
            base_sha=base_sha,
            head_sha=args.head_sha,
            verdict=args.verdict,
            archived=is_archived,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    _after_protected_write(change_dir, is_archived)
    print(f"已写入 review manifest: {path}")
    return 0


# ── policy-*（flow-policy-source P0 单一策略源合法更新通道）────────────

_POLICY_PATH = _SCRIPT_DIR / "flow-policy.json"


def _read_policy() -> dict | None:
    try:
        data = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def cmd_policy_show(args: argparse.Namespace) -> int:
    data = _read_policy()
    if data is None:
        print(f"错误：{_POLICY_PATH} 缺失或不是合法 JSON", file=sys.stderr)
        return 1
    rules = data.get("protected_paths", [])
    print(f"{'path':<45} {'match_type':<10} {'governance':<18} event_types")
    print("-" * 100)
    for r in rules:
        if not isinstance(r, dict):
            continue
        et = ",".join(r.get("event_types", []) or []) or "-"
        print(
            f"{r.get('path',''):<45} {r.get('match_type',''):<10} "
            f"{r.get('governance',''):<18} {et}"
        )
    print(f"\n共 {len(rules)} 条受保护路径规则（phases/review agent schema 见 flow-policy.json）")
    return 0


def cmd_policy_validate(args: argparse.Namespace) -> int:
    import scripts.check_openspec_artifacts as checker
    import scripts.workflow_guard as guard

    errors: list[str] = []

    data = _read_policy()
    if data is None:
        errors.append(f"{_POLICY_PATH} 缺失或不是合法 JSON")
    try:
        if checker._load_protected_path_rules(_PROJECT_ROOT) is None:
            errors.append("受保护路径规则表加载失败（event_explained 规则缺失 event_types 或结构非法）")
    except RuntimeError as exc:
        errors.append(f"受保护路径规则表 schema 非法: {exc}")
    schema_errs = checker._validate_policy_agent_schema(_PROJECT_ROOT)
    errors.extend(schema_errs)

    # parity：磁盘表 event_explained 子集 == guard 内嵌默认表 event_explained 子集
    if data is not None:
        disk = {
            (r.get("path"), r.get("match_type"), tuple(r.get("event_types", [])))
            for r in data.get("protected_paths", [])
            if isinstance(r, dict) and r.get("governance") == "event_explained"
        }
        default = {
            (r.get("path"), r.get("match_type"), tuple(r.get("event_types", [])))
            for r in guard._DEFAULT_PROTECTED_PATHS
            if r.get("governance") == "event_explained"
        }
        if disk != default:
            errors.append(
                "磁盘策略表 event_explained 子集与 guard 内嵌默认表不一致（parity 漂移）——"
                "请同步 scripts/workflow_guard.py 的 _DEFAULT_PROTECTED_PATHS"
            )

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("flow-policy.json 校验通过（schema 合法 + 与 guard 内嵌默认表 parity 一致）")
    return 0


def cmd_policy_set(args: argparse.Namespace) -> int:
    import scripts.check_openspec_artifacts as checker

    data = _read_policy()
    if data is None:
        print(f"错误：{_POLICY_PATH} 缺失或不是合法 JSON", file=sys.stderr)
        return 1
    rules = data.setdefault("protected_paths", [])
    if not isinstance(rules, list):
        print("错误：flow-policy.json 的 protected_paths 不是数组", file=sys.stderr)
        return 1

    if args.delete:
        before = len(rules)
        rules[:] = [r for r in rules if not (isinstance(r, dict) and r.get("path") == args.path)]
        if len(rules) == before:
            print(f"未找到要删除的规则: {args.path}", file=sys.stderr)
            return 1
        verb = "删除"
    else:
        if not args.match_type or not args.governance:
            print("错误：--match-type 与 --governance 必填（--delete 时除外）", file=sys.stderr)
            return 1
        entry: dict = {"path": args.path, "match_type": args.match_type, "governance": args.governance}
        if args.event_types:
            entry["event_types"] = [t.strip() for t in args.event_types.split(",") if t.strip()]
        for i, r in enumerate(rules):
            if isinstance(r, dict) and r.get("path") == args.path:
                rules[i] = entry
                break
        else:
            rules.append(entry)
        verb = "写入"

    try:
        if checker._load_protected_path_rules(_PROJECT_ROOT) is None:
            print("错误：写入后策略规则表校验失败（请检查 match-type/governance/event-types）", file=sys.stderr)
            return 1
    except RuntimeError as exc:
        print(f"错误：写入后策略规则表 schema 非法: {exc}", file=sys.stderr)
        return 1

    _atomic_write_json(_POLICY_PATH, data)
    print(f"已{verb}策略规则: {args.path}（{_POLICY_PATH}）")
    return 0


# ── CLI ──

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Workflow 状态管理 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("disable", help="禁用 workflow 并写入 resume baseline")
    p.add_argument("--who")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("enable", help="启用 workflow；如有 resume baseline，先执行恢复审计")
    p.add_argument("--who")
    p.add_argument("--reason")
    p.add_argument("--reconcile-change", help="将禁用期间改动归入指定 change 并记录 reconciliation 事件")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("resume-audit", help="检查 workflow 禁用期间产生的未恢复改动")
    p.add_argument("--json", action="store_true")
    p.add_argument("--reconcile-change", help="将禁用期间改动归入指定 change 并记录 reconciliation 事件")
    p.add_argument("--approved-by", default="human")
    p.add_argument("--reason", default="workflow resume reconciled")
    p.add_argument("--keep-baseline", action="store_true", help="记录事件后保留 baseline")
    p.set_defaults(func=cmd_resume_audit)

    p = sub.add_parser("flow", help="flow 命令组：投影查询")
    flow_sub = p.add_subparsers(dest="flow_command", required=True)

    p_status = flow_sub.add_parser("status", help="输出投影状态（唯一/默认 JSON）")
    p_status.add_argument("--change", help="指定 change id")
    p_status.add_argument("--all", action="store_true", help="所有 change")
    p_status.set_defaults(func=cmd_flow_status)

    p = sub.add_parser("artifact-event", help="记录 protected artifact 解释事件")
    p.add_argument("--change", required=True)
    p.add_argument(
        "--event-type",
        required=True,
        choices=sorted(ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES),
    )
    p.add_argument("--artifact-path", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--approved-by", required=True)
    p.set_defaults(func=cmd_artifact_event)

    p = sub.add_parser("review-manifest", help="写入阶段 review manifest")
    p.add_argument("--change", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--reviewer-run-id", required=True)
    p.add_argument("--base-sha")
    p.add_argument("--head-sha")
    p.add_argument("--verdict", default="PASS", choices=["PASS"])
    p.set_defaults(func=cmd_review_manifest)

    p = sub.add_parser("policy-show", help="展示 flow-policy.json 当前受保护路径规则")
    p.set_defaults(func=cmd_policy_show)

    p = sub.add_parser("policy-validate", help="校验 flow-policy.json（schema + 与 guard 内嵌默认表 parity）")
    p.set_defaults(func=cmd_policy_validate)

    p = sub.add_parser("policy-set", help="写入/删除 flow-policy.json 的单条受保护路径规则（原子写）")
    p.add_argument("--path", required=True, help="受保护路径模式")
    p.add_argument("--match-type", choices=["exact", "prefix", "contains"])
    p.add_argument("--governance", choices=["guard_only", "event_explained", "manifest_verified", "cli_written"])
    p.add_argument("--event-types", help="逗号分隔的事件类型列表（governance=event_explained 时必填）")
    p.add_argument("--delete", action="store_true", help="删除该 path 的规则")
    p.set_defaults(func=cmd_policy_set)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

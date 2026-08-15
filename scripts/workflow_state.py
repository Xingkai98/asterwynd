#!/usr/bin/env python3
"""Workflow state management CLI — discover, inspect, flow, spawn.

Usage:
    uv run python scripts/workflow_state.py discover
    uv run python scripts/workflow_state.py discover --format json
    uv run python scripts/workflow_state.py disable --reason <reason>
    uv run python scripts/workflow_state.py enable --reconcile-change <id>
    uv run python scripts/workflow_state.py resume-audit
    uv run python scripts/workflow_state.py current --change <id>
    uv run python scripts/workflow_state.py flow status [--change <id>|--all]
    uv run python scripts/workflow_state.py flow block --change <id> --awaiting <type>
    uv run python scripts/workflow_state.py flow confirm --change <id>
    uv run python scripts/workflow_state.py flow approve --change <id> --phase <phase>
    uv run python scripts/workflow_state.py flow advance --change <id> --to <sub_state>
    uv run python scripts/workflow_state.py artifact-event --change <id> --event-type <type> ...
    uv run python scripts/workflow_state.py review-manifest --change <id> --phase <phase> ...
    uv run python scripts/workflow_state.py validate --change <id>
    uv run python scripts/workflow_state.py spawn --from <wayfinding-id> --changes <id1,id2,...>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Import shared workflow constants from the canonical source
sys.path.insert(0, str(_PROJECT_ROOT))
from agent.workflow.models import (  # noqa: E402
    PHASE_ORDER,
    PHASE_SUB_STATES,
    PHASE_TO_ROLE,
    GATE_SUB_STATE,
    WORKTREE_REQUIRED_PHASES,
    StateSnapshot,
)
from agent.workflow.manager import WorkflowManager  # noqa: E402
from agent.workflow.event_log import (  # noqa: E402
    AWAITING_SUB_STATES,
    ALLOWED_PROTECTED_ARTIFACT_EVENT_TYPES,
    DEFAULT_SEED_STATE,
    _read_events,
    append_blocked_event,
    append_protected_artifact_event,
    append_transition_event,
    append_unblocked_event,
    append_wayfinding_children_event,
    event_log_path,
    is_awaiting_state,
    project_workflow_state,
    replay_handoff_projection,
    verify_projection,
    workflow_state_path,
    write_init_event,
)
from agent.workflow.review_manifest import write_review_manifest  # noqa: E402
from agent.workflow.routing import is_workflow_enabled  # noqa: E402
from agent.workflow.resume_audit import (  # noqa: E402
    record_resume_reconciliation,
    run_resume_audit,
    write_resume_baseline,
)
from agent.workflow.state_machine import (  # noqa: E402
    CROSS_PHASE_FORWARD,
    StateMachineError,
    init_handoff_json,
    validate_transition,
)

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


def _resolve_handoff_dir() -> Path:
    """Resolve the handoff directory from workflow_methods.json doc_artifact config."""
    methods_path = _SCRIPT_DIR / "workflow_methods.json"
    try:
        if methods_path.exists():
            methods = json.loads(methods_path.read_text(encoding="utf-8"))
            doc_artifact = methods.get("doc_artifact", {})
            paths = doc_artifact.get("paths", {})
            configured = paths.get("handoff_dir", ".handoff")
            return Path(configured)
    except (json.JSONDecodeError, OSError):
        pass
    return Path(".handoff")


CHANGES_ROOT = _resolve_changes_root()
HANDOFF_DIR = _resolve_handoff_dir()

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


def _ticket_tracker_label() -> str:
    methods = _load_methods()
    tracker = methods.get("ticket_tracker", {})
    if not isinstance(tracker, dict):
        return "GitHub Issues"

    backend = str(tracker.get("backend", "github")).strip().lower() or "github"
    repo = str(tracker.get("repo", "")).strip()

    if backend == "github":
        return f"GitHub Issues ({repo})" if repo else "GitHub Issues"
    if repo:
        return f"{backend} ({repo})"
    return backend


def _method_hint(phase: str, sub_state: str) -> str:
    methods = _load_methods()
    try:
        hint = methods[phase][sub_state]["hint"]
    except (KeyError, TypeError):
        return ""

    if phase == "wayfinding" and sub_state == "working_tickets":
        return f"{hint}（后端：{_ticket_tracker_label()}）"

    if "issue tracker" in hint:
        return hint.replace("issue tracker", f"issue tracker（{_ticket_tracker_label()}）")

    return hint


def _method_review_dims(phase: str, sub_state: str) -> list[str]:
    methods = _load_methods()
    try:
        return methods[phase][sub_state].get("review_dimensions", [])
    except (KeyError, TypeError):
        return []


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


def _load_handoff(change_id: str, root: Path = CHANGES_ROOT) -> dict | None:
    path = root / change_id / "handoff.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_handoff(change_id: str, data: dict, root: Path = CHANGES_ROOT) -> None:
    path = root / change_id / "handoff.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    Path(tmp).replace(path)


def _sub_state_index(phase: str, sub_state: str) -> int:
    seq = PHASE_SUB_STATES.get(phase, ())
    try:
        return seq.index(sub_state)
    except ValueError:
        return -1


def _build_path(phase: str, current_sub: str) -> list[dict]:
    """Build the full sub_state path with status markers, hints, review dims.

    Returns list[dict] rather than a dataclass to keep this CLI script lightweight.
    The canonical typed model lives in agent/workflow/models.py.
    """
    seq = PHASE_SUB_STATES.get(phase, ())
    current_idx = _sub_state_index(phase, current_sub)
    path = []
    for i, ss in enumerate(seq):
        if i < current_idx:
            status = "completed"
        elif i == current_idx:
            status = "current"
        else:
            status = "pending"

        is_gate = (ss == GATE_SUB_STATE)
        is_reviewing = ss.startswith("reviewing_")
        step: dict = {
            "sub_state": ss,
            "status": status,
            "hint": _method_hint(phase, ss),
            "is_gate": is_gate,
            "is_reviewing": is_reviewing,
            "trigger": "human_review" if is_gate else "auto",
        }
        if is_reviewing:
            step["review_dimensions"] = _method_review_dims(phase, ss) or None
        path.append(step)
    return path


def _next_action(phase: str, current_sub: str) -> str:
    seq = PHASE_SUB_STATES.get(phase, ())
    idx = _sub_state_index(phase, current_sub)
    if idx < 0:
        return "当前 sub_state 不合法，请检查 handoff.json"

    if current_sub == GATE_SUB_STATE:
        check_cmd = f"python3 scripts/check_phase_done.py --phase {phase}"
        return (
            f"[GATE] 当前在 GATE: {GATE_SUB_STATE}。"
            f"必须停止执行。运行 `{check_cmd}` 验证完成状态，"
            "然后等待人工审批（用户说 批准/通过/继续）。"
            "审批前不得推进。"
        )

    cur_hint = _method_hint(phase, current_sub)
    prefix = f"当前: {current_sub}"
    if cur_hint:
        prefix += f" — {cur_hint[:60]}..."

    next_idx = idx + 1
    if next_idx >= len(seq):
        return f"{prefix}\n当前阶段已完成，等待跨阶段推进。"

    next_ss = seq[next_idx]
    next_hint = _method_hint(phase, next_ss)
    if next_ss == GATE_SUB_STATE:
        return (
            f"{prefix}\n"
            f"下一步是 [GATE]: {GATE_SUB_STATE}。"
            f"完成当前任务后 advance to {GATE_SUB_STATE}，停止等待人工审批。"
        )
    return f"{prefix}\n下一步: {next_ss} — {next_hint}"


def _review_report_path(change_id: str, phase: str) -> Path:
    return HANDOFF_DIR / change_id / f"{phase}-review.md"


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

def cmd_discover(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        if args.format == "json":
            return _cmd_discover_json([], workflow_enabled=False)
        print("工作流已禁用。无活跃 change。")
        return 0
    changes = _all_change_ids()
    resume_audit = run_resume_audit(_PROJECT_ROOT)
    if args.format == "json":
        return _cmd_discover_json(changes, workflow_enabled=True, resume_audit=resume_audit)
    return _cmd_discover_text(changes, workflow_enabled=True, resume_audit=resume_audit)


def _cmd_discover_text(
    changes: list[str],
    workflow_enabled: bool = True,
    resume_audit=None,
) -> int:
    if not workflow_enabled:
        print("工作流已禁用。无活跃 change。")
        return 0
    if resume_audit is not None and resume_audit.baseline_present:
        if resume_audit.needs_reconciliation:
            print("⚠️ workflow resume audit 需要人工恢复确认：")
            for error in resume_audit.errors:
                print(f"- {error}")
        elif resume_audit.warnings:
            print("workflow resume audit 有警告：")
            for warning in resume_audit.warnings:
                print(f"- {warning}")
    if not changes:
        print("无活跃 change。")
        return 0

    print(f"{'Change':<50} {'Phase':<14} {'SubState':<22}")
    print("-" * 86)
    for cid in changes:
        data = _load_handoff(cid)
        if data is None:
            continue
        state = data.get("state", {})
        phase = state.get("phase", "?")
        sub = state.get("sub_state", "?") or "-"
        marker = " [GATE]" if sub == GATE_SUB_STATE else ""
        print(f"{cid:<50} {phase:<14} {sub:<22}{marker}")
    return 0


def _cmd_discover_json(
    changes: list[str],
    workflow_enabled: bool = True,
    resume_audit=None,
) -> int:
    result: dict = {
        "workflow_enabled": workflow_enabled,
        "active_count": len(changes),
        "active_changes": [],
        "resume_audit": resume_audit.to_dict() if resume_audit is not None else None,
        "instruction": (
            "工作流已禁用，忽略现有 handoff 状态。"
            if not workflow_enabled
            else (
                "如果有 change 处于 ready_for_review (GATE)，必须停止执行并等待人工审批。"
                "非 GATE 状态下: building phase 必须先创建 worktree。"
                "每个 sub_state 完成后自动 advance 到下一步，直到到达 GATE。"
                "reviewing_* 子状态: spawn 独立子 Agent（零记忆）审阅本阶段产出，三轮封顶。"
            )
        ),
    }

    if not workflow_enabled:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    for cid in changes:
        data = _load_handoff(cid)
        if data is None:
            continue
        state = data.get("state", {})
        phase = state.get("phase", "?")
        sub = state.get("sub_state", "") or ""
        role = PHASE_TO_ROLE.get(phase, "unknown")
        worktree = phase in WORKTREE_REQUIRED_PHASES
        is_gate = sub == GATE_SUB_STATE
        is_reviewing = sub.startswith("reviewing_")

        change_info: dict = {
            "change_id": cid,
            "state": {
                "phase": phase,
                "sub_state": sub,
                "role": role,
                "worktree_required": worktree,
                "at_gate": is_gate,
                "is_reviewing": is_reviewing,
            },
            "path": _build_path(phase, sub),
            "next_action": _next_action(phase, sub),
        }

        if is_reviewing:
            change_info["review"] = {
                "protocol": "spawn 独立子 Agent（零记忆），三轮封顶，产出到 .handoff/<change-id>/",
                "dimensions": _method_review_dims(phase, sub) or [],
                "report_path": str(_review_report_path(cid, phase)),
                "max_rounds": 3,
            }

        if is_gate:
            check_cmd = f"python3 scripts/check_phase_done.py --phase {phase} --change {cid}"
            change_info["gate_check"] = {
                "command": check_cmd,
                "approve_command": f"python3 scripts/workflow_state.py flow approve --change {cid} --phase {phase}",
            }

        if phase == "wayfinding" and sub == "map_cleared":
            change_info["wayfinding_next"] = {
                "action": "path_cleared",
                "hint": "地图已清除。审批通过后可用 spawn 命令创建子 change：",
                "spawn_command": "python3 scripts/workflow_state.py spawn --from <wayfinding-id> --changes <id1,id2,...>",
            }

        result["active_changes"].append(change_info)

    # Include on_ramps, cross_cutting, review_protocol as reference context
    methods = _load_methods()
    if methods:
        result["on_ramps"] = methods.get("on_ramps", {})
        result["cross_cutting"] = methods.get("cross_cutting", {})
        result["review_protocol"] = methods.get("review_protocol", {})

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


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


def cmd_current(args: argparse.Namespace) -> int:
    data = _load_handoff(args.change)
    if data is None:
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1
    print(json.dumps(data["state"], indent=2, ensure_ascii=False))
    return 0


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


def cmd_flow_block(args: argparse.Namespace) -> int:
    change_dir = _flow_require_change(args.change)
    if change_dir is None:
        return 1
    if args.awaiting not in AWAITING_SUB_STATES:
        print(f"错误：--awaiting 必须是 {', '.join(AWAITING_SUB_STATES)}", file=sys.stderr)
        return 1
    try:
        projection = project_workflow_state(change_dir)
    except StateMachineError as exc:
        print(f"错误：事件不完整，检查 seq（{exc}）", file=sys.stderr)
        return 1
    current = projection["state"]
    if current.get("phase") == "blocked":
        print(f"错误：change 已处于 blocked/awaiting 态（{current['phase']}.{current.get('sub_state')}）", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": current,
        "to": {"phase": "blocked", "sub_state": args.awaiting},
        "trigger": "auto",
        "actor_type": "human",
        "actor_id": "flow",
        "timestamp": now,
    }
    blocker = {"blocked_from": current, "reason": args.awaiting, "blocked_at": now}
    try:
        validate_transition(
            StateSnapshot(phase=current["phase"], sub_state=current.get("sub_state")),
            StateSnapshot(phase="blocked", sub_state=args.awaiting),
            "auto",
        )
        append_blocked_event(change_dir, args.change, transition, blocker)
    except StateMachineError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    _flow_refresh_after_event(change_dir)
    print(f"已进入 awaiting: {args.change} → blocked.{args.awaiting}")
    return 0


def cmd_flow_confirm(args: argparse.Namespace) -> int:
    change_dir = _flow_require_change(args.change)
    if change_dir is None:
        return 1
    try:
        projection = project_workflow_state(change_dir)
    except StateMachineError as exc:
        print(f"错误：事件不完整，检查 seq（{exc}）", file=sys.stderr)
        return 1
    current = projection["state"]
    if not is_awaiting_state(current):
        print(
            f"错误：change '{args.change}' 不在 awaiting 态（当前 {current['phase']}.{current.get('sub_state')}）",
            file=sys.stderr,
        )
        return 1
    awaiting = current["sub_state"]
    recovery = _awaiting_recovery_target(change_dir, awaiting, current)
    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": current,
        "to": recovery,
        "trigger": "auto",
        "actor_type": "human",
        "actor_id": "flow",
        "timestamp": now,
    }
    blocker = {"blocked_from": recovery, "reason": awaiting, "blocked_at": now}
    try:
        append_unblocked_event(change_dir, args.change, transition, 0, blocker)
    except StateMachineError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    _flow_refresh_after_event(change_dir)
    print(f"已确认解除 awaiting: {args.change} → {recovery['phase']}.{recovery.get('sub_state')}")
    return 0


def cmd_flow_approve(args: argparse.Namespace) -> int:
    change_dir = _flow_require_change(args.change)
    if change_dir is None:
        return 1
    try:
        projection = project_workflow_state(change_dir)
    except StateMachineError as exc:
        print(f"错误：事件不完整，检查 seq（{exc}）", file=sys.stderr)
        return 1
    current = projection["state"]
    phase = args.phase
    if current.get("phase") != phase or current.get("sub_state") != GATE_SUB_STATE:
        print(
            f"错误：期望 gate {phase}.{GATE_SUB_STATE}，实际 {current.get('phase')}.{current.get('sub_state')}",
            file=sys.stderr,
        )
        return 1
    check = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_DIR / "check_phase_done.py"),
            "--phase",
            phase,
            "--change",
            args.change,
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        output = (check.stdout + check.stderr).strip()
        print(f"错误：phase 机械检查未通过，拒绝批准\n{output}", file=sys.stderr)
        return 1

    targets = CROSS_PHASE_FORWARD.get((phase, GATE_SUB_STATE), [])
    if not targets:
        print(f"错误：phase '{phase}' 无跨阶段推进目标", file=sys.stderr)
        return 1
    target_phase, target_sub = targets[0]
    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": current,
        "to": {"phase": target_phase, "sub_state": target_sub},
        "trigger": "human_review",
        "actor_type": "human",
        "actor_id": args.who or "human",
        "timestamp": now,
    }
    try:
        validate_transition(
            StateSnapshot(phase=phase, sub_state=GATE_SUB_STATE),
            StateSnapshot(phase=target_phase, sub_state=target_sub),
            "human_review",
        )
        append_transition_event(change_dir, args.change, transition)
    except StateMachineError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    _flow_refresh_after_event(change_dir)
    print(f"已批准并推进: {args.change} / {phase} → {target_phase}.{target_sub}")
    return 0


def cmd_flow_advance(args: argparse.Namespace) -> int:
    change_dir = _flow_require_change(args.change)
    if change_dir is None:
        return 1
    try:
        projection = project_workflow_state(change_dir)
    except StateMachineError as exc:
        print(f"错误：事件不完整，检查 seq（{exc}）", file=sys.stderr)
        return 1
    current = projection["state"]
    if current.get("phase") == "blocked":
        print("错误：blocked/awaiting 态不能 advance", file=sys.stderr)
        return 1
    phase = current["phase"]
    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": current,
        "to": {"phase": phase, "sub_state": args.to},
        "trigger": "auto",
        "actor_type": "agent",
        "actor_id": "flow",
        "timestamp": now,
    }
    try:
        validate_transition(
            StateSnapshot(phase=phase, sub_state=current.get("sub_state")),
            StateSnapshot(phase=phase, sub_state=args.to),
            "auto",
        )
        append_transition_event(change_dir, args.change, transition)
    except StateMachineError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    _flow_refresh_after_event(change_dir)
    print(f"已推进: {args.change} → {phase}.{args.to}")
    return 0


# ── flow 命令组 helpers ───────────────────────────────────────────────

_AWAITING_RECOVERY_DEFAULTS: dict[str, dict] = {
    "awaiting_proposal_confirmation": {"phase": "planning", "sub_state": "writing_design"},
    "awaiting_human_review": {"phase": "planning", "sub_state": "reviewing_artifacts"},
    "awaiting_user_confirmation": {"phase": "planning", "sub_state": "writing_design"},
}


def _flow_require_change(change_id: str) -> Path | None:
    change_dir = CHANGES_ROOT / change_id
    if not change_dir.exists():
        print(f"错误：change '{change_id}' 不存在", file=sys.stderr)
        return None
    if not (change_dir / "workflow-events.jsonl").exists():
        print(f"错误：change '{change_id}' 没有 workflow-events.jsonl", file=sys.stderr)
        return None
    return change_dir


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
        # 自愈重建：写新鲜投影 + 同步映射 handoff.json
        _refresh_workflow_state(change_dir, projection)
    return {**projection, "stale": stale}, None


def _awaiting_recovery_target(change_dir: Path, awaiting: str, current_state: dict) -> dict:
    """confirm 恢复目标：优先最后 blocked_entered 的 transition.from，否则按 awaiting 类型默认。"""
    try:
        events = _read_events(event_log_path(change_dir))
    except StateMachineError:
        events = []
    for event in reversed(events):
        if event.get("event_type") == "blocked_entered":
            trans = event.get("transition", {})
            if trans.get("from"):
                return trans["from"]
    return _AWAITING_RECOVERY_DEFAULTS.get(awaiting, DEFAULT_SEED_STATE)


def _flow_refresh_after_event(change_dir: Path) -> None:
    """写事件后刷新投影：gen-1 同步 handoff.json，gen-2 写 workflow-state.json + 映射 handoff。"""
    if _flow_is_gen1(change_dir):
        try:
            _save_handoff(change_dir.name, replay_handoff_projection(change_dir))
        except StateMachineError as exc:
            print(f"错误：handoff.json 同步失败：{exc}", file=sys.stderr)
    else:
        _refresh_workflow_state(change_dir)


def _refresh_workflow_state(change_dir: Path, projection: dict | None = None) -> None:
    """写 workflow-state.json + 同步映射 handoff.json（代码层修正 5/6）。"""
    if projection is None:
        try:
            projection = project_workflow_state(change_dir)
        except StateMachineError:
            return
    _atomic_write_json(workflow_state_path(change_dir), projection)
    handoff = {
        "schema_version": "1.0",
        "change_id": projection["change_id"],
        "state": projection["state"],
        "transitions": [],
    }
    _atomic_write_json(change_dir / "handoff.json", handoff)


def cmd_spawn(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        print("错误：workflow 已在 workflow_methods.json 中禁用，spawn 不可用", file=sys.stderr)
        return 1
    parent_data = _load_handoff(args.from_change)
    if parent_data is None:
        print(f"错误: 父 change '{args.from_change}' 没有 handoff.json", file=sys.stderr)
        return 1

    parent_phase = parent_data["state"]["phase"]
    if parent_phase != "wayfinding":
        print(f"错误: 父 change '{args.from_change}' 不在 wayfinding 阶段 (实际: {parent_phase})", file=sys.stderr)
        return 1
    parent_sub_state = parent_data["state"].get("sub_state")
    if parent_sub_state != GATE_SUB_STATE:
        print(
            f"错误: 父 change '{args.from_change}' 必须位于 wayfinding.{GATE_SUB_STATE} 才能 spawn "
            f"(实际: wayfinding.{parent_sub_state})",
            file=sys.stderr,
        )
        return 1

    child_ids = [c.strip() for c in args.changes.split(",") if c.strip()]
    if not child_ids:
        print("错误: --changes 必须提供至少一个子 change ID (逗号分隔)", file=sys.stderr)
        return 1

    created = []
    for cid in child_ids:
        child_dir = CHANGES_ROOT / cid
        if child_dir.exists():
            print(f"跳过: '{cid}' 目录已存在")
            continue
        child_dir.mkdir(parents=True, exist_ok=True)
        handoff = init_handoff_json(cid)
        handoff["parent_wayfinding"] = args.from_change
        _save_handoff(cid, handoff)
        write_init_event(child_dir, handoff)
        created.append(cid)
        print(f"已创建: {cid}")

    if created:
        children_list = list(parent_data.get("wayfinding_children", []))
        children_list.extend(created)
        append_wayfinding_children_event(
            CHANGES_ROOT / args.from_change,
            args.from_change,
            children_list,
        )
        parent_data = replay_handoff_projection(CHANGES_ROOT / args.from_change)
        _save_handoff(args.from_change, parent_data)

    print(f"\n共创建 {len(created)} 个子 change，父 {args.from_change} 记录关联。")
    return 0


def cmd_artifact_event(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        print(
            "错误：workflow 已在 workflow_methods.json 中禁用，artifact-event 不可用",
            file=sys.stderr,
        )
        return 1
    change_dir = CHANGES_ROOT / args.change
    if not (change_dir / "handoff.json").exists():
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1

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

    print(f"已记录 artifact 事件: {args.event_type} ({args.artifact_path})")
    return 0


def cmd_review_manifest(args: argparse.Namespace) -> int:
    if not is_workflow_enabled(_PROJECT_ROOT):
        print(
            "错误：workflow 已在 workflow_methods.json 中禁用，review-manifest 不可用",
            file=sys.stderr,
        )
        return 1
    change_dir = CHANGES_ROOT / args.change
    if not (change_dir / "handoff.json").exists():
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1

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
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"已写入 review manifest: {path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    data = _load_handoff(args.change)
    if data is None:
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1

    errors: list[str] = []
    required = ["schema_version", "change_id", "state", "transitions"]
    for key in required:
        if key not in data:
            errors.append(f"缺少必填字段: {key}")

    state = data.get("state", {})
    valid_phases = {"wayfinding", "planning", "building", "closing", "blocked", "done"}
    if "phase" not in state:
        errors.append("state 缺少 phase")
    else:
        if state["phase"] not in valid_phases:
            errors.append(f"无效 phase: {state['phase']}")
    if "sub_state" not in state:
        errors.append("state 缺少 sub_state")
    if not isinstance(data.get("transitions", None), list):
        errors.append("transitions 必须是数组")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print(f"handoff.json 结构有效 (phase={state.get('phase')}, sub_state={state.get('sub_state')})")
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

    p = sub.add_parser("discover", help="列出所有活跃 change 及当前 phase/sub_state")
    p.add_argument("--format", choices=["text", "json"], default="text",
                   help="输出格式: text (默认表格) 或 json (Agent 可消费的丰富上下文)")
    p.set_defaults(func=cmd_discover)

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

    p = sub.add_parser("current", help="输出指定 change 的当前状态 (JSON)")
    p.add_argument("--change", required=True)
    p.set_defaults(func=cmd_current)

    p = sub.add_parser("flow", help="flow 命令组：投影查询、等待态确认与阶段推进")
    flow_sub = p.add_subparsers(dest="flow_command", required=True)

    p_status = flow_sub.add_parser("status", help="输出投影状态（唯一/默认 JSON）")
    p_status.add_argument("--change", help="指定 change id")
    p_status.add_argument("--all", action="store_true", help="所有 change")
    p_status.set_defaults(func=cmd_flow_status)

    p_block = flow_sub.add_parser("block", help="进入 awaiting 态（写 blocked_entered）")
    p_block.add_argument("--change", required=True)
    p_block.add_argument("--awaiting", required=True, choices=list(AWAITING_SUB_STATES))
    p_block.set_defaults(func=cmd_flow_block)

    p_confirm = flow_sub.add_parser("confirm", help="确认解除 awaiting（写 blocked_resolved）")
    p_confirm.add_argument("--change", required=True)
    p_confirm.set_defaults(func=cmd_flow_confirm)

    p_approve = flow_sub.add_parser("approve", help="阶段通过（跨阶段推进，写 transition_applied）")
    p_approve.add_argument("--change", required=True)
    p_approve.add_argument("--phase", required=True)
    p_approve.add_argument("--who")
    p_approve.set_defaults(func=cmd_flow_approve)

    p_advance = flow_sub.add_parser("advance", help="sub_state 推进（写 transition_applied）")
    p_advance.add_argument("--change", required=True)
    p_advance.add_argument("--to", required=True, help="目标 sub_state")
    p_advance.set_defaults(func=cmd_flow_advance)

    p = sub.add_parser("validate", help="校验 handoff.json 结构")
    p.add_argument("--change", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("spawn", help="从 wayfinding change 创建子 change")
    p.add_argument("--from", dest="from_change", required=True, help="父 wayfinding change ID")
    p.add_argument("--changes", required=True, help="子 change ID 列表 (逗号分隔)")
    p.set_defaults(func=cmd_spawn)

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

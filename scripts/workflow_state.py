#!/usr/bin/env python3
"""Workflow state management CLI — discover, inspect, advance, approve, spawn.

Usage:
    uv run python scripts/workflow_state.py discover
    uv run python scripts/workflow_state.py discover --format json
    uv run python scripts/workflow_state.py current --change <id>
    uv run python scripts/workflow_state.py advance --change <id> --to <sub_state>
    uv run python scripts/workflow_state.py approve --change <id> --phase <phase>
    uv run python scripts/workflow_state.py validate --change <id>
    uv run python scripts/workflow_state.py spawn --from <wayfinding-id> --changes <id1,id2,...>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__ != "__main__":
    raise ImportError("workflow_state.py is a CLI script, not a library module")

_SCRIPT_DIR = Path(__file__).resolve().parent
CHANGES_ROOT = Path("openspec/changes")
HANDOFF_DIR = Path(".handoff")
METHODS_PATH = _SCRIPT_DIR / "workflow_methods.json"

# ── Phase / sub-state definitions ──

PHASE_ORDER = ("wayfinding", "planning", "building", "closing")

PHASE_SUB_STATES: dict[str, tuple[str, ...]] = {
    "wayfinding": (
        "charting_map", "working_tickets", "map_cleared",
        "reviewing_map", "ready_for_review",
    ),
    "planning": (
        "exploring", "writing_design", "writing_spec", "writing_tickets",
        "reviewing_artifacts", "ready_for_review",
    ),
    "building": (
        "writing_tests", "test_failing", "implementing",
        "all_tests_passing", "smoke_validating",
        "reviewing_impl", "ready_for_review",
    ),
    "closing": (
        "syncing_specs", "archiving", "updating_backlog", "validating",
        "pr_ready", "reviewing_archive", "ready_for_review",
    ),
}

PHASE_TO_ROLE: dict[str, str] = {
    "wayfinding": "wayfinder",
    "planning": "planner",
    "building": "builder",
    "closing": "closer",
}

WORKTREE_REQUIRED_PHASES = {"building"}

GATE_SUB_STATE = "ready_for_review"

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


def _method_hint(phase: str, sub_state: str) -> str:
    """Look up hint from workflow_methods.json; fallback to built-in."""
    methods = _load_methods()
    try:
        return methods[phase][sub_state]["hint"]
    except (KeyError, TypeError):
        pass
    return ""


def _method_review_dims(phase: str, sub_state: str) -> list[str]:
    """Return review_dimensions for a reviewing_* sub-state."""
    methods = _load_methods()
    try:
        return methods[phase][sub_state].get("review_dimensions", [])
    except (KeyError, TypeError):
        return []


def _reviewing_sub_state(phase: str) -> str | None:
    """Return the reviewing_* sub-state name for a phase, if it exists."""
    seq = PHASE_SUB_STATES.get(phase, ())
    for ss in seq:
        if ss.startswith("reviewing_"):
            return ss
    return None


# ── Helpers ──

def _all_change_ids(root: Path = CHANGES_ROOT) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and d.name != "archive" and (d / "handoff.json").exists()
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
    """Build the full sub_state path with status markers, hints, review dims."""
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
            f"🔴 当前在 GATE: {GATE_SUB_STATE}。"
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
            f"下一步是 🔴 GATE: {GATE_SUB_STATE}。"
            f"完成当前任务后 advance to {GATE_SUB_STATE}，停止等待人工审批。"
        )
    return f"{prefix}\n下一步: {next_ss} — {next_hint}"


def _review_report_path(change_id: str, phase: str) -> Path:
    """Path to the review report for this phase."""
    return HANDOFF_DIR / change_id / f"{phase}-review.md"


# ── Commands ──

def cmd_discover(args: argparse.Namespace) -> int:
    changes = _all_change_ids()
    if args.format == "json":
        return _cmd_discover_json(changes)
    return _cmd_discover_text(changes)


def _cmd_discover_text(changes: list[str]) -> int:
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
        marker = " ← GATE" if sub == GATE_SUB_STATE else ""
        print(f"{cid:<50} {phase:<14} {sub:<22}{marker}")
    return 0


def _cmd_discover_json(changes: list[str]) -> int:
    result: dict = {
        "active_count": len(changes),
        "active_changes": [],
        "instruction": (
            "如果有 change 处于 ready_for_review (GATE)，必须停止执行并等待人工审批。"
            "非 GATE 状态下: building phase 必须先创建 worktree。"
            "每个 sub_state 完成后自动 advance 到下一步，直到到达 GATE。"
            "reviewing_* 子状态: spawn 独立子 Agent（零记忆）审阅本阶段产出，三轮封顶。"
        ),
    }

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
                "approve_command": f"python3 scripts/workflow_state.py approve --change {cid} --phase {phase}",
            }

        # wayfinding extra: hint about spawning
        if phase == "wayfinding" and sub == "map_cleared":
            change_info["wayfinding_next"] = {
                "action": "path_cleared",
                "hint": "地图已清除。审批通过后可用 spawn 命令创建子 change：",
                "spawn_command": "python3 scripts/workflow_state.py spawn --from <wayfinding-id> --changes <id1,id2,...>",
            }

        result["active_changes"].append(change_info)

    # add on_ramps and cross_cutting from workflow_methods.json
    methods = _load_methods()
    if methods:
        result["on_ramps"] = methods.get("on_ramps", {})
        result["cross_cutting"] = methods.get("cross_cutting", {})
        result["review_protocol"] = methods.get("review_protocol", {})

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    data = _load_handoff(args.change)
    if data is None:
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1
    print(json.dumps(data["state"], indent=2, ensure_ascii=False))
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    data = _load_handoff(args.change)
    if data is None:
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1

    from_phase = data["state"]["phase"]
    from_sub = data["state"]["sub_state"]
    to_sub = args.to

    if to_sub == GATE_SUB_STATE:
        trigger = "handoff"
    elif from_sub == GATE_SUB_STATE:
        trigger = "human_review"
    else:
        trigger = "auto"

    # Phase transition: moving to a new phase
    if args.to_phase:
        data["state"]["phase"] = args.to_phase
        data["state"]["sub_state"] = to_sub
        trigger = "human_review"

    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": {"phase": from_phase, "sub_state": from_sub},
        "to": {"phase": data["state"]["phase"], "sub_state": to_sub},
        "trigger": trigger,
        "actor_type": "agent",
        "actor_id": "workflow_state.py",
        "timestamp": now,
    }
    data["state"]["sub_state"] = to_sub
    data["transitions"].append(transition)

    if to_sub == GATE_SUB_STATE:
        data["last_gate"] = {"phase": data["state"]["phase"], "sub_state": GATE_SUB_STATE}

    _save_handoff(args.change, data)
    phase_label = data["state"]["phase"]
    print(f"已推进: {from_phase}.{from_sub} → {phase_label}.{to_sub}  (trigger: {trigger})")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    change_dir = HANDOFF_DIR / args.change
    change_dir.mkdir(parents=True, exist_ok=True)

    approvals_path = change_dir / "gate-approvals.json"
    existing: list[dict] = []
    if approvals_path.exists():
        existing = json.loads(approvals_path.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "phase": args.phase,
        "approved_at": now,
        "approved_by": args.who or "human",
        "notes": args.notes or "",
    }
    existing.append(entry)

    with open(str(approvals_path) + ".tmp", "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    Path(str(approvals_path) + ".tmp").replace(approvals_path)

    print(f"已记录批准: {args.change} / {args.phase}")
    return 0


def cmd_spawn(args: argparse.Namespace) -> int:
    """Spawn child changes from a wayfinding map."""
    parent_data = _load_handoff(args.from_change)
    if parent_data is None:
        print(f"错误: 父 change '{args.from_change}' 没有 handoff.json", file=sys.stderr)
        return 1

    parent_phase = parent_data["state"]["phase"]
    if parent_phase != "wayfinding":
        print(f"错误: 父 change '{args.from_change}' 不在 wayfinding 阶段 (实际: {parent_phase})", file=sys.stderr)
        return 1

    child_ids = [c.strip() for c in args.changes.split(",") if c.strip()]
    if not child_ids:
        print("错误: --changes 必须提供至少一个子 change ID (逗号分隔)", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    created = []
    for cid in child_ids:
        child_dir = CHANGES_ROOT / cid
        if child_dir.exists():
            print(f"跳过: '{cid}' 目录已存在")
            continue
        child_dir.mkdir(parents=True, exist_ok=True)
        handoff = {
            "schema_version": "1.0",
            "change_id": cid,
            "parent_wayfinding": args.from_change,
            "state": {"phase": "planning", "sub_state": "exploring"},
            "transitions": [{
                "from": {"phase": None, "sub_state": None},
                "to": {"phase": "planning", "sub_state": "exploring"},
                "trigger": "auto",
                "actor_type": "agent",
                "actor_id": "workflow_state.py",
                "timestamp": now,
            }],
        }
        hf_path = child_dir / "handoff.json"
        with open(str(hf_path) + ".tmp", "w", encoding="utf-8") as f:
            json.dump(handoff, f, indent=2, ensure_ascii=False)
        Path(str(hf_path) + ".tmp").replace(hf_path)
        created.append(cid)
        print(f"已创建: {cid} ({hf_path})")

    # Record relationship in parent
    children_list = parent_data.get("wayfinding_children", [])
    children_list.extend(created)
    parent_data["wayfinding_children"] = children_list
    _save_handoff(args.from_change, parent_data)

    print(f"\n共创建 {len(created)} 个子 change，父 {args.from_change} 记录关联。")
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

    p = sub.add_parser("current", help="输出指定 change 的当前状态 (JSON)")
    p.add_argument("--change", required=True)
    p.set_defaults(func=cmd_current)

    p = sub.add_parser("advance", help="推进 change 的 sub_state")
    p.add_argument("--change", required=True)
    p.add_argument("--to", required=True, help="目标 sub_state")
    p.add_argument("--to-phase", help="跨阶段推进时的目标 phase（只用于 Gate 审批后切换阶段）")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("approve", help="记录人工 gate 批准")
    p.add_argument("--change", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--who")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("validate", help="校验 handoff.json 结构")
    p.add_argument("--change", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("spawn", help="从 wayfinding change 创建子 change")
    p.add_argument("--from", dest="from_change", required=True, help="父 wayfinding change ID")
    p.add_argument("--changes", required=True, help="子 change ID 列表 (逗号分隔)")
    p.set_defaults(func=cmd_spawn)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

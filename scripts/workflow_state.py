#!/usr/bin/env python3
"""Workflow state management CLI — discover, inspect, advance, and approve.

Usage:
    uv run python scripts/workflow_state.py discover
    uv run python scripts/workflow_state.py discover --format json
    uv run python scripts/workflow_state.py current --change <id>
    uv run python scripts/workflow_state.py advance --change <id> --to <sub_state>
    uv run python scripts/workflow_state.py approve --change <id> --phase <phase>
    uv run python scripts/workflow_state.py validate --change <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Guard against accidental execution as a library call
if __name__ != "__main__":
    raise ImportError("workflow_state.py is a CLI script, not a library module")

CHANGES_ROOT = Path("openspec/changes")
HANDOFF_DIR = Path(".handoff")

PHASE_ORDER = ("planning", "reviewing", "building", "code-review", "closing")

PHASE_SUB_STATES: dict[str, tuple[str, ...]] = {
    "planning": (
        "exploring", "writing_proposal", "writing_design", "grilling_design",
        "writing_specs", "writing_tasks", "ready_for_review",
    ),
    "reviewing": (
        "reading_docs", "reviewing_design", "ready_for_review",
    ),
    "building": (
        "writing_tests", "test_failing", "implementing",
        "all_tests_passing", "smoke_validating", "ready_for_review",
    ),
    "code-review": (
        "reading_diff", "analyzing_tests", "reviewing_code",
        "requesting_changes", "ready_for_review",
    ),
    "closing": (
        "syncing_specs", "archiving", "updating_backlog", "validating",
        "pr_ready", "ready_for_review",
    ),
}

PHASE_TO_ROLE: dict[str, str] = {
    "planning": "planner",
    "reviewing": "reviewer",
    "building": "builder",
    "code-review": "code-reviewer",
    "closing": "closer",
}

WORKTREE_REQUIRED_PHASES = {"building"}

GATE_SUB_STATE = "ready_for_review"

# --- Action hints for each sub_state ---
SUB_STATE_HINTS: dict[str, str] = {
    "exploring": "探索代码库和现有实现，理解相关模块的当前状态",
    "writing_proposal": "编写 proposal.md，明确需求边界和验收标准",
    "writing_design": "编写 design.md，记录架构决策和备选方案（参考 ADR 模板）",
    "grilling_design": "运行 /grill-with-docs 追问确认设计细节、依赖、风险和测试策略",
    "writing_specs": "编写 spec delta，更新 openspec/specs/",
    "writing_tasks": "编写 tasks.md，将实现拆分为独立可验证的任务",
    "ready_for_review": "🔴 GATE — 停止执行，运行 check_phase_done.py，等待人工审批",
    "reading_docs": "阅读相关文档、spec 和已有代码",
    "reviewing_design": "审阅 design.md，评估方案合理性和风险",
    "writing_tests": "按 TDD 先写测试用例，确保覆盖核心路径和边界条件",
    "test_failing": "运行测试确认红灯（代码未实现时测试应失败）",
    "implementing": "实现功能代码，保持小步提交",
    "all_tests_passing": "运行全量 pytest 确认所有测试通过、无回归",
    "smoke_validating": "运行冒烟测试（启动应用验证核心功能可用）",
    "reading_diff": "读取 git diff，理解本次变更的完整范围",
    "analyzing_tests": "分析测试覆盖是否充分，是否有遗漏的边界条件",
    "reviewing_code": "多维度审阅代码（正确性/安全性/可维护性/性能）",
    "requesting_changes": "整理审阅发现的问题，生成修复建议",
    "syncing_specs": "将 delta spec 合并到 openspec/specs/ 主规格",
    "archiving": "归档 change 到 openspec/changes/archive/YYYY-MM-DD-<id>/",
    "updating_backlog": "从 docs/openspec-change-backlog.md 移除已完成 change",
    "validating": "运行 openspec validate + artifact checker 确认归档正确",
    "pr_ready": "创建 PR，填写描述和验证结果",
}


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
    """Return the index of sub_state within the phase sequence."""
    seq = PHASE_SUB_STATES.get(phase, ())
    try:
        return seq.index(sub_state)
    except ValueError:
        return -1


def _build_path(phase: str, current_sub: str) -> list[dict]:
    """Build the full sub_state path with status markers and hints."""
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
        step: dict = {
            "sub_state": ss,
            "status": status,
            "hint": SUB_STATE_HINTS.get(ss, ""),
            "is_gate": is_gate,
            "trigger": "human_review" if is_gate else "auto",
        }
        path.append(step)
    return path


def _next_action(phase: str, current_sub: str) -> str:
    """Generate a human-readable next action hint."""
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

    next_idx = idx + 1
    if next_idx >= len(seq):
        return "当前阶段已完成，等待跨阶段推进。"

    next_ss = seq[next_idx]
    next_hint = SUB_STATE_HINTS.get(next_ss, "")
    if next_ss == GATE_SUB_STATE:
        return (
            f"当前: {current_sub}。下一步是 🔴 GATE: {GATE_SUB_STATE}。"
            f"完成当前任务后 advance to {GATE_SUB_STATE}，"
            f"然后停止等待人工审批。"
        )
    return f"下一步: {next_ss} — {next_hint}"


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
    """Rich JSON output for agent consumption — includes full path, gate positions, hints."""
    result: dict = {
        "active_count": len(changes),
        "active_changes": [],
        "instruction": (
            "如果有 change 处于 ready_for_review (GATE)，必须停止执行并等待人工审批。"
            "非 GATE 状态下: building phase 必须先创建 worktree。"
            "每个 sub_state 完成后自动 advance 到下一步，直到到达 GATE。"
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

        change_info: dict = {
            "change_id": cid,
            "state": {
                "phase": phase,
                "sub_state": sub,
                "role": role,
                "worktree_required": worktree,
                "at_gate": is_gate,
            },
            "path": _build_path(phase, sub),
            "next_action": _next_action(phase, sub),
        }
        if is_gate:
            check_cmd = f"python3 scripts/check_phase_done.py --phase {phase} --change {cid}"
            change_info["gate_check"] = {
                "command": check_cmd,
                "approve_command": f"python3 scripts/workflow_state.py approve --change {cid} --phase {phase}",
            }

        result["active_changes"].append(change_info)

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

    # Determine trigger type
    if to_sub == GATE_SUB_STATE:
        trigger = "handoff"
    elif from_sub == GATE_SUB_STATE and from_phase in data.get("routing", {}):
        trigger = "human_review"
    else:
        trigger = "auto"

    now = datetime.now(timezone.utc).isoformat()
    transition = {
        "from": {"phase": from_phase, "sub_state": from_sub},
        "to": {"phase": from_phase, "sub_state": to_sub},
        "trigger": trigger,
        "actor_type": "agent",
        "actor_id": "workflow_state.py",
        "timestamp": now,
    }

    data["state"]["sub_state"] = to_sub
    data["transitions"].append(transition)

    if to_sub == GATE_SUB_STATE:
        data["last_gate"] = {"phase": from_phase, "sub_state": GATE_SUB_STATE}

    _save_handoff(args.change, data)
    print(f"已推进: {from_phase}.{from_sub} → {from_phase}.{to_sub}  (trigger: {trigger})")
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
    if "phase" not in state:
        errors.append("state 缺少 phase")
    else:
        valid_phases = {"planning", "reviewing", "building", "code-review", "closing", "blocked", "done"}
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

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Workflow state management CLI — discover, inspect, advance, and approve.

Usage:
    uv run python scripts/workflow_state.py discover
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


def cmd_discover(args: argparse.Namespace) -> int:
    changes = _all_change_ids()
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
        marker = " ← GATE" if sub == "ready_for_review" else ""
        print(f"{cid:<50} {phase:<14} {sub:<22}{marker}")
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
    if to_sub == "ready_for_review":
        trigger = "handoff"
    elif from_sub == "ready_for_review" and from_phase in data.get("routing", {}):
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

    if to_sub == "ready_for_review":
        data["last_gate"] = {"phase": from_phase, "sub_state": "ready_for_review"}

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

#!/usr/bin/env python3
"""Workflow state compatibility CLI — discover and inspect legacy handoff.json.

Usage:
    uv run python scripts/workflow_state.py discover
    uv run python scripts/workflow_state.py current --change <id>
    uv run python scripts/workflow_state.py validate --change <id>

State transitions are owned by `asterwynd workflow ...`; this legacy script is
kept as a read-only compatibility view during migration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Guard against accidental execution as a library call
if __name__ != "__main__":
    raise ImportError("workflow_state.py is a CLI script, not a library module")

CHANGES_ROOT = Path("openspec/changes")


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
    from workflow_control import import_handoff_read_only

    snapshot = import_handoff_read_only(path)
    return {
        "change_id": snapshot.change_id,
        "state": {"phase": snapshot.phase, "sub_state": snapshot.sub_state},
        "source": snapshot.source,
    }


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
    print(
        "错误：workflow_state.py 已降级为只读兼容入口；请使用 `asterwynd workflow report` 或正式 gate 命令推进状态。",
        file=sys.stderr,
    )
    return 2


def cmd_approve(args: argparse.Namespace) -> int:
    print(
        "错误：workflow_state.py 不再记录人工批准；请使用 `asterwynd workflow gate approve`。",
        file=sys.stderr,
    )
    return 2


def cmd_validate(args: argparse.Namespace) -> int:
    data = _load_handoff(args.change)
    if data is None:
        print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
        return 1

    errors: list[str] = []

    required = ["change_id", "state"]
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

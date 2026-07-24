#!/usr/bin/env python3
"""PreToolUse hook: 文件系统门禁 — 阻止 Agent 在不符合条件时修改代码。

用法 (Claude Code settings.json):
  "PreToolUse": [{"matcher": "Write|Edit|Bash", "command": "python3 scripts/workflow_guard.py"}]

拦截:
  - Write / Edit 工具
  - Bash 命令中包含写操作模式的 (>, >>, tee, sed -i, cp, mv, mkdir,
    git commit/add/push, touch, dd of=, python -c/exec with write, etc)

逻辑:
  1. Write/Edit → 直接检查门禁
  2. Bash → 分析命令是否含写操作 → 是则检查门禁，否则放行
  3. 扫描活跃 change，检查 phase.required_files
  4. 缺失 → exit 2 (阻止) + stderr
  5. building phase 不在 worktree → exit 2
  6. 否则 → exit 0 (放行)
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_guard_test_dir = os.environ.get("_GUARD_TEST_CHANGES_DIR")
if _guard_test_dir:
    CHANGES_DIR = Path(_guard_test_dir)
    REQUIRED_BASE = CHANGES_DIR.parent.parent
else:
    CHANGES_DIR = REPO_ROOT / "openspec" / "changes"
    REQUIRED_BASE = REPO_ROOT

METHODS_FILE = REPO_ROOT / "scripts" / "workflow_methods.json"

_MANAGEMENT_FILES = {"handoff.json", "workflow_methods.json", "workflow_hook.example.json"}

# ── Bash write patterns ─────────────────────────────────────────────
_BASH_WRITE_PATTERNS = [
    # output redirection: > file, >> file, 2> file, &> file, |& file
    r'\s[0-9]?>>?\s+\S',            # >file, >>file, 2>file
    r'\s[>&][>&]?\s+\S',             # &> file, &>> file
    r'<<<\s',                        # here-string
    # tee (written to file)
    r'\|\s*tee\s',                   # | tee file
    r'\btee\s+\S',                   # tee file (start of command)
    # in-place file modification
    r'\bsed\s+.*-i',                 # sed -i
    r'\bsed\s+.*--in-place',         # sed --in-place
    # file creation / copy / move
    r'\bcp\s+',                      # cp src dst
    r'\bmv\s+',                      # mv src dst
    r'\bmkdir\s+',                   # mkdir dir
    r'\btouch\s+',                   # touch file
    r'\bdd\s+.*\bof=',               # dd of=file
    r'\binstall\s+',                 # install file
    # destructive git
    r'\bgit\s+(commit|add|push|tag|branch\s+-[dD]|stash(?!\s+list))',
    r'\bgit\s+checkout\s+-[bB]',     # git checkout -b (create branch)
    r'\bgit\s+rm\s+',                # git rm
    # python -c with file writes (not print/arithmetic)
    r'\bpython3?\s+-c\s+.*\b(open|write|dump|save|remove|unlink|'
    r'chmod|mkdir|rmdir|shutil|os\.system|subprocess)\s*\(',
    # perl/ruby in-place edit
    r'\bperl\s+-[pie]',              # perl -pi -e
    r'\bruby\s+-[pie]',              # ruby -pi -e
    # chmod +x (make script executable)
    r'\bchmod\s+.*\+x',
    # rm, rmdir
    r'\brm\s+(-[rRf]+\s+)?\S',
    r'\brmdir\s+',
    # curl/wget -O (save to file)
    r'\bcurl\s+.*-[Oo]\s',
    r'\bwget\s+.*-[Oo]\s',
]

_READ_ONLY_ALLOW = re.compile(
    r'^\s*(ls|find|which|pwd|env|echo|cat|head|tail|wc|sort|uniq|'
    r'grep|rg|git\s+status|git\s+log|git\s+diff|git\s+branch|git\s+remote|'
    r'git\s+worktree\s+list|git\s+stash\s+list|'
    r'uv\s+run|pytest|npm\s+(test|run|list|view|info|outdated)|'
    r'npx\s+|node\s+-[vp]|node\s+--version|'
    r'python3?\s+--version|python3?\s+-[mv]|'
    r'curl\s+[^-]|wget\s+[^-]|'
    r'which|type|command\s+-v|'
    r'df|du|free|ps|top|uptime|uname|whoami|'
    r'diff|colordiff|sdiff|'
    r'poetry\s+show|poetry\s+check|'
    r'pip\s+list|pip\s+show|pip\s+freeze|'
    r'^cd\s|^echo\s)',
    re.IGNORECASE
)


def _is_write_bash(command: str) -> bool:
    """Check if a Bash command contains file-write operations."""
    if not command or not command.strip():
        return False
    # strip leading shell builtins that don't affect the write analysis
    stripped = command.strip()
    # remove leading variable assignments: FOO=bar cmd
    stripped = re.sub(r'^(\w+=[^\s]+\s*)+', '', stripped)
    # remove leading 'cd /x && ' or 'cd /x; '
    stripped = re.sub(r'^cd\s+\S+\s*(&&|;)\s*', '', stripped)
    # remove leading 'export FOO=bar && '
    stripped = re.sub(r'^export\s+\S+\s*(&&|;)\s*', '', stripped)

    if not stripped.strip():
        return False

    # Check write patterns FIRST — "echo hello" is safe, "echo > file" is not
    for pattern in _BASH_WRITE_PATTERNS:
        if re.search(pattern, stripped):
            return True

    # fast path: common read-only commands (only reached if no write pattern matched)
    if _READ_ONLY_ALLOW.match(stripped):
        return False

    # unknown command → conservative: treat as safe (let it run, gate checks elsewhere)
    return False


def _discover_active_change():
    if not CHANGES_DIR.exists():
        return None
    for d in sorted(CHANGES_DIR.iterdir()):
        if not d.is_dir():
            continue
        hj = d / "handoff.json"
        if not hj.exists():
            continue
        try:
            data = json.loads(hj.read_text())
            if data.get("state", {}).get("phase") != "done":
                return (d.name, data)
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _load_methods():
    if METHODS_FILE.exists():
        return json.loads(METHODS_FILE.read_text())
    return {}


def _in_worktree():
    import subprocess
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True, text=True, timeout=5
        )
        cwd = os.getcwd()
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if parts and parts[0] == cwd:
                return "worktree" in line.lower() or parts[0] != str(REPO_ROOT)
        return False
    except Exception:
        return False


def _check_gate(change_id, handoff, methods):
    phase = handoff["state"]["phase"]
    sub_state = handoff["state"]["sub_state"]
    phase_cfg = methods.get(phase, {})

    if phase_cfg.get("require_worktree") and not _in_worktree():
        print(
            f"⛔ Phase={phase} 要求独立 git worktree。",
            f"Change: {change_id}",
            f"请先创建 worktree: python3 scripts/workflow_state.py advance --change {change_id}",
            file=sys.stderr,
        )
        return False

    required_files = phase_cfg.get("required_files_before_write", [])
    if isinstance(required_files, list):
        for rf_pattern in required_files:
            resolved = rf_pattern.replace("{change_id}", change_id)
            p = REQUIRED_BASE / resolved
            if not p.exists():
                print(
                    f"⛔ 缺少必备文件: {resolved}",
                    f"Change: {change_id}  Phase: {phase}/{sub_state}",
                    f"请先完成此阶段再修改代码。",
                    file=sys.stderr,
                )
                return False
    return True


def main():
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # ── determine if this tool call is a "write operation" ──
    is_write = False
    if tool_name in ("Write", "Edit"):
        is_write = True
    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        is_write = _is_write_bash(command)

    if not is_write:
        sys.exit(0)

    # ── management files always bypass ──
    file_path = tool_input.get("file_path", "")
    if file_path:
        if Path(file_path).name in _MANAGEMENT_FILES:
            sys.exit(0)

    # ── gate check ──
    active = _discover_active_change()
    methods = _load_methods()

    if active is None:
        print(
            "⛔ 无活跃 OpenSpec change。",
            "请先创建 change: mkdir -p openspec/changes/<change-id>",
            "然后创建 handoff.json (python3 scripts/workflow_state.py init --change <id>)",
            file=sys.stderr,
        )
        sys.exit(2)

    change_id, handoff = active
    if not _check_gate(change_id, handoff, methods):
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

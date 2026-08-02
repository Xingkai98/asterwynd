#!/usr/bin/env python3
"""PreToolUse hook: 受保护文件门禁 — 阻止 Agent 直接写入受保护 artifact。

用法 (Claude Code settings.json):
  "PreToolUse": [{"matcher": "Write|Edit|Bash", "command": "python3 scripts/workflow_guard.py"}]

拦截:
  - Write / Edit 工具写入受保护路径
  - Bash 命令中对受保护路径的写操作
  - Bash 命令中包含写操作模式的 (>, >>, tee, sed -i, cp, mv, mkdir,
    git commit/add/push, touch, dd of=, python -c/exec with write, etc)

受保护路径（始终拦截，不随 workflow 状态变化）:
  - docs/known-debt.md, docs/known-issues.md, docs/openspec-change-backlog.md
  - openspec/specs/, openspec/changes/archive/, workflow-events.jsonl
  - handoff.json, gate-approvals.json, -review-manifest.json

状态机仪式（issue #90）已停用：不再检查 phase/required_files/worktree。
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _resolve_changes_dir(repo_root: Path) -> Path:
    """Resolve changes directory from workflow_methods.json doc_artifact config.

    Falls back to openspec/changes if config is unavailable.
    """
    methods_path = repo_root / "scripts" / "workflow_methods.json"
    try:
        if methods_path.exists():
            methods = json.loads(methods_path.read_text(encoding="utf-8"))
            doc_artifact = methods.get("doc_artifact", {})
            paths = doc_artifact.get("paths", {})
            tmpl = paths.get("change_dir_template", "openspec/changes/{change_id}")
            # Extract base: everything before {change_id}
            base = tmpl.split("/{")[0] if "/{" in tmpl else tmpl.rsplit("/", 1)[0]
            return repo_root / base
    except (json.JSONDecodeError, OSError):
        pass
    return repo_root / "openspec" / "changes"


_guard_test_dir = os.environ.get("_GUARD_TEST_CHANGES_DIR")
if _guard_test_dir:
    CHANGES_DIR = Path(_guard_test_dir)
    REQUIRED_BASE = CHANGES_DIR.parent.parent
else:
    CHANGES_DIR = _resolve_changes_dir(REPO_ROOT)
    REQUIRED_BASE = REPO_ROOT

_MANAGEMENT_FILES = {"workflow_methods.json", "workflow_hook.example.json"}
_PROTECTED_PATH_FRAGMENTS = (
    "docs/known-debt.md",
    "docs/known-issues.md",
    "docs/openspec-change-backlog.md",
    "openspec/specs/",
    "openspec/changes/archive/",
    "workflow-events.jsonl",
    "gate-approvals.json",
    "-review-manifest.json",
    "handoff.json",
)

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


def _mentions_protected_path(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return any(fragment in normalized for fragment in _PROTECTED_PATH_FRAGMENTS)




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
    if file_path and Path(file_path).name in _MANAGEMENT_FILES:
        sys.exit(0)

    # ── protected-path guard stays enforced regardless of workflow state ──
    if file_path and _mentions_protected_path(file_path):
        print(
            f"⛔ 受保护文件不可由 Agent 直接写入: {file_path}",
            "受保护 artifact 的修改需 workflow-events.jsonl 结构化解释事件或 review manifest。",
            file=sys.stderr,
        )
        sys.exit(2)

    if tool_name == "Bash" and _mentions_protected_path(tool_input.get("command", "")):
        print(
            "⛔ 受保护路径不可通过 Bash 直接写入。",
            "受保护 artifact 的修改需 workflow-events.jsonl 结构化解释事件或 review manifest。",
            file=sys.stderr,
        )
        sys.exit(2)

    # ── state-machine ceremony is disabled (issue #90) ──
    # The phase gate check (active change / worktree / required files) is
    # retired: the OpenSpec + review-loop flow replaces it. Only the protected
    # path guard above remains enforced, always.
    sys.exit(0)


if __name__ == "__main__":
    main()

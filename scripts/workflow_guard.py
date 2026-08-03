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
import subprocess
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


# ── grill gate (issue #95) ────────────────────────────────────────────
# 写代码前门禁：非 docs + 有 spec delta 的 change，代码写操作前必须有
# reviews/grill-design.md 证据。分支名 `<change-id>/<date>` 推导为主，
# 单 active change 兜底；两者都不成立则门禁不触发。
# 文档类写操作（proposal/design/tasks/specs/reviews）豁免，避免死锁。


def _current_change_id() -> str | None:
    """Map the current worktree/branch to a change id.

    Priority: branch name `<change-id>/<date>` (or `<change-id>/<anything>`);
    fallback: exactly one active change directory. Returns None if ambiguous.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
        if branch:
            head = branch.split("/")[0]
            if head and head != "master" and head != "main":
                # sanity: an active change dir with this id should exist
                if (CHANGES_DIR / head).is_dir():
                    return head
    except Exception:
        pass

    # Fallback: single active change
    if CHANGES_DIR.exists():
        active = [
            d.name for d in sorted(CHANGES_DIR.iterdir())
            if d.is_dir() and (d / "proposal.md").exists()
        ]
        if len(active) == 1:
            return active[0]
    return None


def _grill_evidence_missing(change_id: str) -> bool:
    """True if a change that requires grilling lacks complete grill evidence.

    A change requires grilling when it is non-docs (has a spec delta) — i.e. it
    will ship implementation code. docs-only changes skip the gate.

    Reordered (grill-confirmation-gate Must-fix B): the "requires grilling"
    check now runs BEFORE the evidence check, so a docs-only or proposal-stage
    change is never blocked by a partial grill-design.md. Completeness: when the
    evidence exists but Open Questions are not all confirmed in
    ``## User Confirmation``, the evidence is treated as missing so code writes
    are blocked until the user confirms (grill-confirmation-gate Decision 3).
    """
    change_dir = CHANGES_DIR / change_id
    # 1. docs-only proposal? skip the gate.
    proposal = change_dir / "proposal.md"
    if proposal.exists():
        text = proposal.read_text(encoding="utf-8", errors="ignore")
        if "primary: docs" in text:
            return False
    # 2. non-docs check: must have a spec delta to require grilling.
    specs = change_dir / "specs"
    if not specs.exists():
        return False
    if not any(specs.glob("*/spec.md")):
        return False
    # 3. evidence completeness.
    evidence = change_dir / "reviews" / "grill-design.md"
    if not evidence.exists():
        return True
    try:
        text = evidence.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True
    open_indexes = _extract_open_question_indexes(text)
    if not open_indexes:
        return False
    confirmed = set(_extract_user_confirmation_indexes(text))
    return any(q not in confirmed for q in open_indexes)


# ── grill evidence extraction (mirrors scripts/check_openspec_artifacts.py) ──
# Replicated here (hook is self-contained per issue #95). A parity test in
# tests/test_workflow_guard.py pins the two implementations to the same output.

_UNCONFIRMED_EXACT = {
    "todo", "tbd", "n/a", "na", "无", "none",
    "待确认", "未确认", "待定", "pending", "待补充", "占位", "未决",
}
_UNCONFIRMED_STRONG = {
    "待主 agent", "待主agent", "待用户", "placeholder", "tobeconfirmed",
    "待拍板", "未拍板",
}
_UNCONFIRMED_MAX_ANSWER_LEN = 20
_UNCONFIRMED_STRIP = str.maketrans("", "", "。．.；;，,、 \t")


def _is_unconfirmed_answer(answer: str) -> bool:
    a = answer.lower().strip().translate(_UNCONFIRMED_STRIP)
    if not a:
        return True
    if a in _UNCONFIRMED_EXACT:
        return True
    if len(a) <= _UNCONFIRMED_MAX_ANSWER_LEN:
        for tok in _UNCONFIRMED_STRONG:
            if tok in a:
                return True
    return False


def _extract_open_question_indexes(text: str) -> list[str]:
    """Open Questions entry indexes (``1.`` / ``- **Q1**:`` / ``- Q1 ...``)."""
    section = _h2_section(text, "Open Questions")
    if not section:
        return []
    indexes: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip "no open questions" markers in any form (bare, numbered, "- 无").
        no_q = re.sub(r"^[-*]\s*", "", stripped)
        no_q = re.sub(r"^\d+[.、]\s*", "", no_q)
        no_q = re.sub(r"^\*\*", "", no_q)
        if no_q.strip() in {"无", "无。", "none", "none。", "没有", "无问题"}:
            continue
        # Read the leading index of a real entry (from the original line).
        m = re.match(r"^[-*]?\s*\**\s*(?:(?:Q|q)\d+|\d+)\s*[:：.]?\s*", stripped)
        if m:
            idx = _normalize_question_index(m.group(0))
            if idx:
                indexes.append(idx)
    return indexes


def _extract_user_confirmation_indexes(text: str) -> list[str]:
    """Confirmed Open Questions indexes from ``## User Confirmation``."""
    section = _h2_section(text, "User Confirmation")
    if not section:
        return []
    indexes: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        m = re.match(r"^-\s+\*\*Q(\d+)\*\*\s*[:：]", stripped)
        if not m:
            continue
        answer_match = re.search(r"用户答复\s*[:：]\s*(.*?)(?:[；;]\s*确认时间|\s*$)", stripped)
        if not answer_match:
            continue
        answer = answer_match.group(1).strip().strip("`")
        if not answer or _is_unconfirmed_answer(answer):
            continue
        indexes.append(f"Q{m.group(1)}")
    return indexes


def _normalize_question_index(raw: str) -> str | None:
    cleaned = raw.strip().strip(".")
    cleaned = re.sub(r"^[-*]\s*\**\s*", "", cleaned)
    m = re.match(r"(?:[Qq])?(\d+)", cleaned)
    if not m:
        return None
    return f"Q{m.group(1)}"


def _h2_section(text: str, title: str) -> str:
    """Return the body of the ``## <title>`` section, or empty string."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        if match.group(1).strip() == title:
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def _is_change_doc_write(file_path: str) -> bool:
    """True if the write targets change doc files (exempt from grill gate)."""
    normalized = Path(file_path).as_posix()
    for change_dir in CHANGES_DIR.glob("*"):
        if not change_dir.is_dir():
            continue
        prefix = change_dir.as_posix() + "/"
        if not normalized.startswith(prefix):
            continue
        rel = normalized[len(prefix):]
        if rel in ("proposal.md", "design.md", "tasks.md"):
            return True
        if rel.startswith("specs/") or rel.startswith("reviews/"):
            return True
    return False




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

    # ── grill gate (issue #95) ──
    # 写代码前必须完成独立 subagent design grilling。仅对非 docs + 有 spec
    # delta 的 change 生效；文档类写操作豁免；无法映射 change 时不触发。
    file_path = tool_input.get("file_path", "")
    if file_path and not _is_change_doc_write(file_path):
        change_id = _current_change_id()
        if change_id is not None and _grill_evidence_missing(change_id):
            print(
                f"⛔ change '{change_id}' 尚未完成独立 subagent design grilling。",
                f"缺少 {CHANGES_DIR / change_id / 'reviews' / 'grill-design.md'}。",
                "请先运行 /grill 命令：独立零记忆 subagent 挑战 design.md，",
                "产出结构化决策记录到 reviews/grill-design.md，再写代码。",
                file=sys.stderr,
            )
            sys.exit(2)

    # ── state-machine ceremony is disabled (issue #90) ──
    # The phase gate check (active change / worktree / required files) is
    # retired: the OpenSpec + review-loop flow replaces it. Only the protected
    # path guard and grill gate above remain enforced.
    sys.exit(0)


if __name__ == "__main__":
    main()

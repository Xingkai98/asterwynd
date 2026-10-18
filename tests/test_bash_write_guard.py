"""Bash-only 写前拦截：拦截面、防误伤、match 语义与已知绕过面。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.bash_write_guard as guard


REPO_ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_REQUIRE = ["agent/**", "scripts/**", "web/**"]
EMBEDDED_PROTECTED = [
    "openspec/specs/**",
    ".witnessloop/**",
    "docs/known-issues.md",
    "docs/known-debt.md",
    "docs/openspec-change-backlog.md",
]


def _root(tmp_path: Path, *, policy: dict | None = None) -> Path:
    root = tmp_path / "repo"
    (root / ".witnessloop").mkdir(parents=True)
    if policy is not None:
        (root / ".witnessloop" / "policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )
    return root


@pytest.mark.parametrize(
    "command",
    [
        "echo x > agent/y",
        "echo x >> agent/y",
        "echo x>>agent/y",
        "cmd 2> agent/y",
        "cmd &> agent/y",
        "echo x >| agent/y",
        "cp x agent/y",
        "cp -r x agent/y",
        "mv x agent/y",
        "mv agent/y /tmp/z",
        "tee agent/y",
        "tee -a scripts/y",
        "sed -i 's/a/b/' agent/y",
        "sed --in-place 's/a/b/' agent/y",
        "dd if=/dev/zero of=agent/y",
        "install x agent/y",
        "rm agent/y",
        "rm -rf agent",
        "touch agent/y",
        "mkdir -p scripts/new",
        "rmdir web/empty",
        "unlink web/y",
        "truncate -s 0 agent/y",
        "ln -s x agent/y",
        "chmod +x scripts/y",
        "chown u:g agent/y",
        "perl -pi -e 's/a/b/' agent/y",
        "ruby -pi -e 's/a/b/' agent/y",
        "curl -o agent/y https://example.com",
        "wget -O agent/y https://example.com",
        "python -c \"open('agent/y','w').write('x')\"",
        "cd agent && echo x > y",
        "cd scripts; touch new",
        "bash -c 'echo x > agent/y'",
        "sh -c \"cd web && touch y\"",
        "eval 'echo x > agent/y'",
        "echo $(touch agent/y)",
        "echo `touch agent/y`",
        "git restore agent/y",
        "git checkout -- agent/y",
        "git apply patch.diff",
        "git -C . restore agent/y",
        "git -C . checkout -- agent/y",
        "echo x > openspec/specs/a/spec.md",
        "tee docs/known-debt.md",
        "echo x > .witnessloop/policy.json",
    ],
)
def test_blocks_writes_to_managed_or_protected_paths(tmp_path, command):
    root = _root(tmp_path)
    assert guard.evaluate_command(command, root), command


def test_blocks_absolute_path_inside_repo(tmp_path):
    root = _root(tmp_path)
    assert guard.evaluate_command(f"echo x > {root}/agent/y", root)


@pytest.mark.parametrize(
    "command",
    [
        "ls agent",
        "grep -n foo agent/loop.py",
        "cat docs/known-debt.md",
        "git status",
        "git diff",
        "rg 'echo > agent/y' files",
        'git commit -m "cp x agent/y"',
        "cp agent/x /tmp/y",
        "sed -i 's|agent/|x|' docs/y",
        "echo ok >/dev/null",
        "cmd 2>&1",
        "cat <<'EOF'\nrm agent/x\nEOF",
        "git apply --check patch.diff",
        "git apply --stat patch.diff",
        "git restore --staged agent/y",
        "git -C . restore --staged agent/y",
        "rsync -a agent/x /tmp/y",
        "git rm agent/x",
        "git mv agent/x agent/z",
        "git cherry-pick abc123",
        "echo x > /tmp/y",
        "echo x > scriptsfoo/y",
        "echo x > agent2/y",
        "python -c \"print('agent/y')\"",
        "uv run pytest -q",
        "python scripts/self_check.py",
    ],
)
def test_allows_reads_and_non_matching_targets(tmp_path, command):
    root = _root(tmp_path)
    assert guard.evaluate_command(command, root) == [], command


def test_policy_is_loaded_from_witnessloop_policy(tmp_path):
    policy = {
        "require_change_for": ["lib/**"],
        "protected_paths": ["secret.md"],
    }
    root = _root(tmp_path, policy=policy)
    assert guard.evaluate_command("echo x > lib/y", root)
    assert guard.evaluate_command("echo x > secret.md", root)
    assert guard.evaluate_command("echo x > agent/y", root) == []


def test_missing_policy_falls_back_to_embedded_defaults(tmp_path):
    root = _root(tmp_path, policy=None)
    assert guard.evaluate_command("echo x > agent/y", root)
    assert guard.evaluate_command("echo x > docs/known-debt.md", root)


def test_malformed_policy_falls_back_to_embedded_defaults(tmp_path):
    root = tmp_path / "repo"
    (root / ".witnessloop").mkdir(parents=True)
    (root / ".witnessloop" / "policy.json").write_text("{not json", encoding="utf-8")
    assert guard.evaluate_command("echo x > agent/y", root)


def test_embedded_policy_matches_repo_policy():
    policy_path = REPO_ROOT / ".witnessloop" / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert guard.EMBEDDED_REQUIRE_CHANGE_FOR == list(policy["require_change_for"])
    assert guard.EMBEDDED_PROTECTED_PATHS == list(policy["protected_paths"])


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("agent/**", "agent/y", True),
        ("agent/**", "agent/sub/y", True),
        ("agent/**", "agent", True),
        ("agent/**", "scriptsfoo/y", False),
        ("agent/*", "agent/y", True),
        ("agent/*", "agent/sub/y", False),
        ("scripts/**", "scriptsfoo/y", False),
        (".witnessloop/**", ".witnessloop/policy.json", True),
        ("docs/known-debt.md", "docs/known-debt.md", True),
        ("docs/known-debt.md", "docs/known-debt.md.bak", False),
    ],
)
def test_glob_semantics(pattern, path, expected):
    assert guard._matches(path, [pattern]) is expected


def test_hook_json_blocks_bash_write(tmp_path):
    root = _root(tmp_path)
    code = guard.run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "echo x > agent/y"}}, root
    )
    assert code == 2


def test_hook_json_allows_read_and_other_tools(tmp_path):
    root = _root(tmp_path)
    assert (
        guard.run_hook({"tool_name": "Bash", "tool_input": {"command": "ls agent"}}, root)
        == 0
    )
    assert (
        guard.run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "agent/y"}}, root
        )
        == 0
    )


def test_cli_command_mode(tmp_path):
    root = _root(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bash_write_guard.py"),
            "--root",
            str(root),
            "--command",
            "echo x > agent/y",
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert result.returncode == 2
    assert "agent/y" in result.stderr
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bash_write_guard.py"),
            "--root",
            str(root),
            "--command",
            "ls agent",
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert result.returncode == 0


def test_hook_stdin_mode(tmp_path):
    root = _root(tmp_path)
    env = os.environ.copy()
    env["BASH_WRITE_GUARD_ROOT"] = str(root)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "bash_write_guard.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "tee agent/y"}}),
        capture_output=True,
        text=True,
        env=env,
        errors="replace",
    )
    assert result.returncode == 2


# ── 已知残余绕过面：如实登记，不假装封死 ─────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "echo x > $DIR/agent/y",  # 变量展开
        "find agent -name x -exec rm {} \\;",  # find -exec 路径
        "python build.py",  # 被执行程序自行写文件
        "make",  # 同上
        "alias w='echo x > agent/y'",  # alias 定义
        "echo x > link/y",  # 符号链接（路径本身不命中）
        "git merge feature",  # VCS 内容写入
        "git rebase main",
        "git stash",
    ],
)
def test_known_bypasses_are_documented_as_allowed(tmp_path, command):
    """这些形态无法静态判定；guard 不拦，CI 兜底。测试锁定「已知」而不是「已封死」。"""
    root = _root(tmp_path)
    assert guard.evaluate_command(command, root) == [], command

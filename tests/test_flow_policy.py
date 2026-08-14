"""flow-policy-source P0 集成测试：单一策略源、guard/checker 同源、fail-closed、
4 绕过、parity、内容门槛、schema 校验、policy-* CLI。

关联 issue #131（P0）。测试覆盖 tasks.md 2.1-2.8。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "workflow_guard.py"
POLICY = REPO_ROOT / "scripts" / "flow-policy.json"


def _run_guard(tmp_path, payload, policy_path=None):
    env = os.environ.copy()
    env["_GUARD_TEST_CHANGES_DIR"] = str(tmp_path / "openspec" / "changes")
    if policy_path is not None:
        env["_GUARD_TEST_POLICY_PATH"] = str(policy_path)
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


# ── guard：策略加载与 fail-closed ─────────────────────────────────────


def test_guard_loads_rules_from_policy(tmp_path):
    """guard 从 flow-policy.json 加载规则（单条自定义规则生效）。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {"protected_paths": [
                {"path": "docs/custom-guarded.md", "match_type": "exact",
                 "governance": "guard_only"},
            ]}
        ),
        encoding="utf-8",
    )
    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "docs/custom-guarded.md"}},
        policy_path=policy,
    )
    assert result.returncode == 2


def test_guard_fail_closed_missing_policy(tmp_path):
    """策略文件缺失 → guard fail-closed exit 2。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "agent/feature.py"}},
        policy_path=tmp_path / "missing-policy.json",
    )
    assert result.returncode == 2
    assert "fail-closed" in result.stderr or "flow-policy.json" in result.stderr


def test_guard_fail_closed_corrupt_policy(tmp_path):
    """策略文件损坏（非法 JSON）→ guard fail-closed exit 2。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    policy = tmp_path / "policy.json"
    policy.write_text("{not valid json", encoding="utf-8")
    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "agent/feature.py"}},
        policy_path=policy,
    )
    assert result.returncode == 2


def test_guard_fail_closed_event_explained_without_event_types(tmp_path):
    """event_explained 规则缺 event_types → 策略非法 → fail-closed。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"protected_paths": [
            {"path": "docs/known-debt.md", "match_type": "exact", "governance": "event_explained"},
        ]}),
        encoding="utf-8",
    )
    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "agent/feature.py"}},
        policy_path=policy,
    )
    assert result.returncode == 2


# ── guard：4 个绕过回归 ───────────────────────────────────────────────


@pytest.mark.parametrize("command", [
    "echo >docs/known-debt.md",            # 无空格重定向
    "cat <<EOF > docs/known-debt.md",      # here-doc + 重定向
    "python3 -c \"Path('docs/known-debt.md').write_text('x')\"",  # pathlib
    "echo hi > docs/./known-debt.md",      # ./ 变体（重定向目标）
])
def test_guard_blocks_four_bypasses(tmp_path, command):
    """P0 出口：4 个实测绕过全部被拦（exit 2）。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    result = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": command}},
    )
    assert result.returncode == 2, f"命令应被拦: {command}\n{result.stderr}"


def test_guard_blocks_dot_slash_write(tmp_path):
    """Write 到 docs/./known-debt.md（./ 变体）被拦。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "docs/./known-debt.md"}},
    )
    assert result.returncode == 2


# ── guard：豁免与只读放行 ─────────────────────────────────────────────


@pytest.mark.parametrize("command", [
    "python3 scripts/workflow_state.py artifact-event --change test --event-type protected_artifact_explained --artifact-path docs/known-debt.md --reason ok --approved-by human",
    "python3 scripts/workflow_state.py policy-show",
    "python3 scripts/workflow_state.py policy-set --path docs/x.md --match-type exact --governance guard_only",
])
def test_guard_exempts_privileged_cli(tmp_path, command):
    """workflow_state.py artifact-event/review-manifest/policy-* 写通道豁免。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    result = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": command}},
    )
    assert result.returncode == 0, f"豁免命令不应被拦: {command}\n{result.stderr}"


@pytest.mark.parametrize("command", [
    "cat docs/known-debt.md",
    "git diff openspec/specs/dev-workflow-state-machine/spec.md",
    "git status",
])
def test_guard_allows_readonly_commands(tmp_path, command):
    """只读命令含受保护路径 → 放行（写意图感知，非 blanket contains）。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    result = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": command}},
    )
    assert result.returncode == 0, f"只读命令不应被拦: {command}\n{result.stderr}"


# ── 正则死锁修复（guard 与 checker 同步）──────────────────────────────


def test_confirmation_regex_tolerates_suffix_suffix():
    """`- **Q8**（分支命名）: 用户答复：...` 后缀可提取（guard 与 checker 同步）。"""
    import scripts.workflow_guard as wg
    from scripts.check_openspec_artifacts import _extract_user_confirmation_indexes as ck

    text = (
        "## User Confirmation\n"
        "- **Q8**（分支命名）: 用户答复：分支名 = name；确认时间: 2026-08-07\n"
    )
    assert wg._extract_user_confirmation_indexes(text) == ["Q8"]
    assert ck(text) == ["Q8"]


def test_h2_section_skips_fenced_code_block():
    """fenced code block 内 `##` 不当 section 标题（guard 与 checker 同步）。"""
    import scripts.workflow_guard as wg
    from scripts.check_openspec_artifacts import _extract_h2_sections as ck

    text = (
        "## Context\n"
        "ctx\n"
        "```md\n"
        "## Not a real section\n"
        "```\n"
        "## Decisions\n"
        "decision\n"
    )
    assert wg._h2_section(text, "Decisions") == "decision"
    sections = ck(text)
    assert "Decisions" in sections
    assert "Not a real section" not in sections


# ── 同源 parity ───────────────────────────────────────────────────────


def test_policy_disk_matches_guard_default():
    """磁盘策略表 == guard 内嵌默认表（event_explained 子集链式断言）。"""
    import scripts.check_openspec_artifacts as checker
    import scripts.workflow_guard as guard

    data = json.loads(POLICY.read_text(encoding="utf-8"))
    disk_ev = {
        (r["path"], r["match_type"], tuple(r.get("event_types", [])))
        for r in data["protected_paths"]
        if r["governance"] == "event_explained"
    }
    default_ev = {
        (r["path"], r["match_type"], tuple(r.get("event_types", [])))
        for r in guard._DEFAULT_PROTECTED_PATHS
        if r["governance"] == "event_explained"
    }
    # 链式断言：guard 内嵌 event_explained 子集 == 磁盘子集 == checker 加载集
    assert disk_ev == default_ev

    checker_rules = checker._load_protected_path_rules(REPO_ROOT)
    assert checker_rules is not None
    checker_ev = {(p, mt, et) for mt, p, et in checker_rules}
    assert checker_ev == disk_ev


def test_guard_bash_fragments_derive_from_policy():
    """guard 的 Bash 受保护扫描 fragment 集 == 策略表 path 值集。"""
    import scripts.workflow_guard as guard

    data = json.loads(POLICY.read_text(encoding="utf-8"))
    policy_paths = {r["path"] for r in data["protected_paths"]}
    default_paths = {r["path"] for r in guard._DEFAULT_PROTECTED_PATHS}
    assert policy_paths == default_paths
    # 磁盘表加载后，Bash 扫描使用的 rule 集来自磁盘表
    rules = guard._load_protected_paths(guard._resolve_policy_path())
    assert {r["path"] for r in rules} == policy_paths


# ── checker：内容门槛（#123 阶段感知） ────────────────────────────────


def _seed_content_gate_change(tmp_path, *, tasks_all_done: bool, phrase: str):
    from scripts.check_openspec_artifacts import ChangeType

    change_dir = tmp_path / "openspec" / "changes" / "content-gate-change"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        "## Change Type\n\n- primary: feature\n\n"
        "## Reference Implementation Research\n\n"
        "- status: enabled\n"
        "- reason: 需要参考实现\n"
        f"- research questions: {phrase}\n"
        "- findings: 已有发现\n"
        "- design impact: 采用 A 而非 B\n",
        encoding="utf-8",
    )
    (change_dir / "tasks.md").write_text(
        "- [x] 完成项\n" if tasks_all_done else "- [ ] 未完成项\n",
        encoding="utf-8",
    )
    return change_dir


def test_checker_content_gate_fires_on_completed_change(tmp_path):
    """tasks 全勾 + 命中「自认未完成」短语 → check_change 报错。"""
    from scripts.check_openspec_artifacts import ChangeType, check_change

    change_dir = _seed_content_gate_change(tmp_path, tasks_all_done=True, phrase="尚未完成调研")
    errors = check_change(change_dir, Path(tmp_path) / "openspec" / "specs")
    text = "\n".join(errors)
    assert "尚未完成" in text
    assert "research questions" in text


def test_checker_content_gate_skips_proposal_stage(tmp_path):
    """tasks 未全勾（proposal 阶段）→ 结构门槛通过，不触发内容门槛。"""
    from scripts.check_openspec_artifacts import check_change

    change_dir = _seed_content_gate_change(tmp_path, tasks_all_done=False, phrase="尚未完成调研")
    errors = check_change(change_dir, Path(tmp_path) / "openspec" / "specs")
    text = "\n".join(errors)
    assert "自认未完成" not in text


def test_checker_content_gate_allows_clean_findings(tmp_path):
    """tasks 全勾但无占位短语 → 不报内容门槛。"""
    from scripts.check_openspec_artifacts import check_change

    change_dir = _seed_content_gate_change(tmp_path, tasks_all_done=True, phrase="参考本地参考仓库与 codegraph 符号")
    errors = check_change(change_dir, Path(tmp_path) / "openspec" / "specs")
    text = "\n".join(errors)
    assert "自认未完成" not in text


# ── checker：agent schema 校验（#127 P0） ─────────────────────────────


def test_checker_agent_schema_validation(tmp_path):
    """非法 phases/review agent schema → 校验报错；合法 → 通过。"""
    from scripts.check_openspec_artifacts import _validate_policy_agent_schema

    (tmp_path / "scripts").mkdir(parents=True)

    # 合法（当前真实 policy 语义）
    (tmp_path / "scripts" / "flow-policy.json").write_text(
        json.dumps({
            "protected_paths": [],
            "phases": {"building": {"agent": {"provider": "claude", "model": "claude-sonnet-5"}}},
            "review": {"agent": {"provider": "codex", "model": "gpt-5.4"}},
        }),
        encoding="utf-8",
    )
    assert _validate_policy_agent_schema(tmp_path) == []

    # 未知 phase 键
    (tmp_path / "scripts" / "flow-policy.json").write_text(
        json.dumps({"protected_paths": [], "phases": {"nonsense": {}}, "review": {}}),
        encoding="utf-8",
    )
    errs = _validate_policy_agent_schema(tmp_path)
    assert any("unknown phase `nonsense`" in e for e in errs)

    # agent 缺 model
    (tmp_path / "scripts" / "flow-policy.json").write_text(
        json.dumps({"protected_paths": [], "phases": {"building": {"agent": {"provider": "claude"}}}, "review": {}}),
        encoding="utf-8",
    )
    errs = _validate_policy_agent_schema(tmp_path)
    assert any("missing `model`" in e for e in errs)

    # review 未知键
    (tmp_path / "scripts" / "flow-policy.json").write_text(
        json.dumps({"protected_paths": [], "phases": {}, "review": {"executor": "x"}}),
        encoding="utf-8",
    )
    errs = _validate_policy_agent_schema(tmp_path)
    assert any("unknown review key `executor`" in e for e in errs)


# ── policy-* CLI ──────────────────────────────────────────────────────


def _run_policy_cli(*args):
    return subprocess.run(
        [sys.executable, "scripts/workflow_state.py", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_policy_show_and_validate_readonly():
    """policy-show 展示规则；policy-validate 校验通过（只读，不污染）。"""
    show = _run_policy_cli("policy-show")
    assert show.returncode == 0
    assert "docs/known-debt.md" in show.stdout
    assert "workflow-state.json" in show.stdout

    validate = _run_policy_cli("policy-validate")
    assert validate.returncode == 0
    assert "校验通过" in validate.stdout


def test_policy_set_upsert_and_delete_roundtrip():
    """policy-set 原子写 upsert/delete 单条规则（备份-还原不污染真实策略）。"""
    backup = POLICY.read_text(encoding="utf-8")
    try:
        add = _run_policy_cli(
            "policy-set", "--path", "docs/tmp-test.md",
            "--match-type", "exact", "--governance", "guard_only",
        )
        assert add.returncode == 0, add.stderr
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        assert any(r["path"] == "docs/tmp-test.md" for r in data["protected_paths"])

        delete = _run_policy_cli("policy-set", "--path", "docs/tmp-test.md", "--delete")
        assert delete.returncode == 0, delete.stderr
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        assert not any(r["path"] == "docs/tmp-test.md" for r in data["protected_paths"])
    finally:
        POLICY.write_text(backup, encoding="utf-8")


def test_policy_set_rejects_invalid_args():
    """policy-set 缺 match-type/governance（非 delete）→ 报错。"""
    result = _run_policy_cli("policy-set", "--path", "docs/x.md")
    assert result.returncode == 1
    assert "--match-type" in result.stderr or "必填" in result.stderr


# ── 审阅修复回归（building-review Round 1） ─────────────────────────


def test_guard_rejects_chained_privileged_cli_hijack(tmp_path):
    """Issue 1：特权 CLI 豁免不可被 &&/; 链式劫持。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    for cmd in (
        "python3 scripts/workflow_state.py policy-show && echo >docs/known-debt.md",
        "python3 scripts/workflow_state.py artifact-event --change x --event-type protected_artifact_explained --artifact-path docs/known-debt.md --reason r --approved-by h; echo x > docs/known-debt.md",
        "python3 scripts/workflow_state.py policy-show\npython3 -c \"Path('docs/known-debt.md').write_text('x')\"",
    ):
        result = _run_guard(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": cmd}},
        )
        assert result.returncode == 2, f"链式命令应被拦: {cmd}\n{result.stderr}"


def test_guard_empty_rules_consistent_fail_open(tmp_path):
    """Issue 2：空规则集时 Write 与 Bash 一致 fail-open（内嵌默认表不参与运行时）。"""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"protected_paths": []}), encoding="utf-8")
    w = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": "docs/known-debt.md"}},
        policy_path=policy,
    )
    b = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": "echo >docs/known-debt.md"}},
        policy_path=policy,
    )
    assert w.returncode == 0, f"Write 空规则集应放行: {w.stderr}"
    assert b.returncode == 0, f"Bash 空规则集应放行: {b.stderr}"


def test_unconfirmed_vocab_parity():
    """Issue 4：unconfirmed 词表 guard↔checker 一致（机械断言）。"""
    import scripts.workflow_guard as wg
    from scripts.check_openspec_artifacts import (
        UNCONFIRMED_EXACT,
        UNCONFIRMED_STRONG,
    )

    assert wg._UNCONFIRMED_EXACT == UNCONFIRMED_EXACT
    assert wg._UNCONFIRMED_STRONG == UNCONFIRMED_STRONG


def test_checker_schema_error_is_readable(tmp_path):
    """Issue 3：checker 对 schema 非法策略返回可读错误而非裸 traceback。"""
    from scripts.check_openspec_artifacts import check_protected_path_explanations

    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "flow-policy.json").write_text(
        json.dumps({"protected_paths": [
            {"path": "docs/known-debt.md", "match_type": "exact", "governance": "event_explained"},
        ]}),
        encoding="utf-8",
    )
    errors = check_protected_path_explanations(tmp_path, changed_paths={"docs/known-debt.md"})
    assert errors, "应返回可读错误"
    assert any("schema 非法" in e or "event_types" in e for e in errors)

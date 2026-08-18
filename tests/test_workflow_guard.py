from __future__ import annotations

import json
import os
import io
import subprocess
import sys
from pathlib import Path
import pytest

from agent.workflow.manager import WorkflowManager

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "workflow_guard.py"


def _run_guard(tmp_path: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["_GUARD_TEST_CHANGES_DIR"] = str(tmp_path / "openspec" / "changes")
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )


def _seed_active_change(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    WorkflowManager(change_dir, repo_root=tmp_path).init("test-change")


def _seed_reviewing_change(tmp_path: Path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    handoff = {
        "schema_version": "1.0",
        "change_id": "test-change",
        "state": {"phase": "building", "sub_state": "reviewing_impl"},
        "transitions": [],
    }
    (change_dir / "handoff.json").write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def test_guard_blocks_direct_writes_to_protected_files(tmp_path):
    _seed_active_change(tmp_path)

    cases = [
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "openspec" / "changes" / "test-change" / "handoff.json")}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / ".handoff" / "test-change" / "building-review-manifest.json")}},
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "docs" / "known-debt.md")}},
    ]

    for payload in cases:
        result = _run_guard(tmp_path, payload)
        assert result.returncode == 2
        assert "⛔" in result.stderr


def test_guard_allows_workflow_state_cli_commands(tmp_path):
    _seed_active_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "python3 scripts/workflow_state.py artifact-event "
                    "--change test-change "
                    "--event-type protected_artifact_explained "
                    "--artifact-path docs/known-debt.md "
                    "--reason ok "
                    "--approved-by human"
                )
            },
        },
    )

    assert result.returncode == 0


def test_guard_agent_calls_are_not_tracked_when_workflow_disabled(tmp_path):
    """issue #90：状态机停用后，_agent-calls.json 审阅跟踪不再产生。

    独立审阅闭环由 /review-loop 命令驱动，产物是 building-review.md + manifest，
    不再依赖 handoff.json 驱动的 _agent-calls.json 跟踪。
    """
    _seed_reviewing_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Agent",
            "tool_input": {"prompt": "review implementation"},
        },
    )

    log_path = tmp_path / ".handoff" / "test-change" / "_agent-calls.json"
    assert result.returncode == 0
    assert not log_path.exists(), "状态机停用后不应再记录 _agent-calls.json"


def test_guard_noops_when_workflow_disabled(tmp_path, monkeypatch):
    """issue #90：状态机停用后，普通写操作放行（exit 0）。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "agent" / "test.py")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 0


def test_guard_blocks_protected_files_even_when_workflow_disabled(tmp_path, monkeypatch):
    """issue #90：受保护文件（known-issues/known-debt/specs/archive）始终拦截，
    不随状态机停用而放行——这是安全边界，不依赖 workflow 状态。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "docs" / "known-debt.md")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 2


def test_guard_resume_audit_no_longer_blocks_writes(tmp_path, monkeypatch):
    """issue #90：resume audit 门禁已停用（状态机仪式），普通写操作放行。"""
    import scripts.workflow_guard as mod

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")},
                }
            )
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        mod.main()

    assert excinfo.value.code == 0


# ── grill 门禁（issue #95）────────────────────────────────────────────


def _seed_grill_change(tmp_path: Path, change_id: str = "grill-change") -> None:
    """Seed a change dir with a spec delta (triggers grill gate)."""
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "proposal.md").write_text("## Change Type\n\nprimary: feature\n", encoding="utf-8")
    (change_dir / "design.md").write_text("## Context\n\nctx\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("## 1. 实现\n\n- [x] 完成项\n", encoding="utf-8")
    spec = change_dir / "specs" / "web-ui" / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("## ADDED Requirements\n\n### Requirement: X\n\nX.\n", encoding="utf-8")


def test_guard_blocks_code_write_without_grill_evidence(tmp_path):
    """issue #95：有 spec delta 的 change，写代码前无 grill 证据 → exit 2。"""
    _seed_grill_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")},
        },
    )

    assert result.returncode == 2
    assert "grill" in result.stderr.lower()


def test_guard_allows_code_write_with_grill_evidence(tmp_path):
    """issue #95：有 grill 证据（reviews/grill-design.md）→ 放行。"""
    _seed_grill_change(tmp_path)
    reviews = tmp_path / "openspec" / "changes" / "grill-change" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n- **决策**: x；理由: y；来源: run-1\n",
        encoding="utf-8",
    )

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")},
        },
    )

    assert result.returncode == 0


def test_guard_exempts_change_doc_writes(tmp_path):
    """issue #95：change 文档类写操作（design.md/specs/reviews）豁免，不触发 grill 门禁。"""
    _seed_grill_change(tmp_path)

    cases = [
        str(tmp_path / "openspec" / "changes" / "grill-change" / "design.md"),
        str(tmp_path / "openspec" / "changes" / "grill-change" / "specs" / "web-ui" / "spec.md"),
        str(tmp_path / "openspec" / "changes" / "grill-change" / "reviews" / "grill-design.md"),
    ]
    for path in cases:
        result = _run_guard(
            tmp_path,
            {"tool_name": "Write", "tool_input": {"file_path": path}},
        )
        assert result.returncode == 0, f"文档写操作不应被拦: {path}"


def test_guard_no_change_mapping_does_not_trigger(tmp_path):
    """issue #95：无法映射 change（无分支名、多 active）→ 门禁不触发。"""
    _seed_grill_change(tmp_path)
    _seed_grill_change(tmp_path, "other-change")

    # 分支名不是 <change-id>/<date>，多 active change → 门禁不触发（放行）
    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")},
        },
    )
    assert result.returncode == 0


# ── grill 用户确认门禁（grill-confirmation-gate）────────────────────────


def test_guard_blocks_code_write_with_unconfirmed_open_questions(tmp_path):
    """grill-confirmation-gate：grill-design.md 存在但 Open Question 未确认 → 拦代码写。"""
    _seed_grill_change(tmp_path)
    reviews = tmp_path / "openspec" / "changes" / "grill-change" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n- **决策**: x；理由: y；来源: run-1\n"
        "## Open Questions\n1. 问题一\n"
        "## User Confirmation\n- **Q1**: 用户答复：待确认；确认时间: 2026-08-02\n",
        encoding="utf-8",
    )

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "grill" in result.stderr.lower()


def test_guard_allows_code_write_when_open_questions_confirmed(tmp_path):
    """grill-confirmation-gate：grill-design.md 存在且 Open Question 已确认 → 放行。"""
    _seed_grill_change(tmp_path)
    reviews = tmp_path / "openspec" / "changes" / "grill-change" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n- **决策**: x；理由: y；来源: run-1\n"
        "## Open Questions\n1. 问题一\n"
        "## User Confirmation\n- **Q1**: 用户答复：做 A；确认时间: 2026-08-02\n",
        encoding="utf-8",
    )

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 0


def test_guard_grill_evidence_extraction_parity_with_checker(tmp_path):
    """grill-confirmation-gate Decision 4：workflow_guard 与 checker 提取规则一致。"""
    import scripts.workflow_guard as wg
    from scripts.check_openspec_artifacts import (
        _extract_open_question_indexes as ck_open,
        _extract_user_confirmation_indexes as ck_confirm,
    )

    fixtures = [
        (
            "## Open Questions\n1. a\n2. b\n"
            "## User Confirmation\n- **Q1**: 用户答复：x；确认时间: t\n- **Q2**: 用户答复：y；确认时间: t\n",
            ["Q1", "Q2"],
            ["Q1", "Q2"],
        ),
        (
            "## Open Questions\n- 无\n",
            [],
            [],
        ),
        (
            "## Open Questions\n- **Q1**: a\n- **Q3**: c\n"
            "## User Confirmation\n- **Q1**: 用户答复：待确认；确认时间: t\n- **Q3**: 用户答复：ok；确认时间: t\n",
            ["Q1", "Q3"],
            ["Q3"],  # Q1 是未确认占位，不计入
        ),
    ]
    for text, exp_open, exp_confirm in fixtures:
        assert ck_open(text) == exp_open, text
        assert ck_confirm(text) == exp_confirm, text
        assert wg._extract_open_question_indexes(text) == exp_open, text
        assert wg._extract_user_confirmation_indexes(text) == exp_confirm, text


# ── awaiting gate（flow-event-projection P1）────────────────────────────


def _seed_awaiting_change(tmp_path: Path, *, awaiting=True, with_state=True, with_proposal=True) -> Path:
    """Seed a gen-2 change whose projection is (or is not) in awaiting state."""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    if with_proposal:
        (change_dir / "proposal.md").write_text(
            "## Change Type\n\nprimary: feature\n", encoding="utf-8"
        )
    events = [
        {"schema": "workflow-event/v1", "seq": 1, "event_type": "change_created", "change_id": "test-change"},
    ]
    if awaiting:
        events.append(
            {
                "schema": "workflow-event/v1",
                "seq": 2,
                "event_type": "blocked_entered",
                "change_id": "test-change",
                "transition": {
                    "from": {"phase": "planning", "sub_state": "writing_design"},
                    "to": {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
                    "trigger": "auto",
                },
                "blocker": {
                    "blocked_from": {"phase": "planning", "sub_state": "writing_design"},
                    "reason": "proposal done",
                },
            }
        )
    with (change_dir / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    if with_state:
        state = (
            {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"}
            if awaiting
            else {"phase": "planning", "sub_state": "exploring"}
        )
        ws = {
            "schema": "workflow-state/v1",
            "change_id": "test-change",
            "state": state,
            "milestones": [],
            "source_event_seq": len(events),
        }
        (change_dir / "workflow-state.json").write_text(
            json.dumps(ws, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return change_dir


def test_guard_blocks_write_when_awaiting(tmp_path):
    _seed_awaiting_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_blocks_write_when_awaiting_despite_missing_projection(tmp_path):
    """事件已 awaiting、磁盘无投影 → 仍拦截（不因投影缺失放行）。"""
    _seed_awaiting_change(tmp_path, with_state=False)

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_blocks_write_when_awaiting_despite_stale_projection(tmp_path):
    """building-review Issue 2：事件已 awaiting、磁盘 stale → 仍拦截（fail-closed）。"""
    _seed_awaiting_change(tmp_path)
    ws_path = tmp_path / "openspec" / "changes" / "test-change" / "workflow-state.json"
    ws = json.loads(ws_path.read_text(encoding="utf-8"))
    ws["source_event_seq"] = 99  # 人为过期
    ws_path.write_text(json.dumps(ws, indent=2, ensure_ascii=False), encoding="utf-8")

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_blocks_write_when_events_awaiting_but_disk_stale_non_awaiting(tmp_path):
    """building-review Issue 2 具体场景：磁盘 stale 且显示非 awaiting，但事件已 blocked_entered。"""
    _seed_awaiting_change(tmp_path)
    ws_path = tmp_path / "openspec" / "changes" / "test-change" / "workflow-state.json"
    ws = json.loads(ws_path.read_text(encoding="utf-8"))
    ws["state"] = {"phase": "planning", "sub_state": "exploring"}  # 磁盘显示非 awaiting
    ws["source_event_seq"] = 1  # stale
    ws_path.write_text(json.dumps(ws, indent=2, ensure_ascii=False), encoding="utf-8")

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_blocks_write_when_awaiting_despite_corrupt_projection(tmp_path):
    """事件已 awaiting、磁盘投影损坏 → 仍拦截（不因投影损坏放行）。"""
    _seed_awaiting_change(tmp_path)
    ws_path = tmp_path / "openspec" / "changes" / "test-change" / "workflow-state.json"
    ws_path.write_text("{not valid json", encoding="utf-8")

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_allows_write_for_non_awaiting_change_without_projection(tmp_path):
    """building-review Issue 3：无投影的非 awaiting gen-0 change 不被误拦（不额外误拦）。"""
    change_dir = tmp_path / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        "## Change Type\n\nprimary: feature\n", encoding="utf-8"
    )
    with (change_dir / "workflow-events.jsonl").open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "schema": "workflow-event/v1",
                    "seq": 1,
                    "event_type": "backlog_updated",
                    "change_id": "test-change",
                    "artifact_path": "docs/x.md",
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 0


def test_guard_blocks_bash_write_when_awaiting(tmp_path):
    """building-review Issue 1：awaiting 期间 Bash 写代码文件被拦（红线 1 不可经 Bash 绕过）。"""
    _seed_awaiting_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": "echo code > agent/foo.py"}},
    )

    assert result.returncode == 2
    assert "awaiting" in result.stderr


def test_guard_allows_bash_read_when_awaiting(tmp_path):
    """awaiting 期间只读 Bash 放行。"""
    _seed_awaiting_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {"tool_name": "Bash", "tool_input": {"command": "git status"}},
    )

    assert result.returncode == 0


def test_guard_allows_write_when_not_awaiting(tmp_path):
    _seed_awaiting_change(tmp_path, awaiting=False)

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "agent" / "feature.py")}},
    )

    assert result.returncode == 0


def test_guard_allows_change_doc_writes_during_awaiting(tmp_path):
    _seed_awaiting_change(tmp_path)
    change_dir = tmp_path / "openspec" / "changes" / "test-change"

    result = _run_guard(
        tmp_path,
        {"tool_name": "Write", "tool_input": {"file_path": str(change_dir / "design.md")}},
    )

    assert result.returncode == 0


def test_guard_allows_flow_cli_commands(tmp_path):
    _seed_awaiting_change(tmp_path)

    for command in [
        "python3 scripts/workflow_state.py flow status --change test-change",
        "uv run python scripts/workflow_state.py flow block --change test-change --awaiting awaiting_human_review",
        "python3 scripts/workflow_state.py flow confirm --change test-change",
        "python3 scripts/workflow_state.py flow advance --change test-change --to writing_proposal",
    ]:
        result = _run_guard(
            tmp_path,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert result.returncode == 0, f"flow 命令应豁免: {command}"


def test_guard_blocks_flow_chain_hijack(tmp_path):
    _seed_awaiting_change(tmp_path)

    result = _run_guard(
        tmp_path,
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "python3 scripts/workflow_state.py flow status --change test-change "
                    "&& echo x > docs/known-debt.md"
                )
            },
        },
    )

    assert result.returncode == 2

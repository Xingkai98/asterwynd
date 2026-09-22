"""`workflow_state.py` CLI 测试（四阶段状态机退役后）。

保留的活路径：`flow status`、`artifact-event`、`review-manifest`、`policy-*`、
`disable`/`enable`/`resume-audit`。已删除的 legacy 子命令（`discover` / `current` /
`validate` / `spawn`）与 gate 家族（`flow approve` / `advance` / `block` / `confirm`）
的负向回归见文件末尾 `TestRemovedSubcommands`——它们必须以「未知子命令、非零退出、
无副作用」失败，而**不得**静默成功。
"""

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from agent.workflow.event_log import event_log_path, verify_handoff_projection
from agent.workflow.review_manifest import verify_review_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_STATE = REPO_ROOT / "scripts" / "workflow_state.py"

# 已随四阶段状态机退役删除的子命令（负向回归的判据来源）。
REMOVED_SUBCOMMANDS = (
    ("discover",),
    ("current", "--change", "test-change"),
    ("validate", "--change", "test-change"),
    ("spawn", "--from", "parent-map", "--changes", "child-a"),
    ("flow", "approve", "--change", "test-change", "--phase", "planning"),
    ("flow", "advance", "--change", "test-change", "--to", "writing_proposal"),
    ("flow", "block", "--change", "test-change", "--awaiting", "awaiting_proposal_confirmation"),
    ("flow", "confirm", "--change", "test-change"),
)


def _append_ev(change_dir, event_type, seq, change_id="test-change", **extra):
    event = {
        "schema": "workflow-event/v1",
        "seq": seq,
        "event_type": event_type,
        "change_id": change_id,
        **extra,
    }
    with (change_dir / "workflow-events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _tr(from_state, to_state, trigger="auto"):
    return {"from": from_state, "to": to_state, "trigger": trigger}


def _handoff_seed(change_id="test-change"):
    """等价于已删除的 `init_handoff_json(change_id)` 的字典形状（gen-1 首载荷）。"""
    return {
        "schema_version": "1.0",
        "change_id": change_id,
        "state": {"phase": "planning", "sub_state": "exploring"},
        "transitions": [],
        "current_agent": None,
        "last_gate": None,
        "blockers": [],
        "routing": {},
        "next_hints": {},
    }


def _seed_gen1_change(tmp_path, change_id="test-change"):
    """老世代（gen-1）change：`initialized` 首事件 + 同步 handoff.json 投影。

    原实现用 `WorkflowManager(...).init()`（已随四阶段状态机退役删除）。
    """
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    _append_ev(change_dir, "initialized", 1, change_id, handoff=_handoff_seed(change_id))
    (change_dir / "handoff.json").write_text(
        json.dumps(_handoff_seed(change_id), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return change_dir


def _seed_gen2_change(tmp_path, change_id="test-change"):
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    _append_ev(change_dir, "change_created", 1, change_id)
    return change_dir


def _run_cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(WORKFLOW_STATE), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


# ── 活路径：flow status ────────────────────────────────────────────────


def test_flow_status_outputs_json_and_self_heals_stale(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    _append_ev(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")
    # 先写一个 stale 投影
    (change_dir / "workflow-state.json").write_text(
        json.dumps(
            {
                "schema": "workflow-state/v1",
                "change_id": "test-change",
                "state": {"phase": "building", "sub_state": "writing_tests"},
                "milestones": [],
                "source_event_seq": 99,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_cli(tmp_path, "flow", "status", "--change", "test-change")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["state"] == {"phase": "planning", "sub_state": "exploring"}
    assert output["source_event_seq"] == 2
    assert output["stale"] is True
    # 自愈重建：磁盘投影已刷新
    disk = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
    assert disk["source_event_seq"] == 2


def test_flow_status_self_heal_does_not_write_handoff_json(tmp_path):
    """#228 层 1 判别性：自愈只写 workflow-state.json，**不再**产出 handoff.json。

    去掉层 1 改动（恢复 `_refresh_workflow_state` 的 handoff 映射写）→ 本用例变红。
    """
    change_dir = _seed_gen2_change(tmp_path)
    _append_ev(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")

    result = _run_cli(tmp_path, "flow", "status", "--change", "test-change")

    assert result.returncode == 0
    assert (change_dir / "workflow-state.json").exists()
    assert not (change_dir / "handoff.json").exists()


def test_flow_status_all_lists_contemporary_changes(tmp_path):
    _seed_gen2_change(tmp_path, "modern-change")
    # 老世代 change（handoff.json 驱动）
    _seed_gen1_change(tmp_path, "legacy-change")

    result = _run_cli(tmp_path, "flow", "status", "--all")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "modern-change" in output
    assert "legacy-change" in output


def test_flow_status_archived_change_readonly(tmp_path):
    """归档 change 可查询（用户故事：老 change 也能 flow status），只读不落盘。"""
    archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-08-09-old-change"
    archive_dir.mkdir(parents=True)
    _append_ev(archive_dir, "change_created", 1, "old-change")
    _append_ev(archive_dir, "grill_completed", 2, "old-change")

    result = _run_cli(tmp_path, "flow", "status", "--change", "2026-08-09-old-change")

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["change_id"] == "old-change"
    assert output["milestones"] == ["grill_completed"]
    assert not (archive_dir / "workflow-state.json").exists()


def test_flow_status_requires_change_or_all(capsys):
    import scripts.workflow_state as mod

    result = mod.cmd_flow_status(Namespace(change=None, all=False))
    output = capsys.readouterr()

    assert result == 1
    assert "需要 --change" in output.err


# ── 活路径：受保护写通道 ───────────────────────────────────────────────


def test_artifact_event_command_appends_event_without_touching_handoff(tmp_path):
    change_dir = _seed_gen1_change(tmp_path)
    handoff_before = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    result = _run_cli(
        tmp_path,
        "artifact-event",
        "--change",
        "test-change",
        "--event-type",
        "protected_artifact_explained",
        "--artifact-path",
        "docs/known-debt.md",
        "--reason",
        "documented debt entry updated through the workflow gate",
        "--approved-by",
        "human-1",
    )

    event_log = event_log_path(change_dir).read_text(encoding="utf-8")
    handoff_after = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert '"event_type": "protected_artifact_explained"' in event_log
    assert '"artifact_path": "docs/known-debt.md"' in event_log
    # gen-1 目标：写通道刷新其唯一投影载体 handoff.json（不是 #228 说的 gen-2 映射写）
    assert handoff_after == handoff_before
    assert verify_handoff_projection(change_dir) == []


def test_review_manifest_command_writes_manifest(tmp_path):
    change_dir = _seed_gen1_change(tmp_path)

    review_dir = change_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("- [x] cover the path\n", encoding="utf-8")
    (change_dir / "specs").mkdir(parents=True, exist_ok=True)

    result = _run_cli(
        tmp_path,
        "review-manifest",
        "--change",
        "test-change",
        "--phase",
        "building",
        "--reviewer-run-id",
        "reviewer-1",
        "--base-sha",
        "base-sha",
        "--head-sha",
        "head-sha",
    )

    manifest_path = review_dir / "building-review-manifest.json"

    assert result.returncode == 0
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["reviewer_run_id"] == "reviewer-1"
    assert manifest["phase"] == "building"
    assert verify_review_manifest(tmp_path, "test-change", "building") == []


# ── 负向回归：已删除的子命令必须明确报错、非零退出、无副作用 ──────────────


class TestRemovedSubcommands:
    """每个已删子命令 → argparse 未知子命令，非零退出，且不产生任何副作用。

    判别性：这些用例在「子命令被恢复」时会变红（恢复到会静默成功的旧行为更红）——
    静默成功比「命令消失」更坏，故不只断言「报错」，还断言「无事件/无投影落盘」。
    """

    def test_removed_subcommands_are_unknown(self, tmp_path):
        _seed_gen2_change(tmp_path)
        for args in REMOVED_SUBCOMMANDS:
            result = _run_cli(tmp_path, *args)
            combined = result.stderr + result.stdout
            assert result.returncode != 0, f"{args} 不应成功：{combined}"
            assert "invalid choice" in combined, f"{args} 应报未知子命令：{combined}"

    def test_removed_flow_subcommands_report_unknown(self, tmp_path):
        """`flow` 组仍存在（保留 status），但 gate 家族成员必须是未知子命令。"""
        _seed_gen2_change(tmp_path)
        for sub in ("approve", "advance", "block", "confirm"):
            result = _run_cli(tmp_path, "flow", sub, "--change", "test-change")
            combined = result.stderr + result.stdout
            assert result.returncode != 0, f"flow {sub} 不应成功：{combined}"
            assert "invalid choice" in combined, f"flow {sub} 应报未知子命令：{combined}"

    def test_removed_subcommands_have_no_side_effects(self, tmp_path):
        """失败不得留下事件或投影（对照旧 `flow approve` 会写 transition_applied）。"""
        change_dir = _seed_gen2_change(tmp_path)
        events_before = event_log_path(change_dir).read_text(encoding="utf-8")

        for args in REMOVED_SUBCOMMANDS:
            _run_cli(tmp_path, *args)

        assert event_log_path(change_dir).read_text(encoding="utf-8") == events_before
        assert not (change_dir / "workflow-state.json").exists()
        assert not (change_dir / "handoff.json").exists()
        # 未派生任何子 change 目录
        assert not (tmp_path / "openspec" / "changes" / "child-a").exists()

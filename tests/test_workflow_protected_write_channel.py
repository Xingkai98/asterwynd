"""fix-issue-199：受保护写通道解除 handoff.json 前置的回归测试。

**冷状态构造约束（本文件所有用例必须遵守，D4b）**：

1. 种子方式：直接向 `workflow-events.jsonl` 落盘 `change_created` 首事件，
   **不得**用会使 change 变成 gen-1 的种子（写 `initialized` 首事件 + 生成
   `handoff.json`）——旧实现（硬前置 `handoff.json`）会把它判为合法，测试因此
   **恒绿**，失去判别力。
2. 调用 CLI 前断言目标目录**没有** `handoff.json`，确保测试跑在冷状态。
3. **层 1 之后（issue #228）**：`flow status` 的 stale 自愈
   （`workflow_state.py:_flow_status_projection` → `_refresh_workflow_state`）
   **不再**产出 `handoff.json`——故原「用例内不得先跑 flow status」的顺序约束
   已无理由。判别点改为**调用后**断言：自愈只落 `workflow-state.json`、
   绝不落 `handoff.json`（见各用例的 post-call 断言与
   `test_flow_status_self_heal_does_not_write_handoff_json`）。去掉层 1 改动
   → 这些 post-call 断言变红。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agent.workflow.event_log import event_log_path, verify_projection
from agent.workflow.review_manifest import verify_review_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_STATE = REPO_ROOT / "scripts" / "workflow_state.py"

PROPOSAL_TEXT = "# Proposal\n"


def _seed_gen2_change(tmp_path, change_id="test-change", *, proposal=True):
    """当代（gen-2）change 冷状态种子：目录 + `change_created` 首事件（+ proposal.md）。

    刻意**不用** `WorkflowManager.init()`：那会写 `initialized` 首事件与
    `handoff.json`，把用例变成 gen-1 而恒绿（见模块 docstring）。
    """
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    if proposal:
        (change_dir / "proposal.md").write_text(PROPOSAL_TEXT, encoding="utf-8")
    (change_dir / "workflow-events.jsonl").write_text(
        json.dumps(
            {
                "schema": "workflow-event/v1",
                "seq": 1,
                "event_type": "change_created",
                "change_id": change_id,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return change_dir


def _handoff_seed(change_id="legacy-change"):
    """gen-1 首载荷字典（等价已删除的 `init_handoff_json(change_id)`，纯构造不落盘）。"""
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


def _seed_gen1_change(tmp_path, change_id="legacy-change", *, proposal=True, handoff=True):
    """老世代（gen-1）change 冷状态种子：`initialized` 首事件 + 可选 handoff.json。

    `initialized` 事件必须内嵌 `handoff` 载荷（`replay_handoff_projection` 从
    `first["handoff"]` 起 replay），故用 `_handoff_seed` 造等价字典（纯构造，不落盘）。
    """
    change_dir = tmp_path / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True)
    if proposal:
        (change_dir / "proposal.md").write_text(PROPOSAL_TEXT, encoding="utf-8")
    handoff_data = _handoff_seed(change_id)
    (change_dir / "workflow-events.jsonl").write_text(
        json.dumps(
            {
                "schema": "workflow-event/v1",
                "seq": 1,
                "event_type": "initialized",
                "change_id": change_id,
                "handoff": handoff_data,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if handoff:
        (change_dir / "handoff.json").write_text(
            json.dumps(handoff_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return change_dir


def _seed_review_artifacts(change_dir):
    review_dir = change_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "building-review.md").write_text("## Review\n\nPASS\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    (change_dir / "specs").mkdir(parents=True, exist_ok=True)
    return review_dir


def _run_cli(cwd, *args):
    return subprocess.run(
        [sys.executable, str(WORKFLOW_STATE), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _artifact_event_args(change_id, event_type="protected_artifact_explained"):
    return (
        "artifact-event",
        "--change",
        change_id,
        "--event-type",
        event_type,
        "--artifact-path",
        "docs/known-debt.md",
        "--reason",
        "regression coverage for issue 199 protected write channel",
        "--approved-by",
        "human-1",
    )


def _review_manifest_args(change_id):
    return (
        "review-manifest",
        "--change",
        change_id,
        "--phase",
        "building",
        "--reviewer-run-id",
        "reviewer-199",
        "--base-sha",
        "base-sha",
        "--head-sha",
        "head-sha",
    )


# --- 当代 change（无 handoff.json）：本 bug 的核心症状 -------------------------


def test_artifact_event_works_without_handoff_json(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    # 冷状态：确认没有自愈产物，否则本用例会因旧前置而假绿
    assert not (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("test-change"))

    assert result.returncode == 0, result.stderr
    log = event_log_path(change_dir).read_text(encoding="utf-8")
    assert '"event_type": "protected_artifact_explained"' in log
    assert '"artifact_path": "docs/known-debt.md"' in log
    # 层 1 判别性（post-call）：写通道只落 workflow-state.json，绝不落 handoff.json
    assert (change_dir / "workflow-state.json").exists()
    assert not (change_dir / "handoff.json").exists()


def test_review_manifest_works_without_handoff_json(tmp_path):
    change_dir = _seed_gen2_change(tmp_path)
    review_dir = _seed_review_artifacts(change_dir)
    assert not (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_review_manifest_args("test-change"))

    assert result.returncode == 0, result.stderr
    manifest_path = review_dir / "building-review-manifest.json"
    assert manifest_path.exists()
    assert verify_review_manifest(tmp_path, "test-change", "building") == []
    # D7 同样覆盖 review-manifest 这条命令：写入后投影即新鲜（删除该刷新会让本断言变红）
    assert (change_dir / "workflow-state.json").exists()
    assert verify_projection(change_dir) == []


def test_artifact_event_refreshes_projection_without_flow_status(tmp_path):
    """D7：写入后投影即新鲜，checker 可立即校验（不需要先跑 flow status）。"""
    change_dir = _seed_gen2_change(tmp_path)
    assert not (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("test-change"))

    assert result.returncode == 0, result.stderr
    assert (change_dir / "workflow-state.json").exists()
    assert verify_projection(change_dir) == []
    # 层 1 判别性（post-call）：自愈不再凭空写出 handoff.json
    assert not (change_dir / "handoff.json").exists()


# --- 老世代兼容：行为不变 -----------------------------------------------------


def test_artifact_event_still_works_for_gen1_change(tmp_path):
    change_dir = _seed_gen1_change(tmp_path)
    assert (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("legacy-change"))

    assert result.returncode == 0, result.stderr
    assert '"event_type": "protected_artifact_explained"' in event_log_path(change_dir).read_text(
        encoding="utf-8"
    )


def test_review_manifest_still_works_for_gen1_change(tmp_path):
    change_dir = _seed_gen1_change(tmp_path)
    review_dir = _seed_review_artifacts(change_dir)

    result = _run_cli(tmp_path, *_review_manifest_args("legacy-change"))

    assert result.returncode == 0, result.stderr
    assert (review_dir / "building-review-manifest.json").exists()


def test_spawn_style_child_without_proposal_still_writable(tmp_path):
    """Q1 兼容分支：历史 spawn 子 change 只有 handoff.json，没有 proposal.md。

    锚点若只认 `proposal.md`，这类老目标会从「可写」退化为 exit 1。
    （`cmd_spawn` 本身已随四阶段状态机退役删除，但归档/历史目录里仍可能存在这类目标。）
    """
    change_dir = _seed_gen1_change(tmp_path, change_id="child-b", proposal=False)
    assert not (change_dir / "proposal.md").exists()
    assert (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("child-b"))

    assert result.returncode == 0, result.stderr


# --- 非法目标仍拒绝：不退化为「任意路径都能写」 --------------------------------


def test_artifact_event_rejects_unknown_change(tmp_path):
    result = _run_cli(tmp_path, *_artifact_event_args("no-such-change"))

    assert result.returncode == 1
    # 断言失败来自目标检查本身（而非其它副作用），保证用例对「前置被删」有判别力
    assert "不存在" in result.stderr


def test_review_manifest_rejects_unknown_change(tmp_path):
    result = _run_cli(tmp_path, *_review_manifest_args("no-such-change"))

    assert result.returncode == 1
    # 同上：若前置被删，失败会退化为 `review report missing`，本断言即变红
    assert "不存在" in result.stderr


def test_artifact_event_rejects_dir_without_proposal_or_handoff(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "empty-dir"
    change_dir.mkdir(parents=True)

    result = _run_cli(tmp_path, *_artifact_event_args("empty-dir"))

    assert result.returncode == 1
    assert "不是合法 change" in result.stderr
    assert not (change_dir / "workflow-events.jsonl").exists()


def test_artifact_event_rejects_path_bearing_change_id(tmp_path):
    """R2 审阅 New-1：`--change` 传绝对路径 / 含分隔符的 id 必须被明确拒绝。

    否则 `CHANGES_ROOT / change_id` 对绝对路径整体替换根（可写到仓库外），对含
    `/` 的相对路径会解析到子目录，而下游按 `change_dir.name` 重拼路径
    （`_save_handoff`）会在不存在的父目录上抛裸 FileNotFoundError traceback。
    """
    nested = tmp_path / "openspec" / "changes" / "group" / "leg"
    nested.mkdir(parents=True)
    (nested / "proposal.md").write_text(PROPOSAL_TEXT, encoding="utf-8")
    (nested / "handoff.json").write_text("{}", encoding="utf-8")

    for bad_id in ("group/leg", str(nested)):
        for args in (_artifact_event_args(bad_id), _review_manifest_args(bad_id)):
            result = _run_cli(tmp_path, *args)
            assert result.returncode == 1, f"{args[0]} {bad_id!r} 应被拒绝"
            assert "非法" in result.stderr, f"{args[0]} {bad_id!r} 应有明确错误文案，实际: {result.stderr!r}"
            assert "Traceback" not in result.stderr, f"{args[0]} {bad_id!r} 不应抛裸 traceback"


def test_review_manifest_rejects_dir_without_proposal_or_handoff(tmp_path):
    change_dir = tmp_path / "openspec" / "changes" / "empty-dir"
    change_dir.mkdir(parents=True)

    result = _run_cli(tmp_path, *_review_manifest_args("empty-dir"))

    assert result.returncode == 1
    assert "不是合法 change" in result.stderr
    assert not (change_dir / "reviews").exists()

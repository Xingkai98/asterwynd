"""fix-issue-232（盲区 A）：受保护写通道支持已归档 change 的回归测试。

#199 收口了写通道的**前置条件**，但没管**目标解析**：归档 change 跑
`artifact-event` / `review-manifest` 报「不存在」exit 1，收尾时只能绕底层函数。

**冷状态构造约束（同 `test_workflow_protected_write_channel.py`）**：

1. 种子直接向 `workflow-events.jsonl` 落盘 `change_created`（当代）首事件，
   **不得**用 `WorkflowManager(...).init()`——它写 `initialized` 首事件 + `handoff.json`，
   得到 gen-1 change，会让判别力失效。
2. 调用 CLI 前断言目标目录**没有** `handoff.json`。
3. 用例内**不得**先跑 `flow status`：其 stale 自愈会凭空写出投影文件，顺序依赖地掩盖问题。
4. 归档用例全部在 `tmp_path` 内构造 `openspec/changes/archive/<date>-<id>/`，
   绝不触碰真实仓库的 archive 目录。
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
ARCHIVE_DATE = "2026-09-21"
HOLLOW_PROJECTIONS = ("handoff.json", "workflow-state.json")


def _seed_change(tmp_path, rel_dir, change_id):
    """在 `rel_dir` 下造一个当代（gen-2）change 冷状态：目录 + proposal.md + `change_created`。

    刻意**不用** `WorkflowManager.init()`（见模块 docstring），也不用
    `flow status`（自愈会写投影）。`rel_dir` 允许点进 archive 子目录。
    """
    change_dir = tmp_path / rel_dir
    change_dir.mkdir(parents=True)
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


def _seed_archived_change(tmp_path, change_id="archived-change", *, date=ARCHIVE_DATE, dir_name=None):
    """归档 change 冷状态：`openspec/changes/archive/<date>-<id>/`（active 目录不存在）。"""
    name = dir_name or f"{date}-{change_id}"
    return _seed_change(tmp_path, Path("openspec") / "changes" / "archive" / name, change_id)


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
        "regression coverage for issue 232 archive write channel",
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
        "reviewer-232",
        "--base-sha",
        "base-sha",
        "--head-sha",
        "head-sha",
    )


def _active_dir(tmp_path, change_id):
    return tmp_path / "openspec" / "changes" / change_id


# --- 归档写通道：本 bug 的核心症状 -------------------------------------------


def test_artifact_event_works_for_archived_change(tmp_path):
    change_dir = _seed_archived_change(tmp_path)
    assert not (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("archived-change"))

    assert result.returncode == 0, result.stderr
    log = event_log_path(change_dir).read_text(encoding="utf-8")
    assert '"event_type": "protected_artifact_explained"' in log
    assert '"artifact_path": "docs/known-debt.md"' in log
    # 事件必须落在**归档目录**的事件日志里（判别性：去掉 archive 回退 → exit 1）
    assert not (tmp_path / "openspec" / "changes" / "archived-change" / "workflow-events.jsonl").exists()


def test_review_manifest_works_for_archived_change(tmp_path):
    change_dir = _seed_archived_change(tmp_path)
    review_dir = _seed_review_artifacts(change_dir)
    assert not (change_dir / "handoff.json").exists()

    result = _run_cli(tmp_path, *_review_manifest_args("archived-change"))

    assert result.returncode == 0, result.stderr
    manifest_path = review_dir / "building-review-manifest.json"
    assert manifest_path.exists()
    assert verify_review_manifest(tmp_path, "archived-change", "building", archived=True) == []


# --- 污染判别：归档目录不得出现投影文件、active 路径不得被新建 -----------------


def test_archived_write_does_not_pollute_archive_dir(tmp_path):
    """判别性：移除「归档跳过刷新」→ 归档目录凭空多出 handoff.json + workflow-state.json。"""
    change_dir = _seed_archived_change(tmp_path)
    _seed_review_artifacts(change_dir)

    for args in (_artifact_event_args("archived-change"), _review_manifest_args("archived-change")):
        result = _run_cli(tmp_path, *args)
        assert result.returncode == 0, result.stderr

    for name in HOLLOW_PROJECTIONS:
        assert not (change_dir / name).exists(), f"归档目录不应出现 {name}"


def test_archived_write_does_not_create_active_ghost_dir(tmp_path):
    """判别性：不传 `archived=` 透传时 manifest 会落到 active 路径（报错误导）。"""
    change_dir = _seed_archived_change(tmp_path)
    _seed_review_artifacts(change_dir)

    result = _run_cli(tmp_path, *_review_manifest_args("archived-change"))

    assert result.returncode == 0, result.stderr
    assert not _active_dir(tmp_path, "archived-change").exists()
    assert not _active_dir(tmp_path, "archived-change").is_symlink()


def test_archived_write_supports_bare_id_archive_dir(tmp_path):
    """归档目录名为**裸 `<id>`**（无日期前缀）时同样可写。

    覆盖 `_archive_dir_matches_change_id` 与 `change_dir_for` 的 `name == change_id`
    分支——否则该分支无测试执行（审阅 O2-①）。
    """
    change_dir = _seed_archived_change(tmp_path, change_id="bare-dir", dir_name="bare-dir")
    assert change_dir.name == "bare-dir"

    result = _run_cli(tmp_path, *_artifact_event_args("bare-dir"))

    assert result.returncode == 0, result.stderr
    assert '"event_type": "protected_artifact_explained"' in event_log_path(change_dir).read_text(
        encoding="utf-8"
    )
    for name in HOLLOW_PROJECTIONS:
        assert not (change_dir / name).exists()


def test_archived_write_supports_gen1_change_with_only_handoff(tmp_path):
    """归档的**老世代** change（只有 `handoff.json`，无 `proposal.md`）仍可写。

    对应 spec 既有 Scenario「老世代 change 的受保护写通道保持可用」在归档语境的延伸
    （审阅 O2-②）：#199 的 handoff 兼容分支不得因归档回退而失效。
    """
    change_dir = tmp_path / "openspec" / "changes" / "archive" / f"{ARCHIVE_DATE}-legacy-arch"
    change_dir.mkdir(parents=True)
    handoff = {"schema_version": "1.0", "change_id": "legacy-arch", "state": {}, "transitions": []}
    (change_dir / "handoff.json").write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
    handoff_before = (change_dir / "handoff.json").read_text(encoding="utf-8")
    assert not (change_dir / "proposal.md").exists()

    result = _run_cli(tmp_path, *_artifact_event_args("legacy-arch"))

    assert result.returncode == 0, result.stderr
    assert '"event_type": "protected_artifact_explained"' in event_log_path(change_dir).read_text(
        encoding="utf-8"
    )
    # 归档跳过刷新：handoff.json 不得被 replay 改写，也不得新增投影
    assert (change_dir / "handoff.json").read_text(encoding="utf-8") == handoff_before
    assert not (change_dir / "workflow-state.json").exists()


def test_archived_write_rejects_unknown_change(tmp_path):
    """审阅 O2-③：归档语境下不存在的 id 仍 exit 1（不退化为「任意 id 都能写」）。"""
    _seed_archived_change(tmp_path)

    for args in (
        _artifact_event_args("no-such-archived-change"),
        _review_manifest_args("no-such-archived-change"),
    ):
        result = _run_cli(tmp_path, *args)
        assert result.returncode == 1
        assert "不存在" in result.stderr
        assert "Traceback" not in result.stderr


# --- 归档目标契约：日期前缀 id / 解析一致性 -----------------------------------


def test_artifact_event_rejects_date_prefixed_change_id(tmp_path):
    """Q4：带 `<date>-` 前缀的 id 会让写入的 change_id 触发 CI `change_id mismatch`。"""
    change_dir = _seed_archived_change(tmp_path)

    result = _run_cli(tmp_path, *_artifact_event_args(f"{ARCHIVE_DATE}-archived-change"))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    # 不得写入任何文件（事件日志保持首事件原样）
    log = event_log_path(change_dir).read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 1


def test_review_manifest_rejects_date_prefixed_change_id(tmp_path):
    change_dir = _seed_archived_change(tmp_path)
    _seed_review_artifacts(change_dir)

    result = _run_cli(tmp_path, *_review_manifest_args(f"{ARCHIVE_DATE}-archived-change"))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert not (change_dir / "reviews" / "building-review-manifest.json").exists()


def test_archived_resolution_rejects_longer_prefixed_sibling(tmp_path):
    """Q2：`change_dir_for` 的 `re.match` 无 `$`，查询 `alpha` 会命中 `alpha-beta`。

    判别性：移除解析一致性断言后，`artifact-event --change alpha` 会把事件**写进
    `alpha-beta`**（另一个 change）并 exit 0——静默污染。

    构造刻意只留**唯一候选**目录 `2026-09-22-alpha-beta`（不存在叫 `alpha` 的 change），
    使 `change_dir_for` 的命中不依赖 `iterdir()` 顺序（顺序依赖会让用例在别的环境假绿）。
    """
    sibling = _seed_archived_change(tmp_path, change_id="alpha-beta", date="2026-09-22")
    _seed_review_artifacts(sibling)

    for args in (_artifact_event_args("alpha"), _review_manifest_args("alpha")):
        result = _run_cli(tmp_path, *args)
        assert result.returncode == 1, f"{args[0]}: 不应把写入落到另一个 change 的目录"
        assert not (sibling / "reviews" / "building-review-manifest.json").exists()

    # 兄弟目录的事件日志必须保持原样（只有种子首事件）
    lines = event_log_path(sibling).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


# --- 只读投影校验（Q3）：一致不告警、不一致告警但 exit 0 ----------------------


def test_archived_write_makes_no_projection_warning_when_consistent(tmp_path):
    change_dir = _seed_archived_change(tmp_path)
    assert verify_projection(change_dir) == []

    result = _run_cli(tmp_path, *_artifact_event_args("archived-change"))

    assert result.returncode == 0, result.stderr
    assert "警告" not in result.stderr
    for name in HOLLOW_PROJECTIONS:
        assert not (change_dir / name).exists()


def test_archived_write_warns_on_stale_committed_projection(tmp_path):
    """归档目录**已提交** `workflow-state.json` 时，跳过刷新会让投影永久 stale。

    现实对应：`openspec/changes/archive/2026-08-15-flow-event-projection/`（仓库唯一）。
    期望：只读校验发现不一致 → stderr 告警，但 **exit 0** 且**不落盘改写**投影。
    """
    change_dir = _seed_archived_change(tmp_path)
    # 造一个陈旧投影：与当前事件 replay 不一致
    (change_dir / "workflow-state.json").write_text(
        json.dumps({"schema": "workflow-state/v1", "state": {"phase": "done"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    stale_before = (change_dir / "workflow-state.json").read_text(encoding="utf-8")

    result = _run_cli(tmp_path, *_artifact_event_args("archived-change"))

    assert result.returncode == 0, result.stderr
    assert "警告" in result.stderr
    # 只读：投影文件内容不得被改写
    assert (change_dir / "workflow-state.json").read_text(encoding="utf-8") == stale_before


# --- 归档语境下的既有拒绝行为保持 ---------------------------------------------


def test_archived_write_rejects_path_bearing_change_id(tmp_path):
    _seed_archived_change(tmp_path)
    nested = tmp_path / "openspec" / "changes" / "archive" / "group"
    nested.mkdir(parents=True)

    for bad_id in ("group/x", str(nested)):
        result = _run_cli(tmp_path, *_artifact_event_args(bad_id))
        assert result.returncode == 1, f"归档语境下 {bad_id!r} 应被拒绝"
        assert "非法" in result.stderr
        assert "Traceback" not in result.stderr


def test_archived_write_rejects_archived_dir_without_proposal_or_handoff(tmp_path):
    """archive 下的非 change 目录（无 proposal/handoff）仍不得成为写入目标。"""
    empty = tmp_path / "openspec" / "changes" / "archive" / f"{ARCHIVE_DATE}-empty-dir"
    empty.mkdir(parents=True)

    result = _run_cli(tmp_path, *_artifact_event_args("empty-dir"))

    assert result.returncode == 1
    assert "不是合法 change" in result.stderr
    assert not (empty / "workflow-events.jsonl").exists()

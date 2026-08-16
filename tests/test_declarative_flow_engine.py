"""declarative-flow-engine（P4，issue #141）测试套件。

覆盖 tasks 2.1-2.7：
- 2.1 statechart 合法性测试（结构校验 + parity 交叉校验）
- 2.2 parity 测试（复用 test_event_log / test_workflow_state_cli 事件 fixture，
      断言完整投影 dict + 逐态 legal_targets / can_transition 等价；gen-2 only）
- 2.3 演示测试（fixture 注入 awaiting_design_confirmation；提交 statechart 不含演示态）
- 2.4 workflow_methods 兼容测试（不删 phase/sub_state 段）
- 2.5 e2e 1：引擎 CLI 冒烟（真实归档 change 事件文件）
- 2.6 e2e 2：真实生命周期（flow block → confirm → advance → 归档）
- 2.7 e2e 3：演示集成（注入新态后引擎驱动 flow 生命周期）

演示态 ``awaiting_design_confirmation`` 只在测试内注入，不进提交的 statechart（Q1/Q6）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent.workflow.event_log import (
    _read_events as python_read_events,
    project_workflow_state,
)
from agent.workflow.models import PHASE_SUB_STATES
from agent.workflow.state_machine import (
    StateMachineError,
    StateSnapshot,
    get_legal_targets,
    validate_transition,
)
from flow.engine import (
    DEFAULT_STATECHART_PATH,
    FlowEngine,
    FlowStatechart,
    StatechartError,
    parse_state,
    state_name,
)
from tests.agent.workflow.test_event_log import (
    _append_raw_event as el_append_raw_event,
    _seed_new_gen_change as el_seed_new_gen_change,
    _transition as el_transition,
)
from tests.test_workflow_state_cli import (
    _append_ev as cli_append_ev,
    _run_cli as cli_run_cli,
    _seed_gen2_change as cli_seed_gen2_change,
    _tr as cli_tr,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMITTED_STATECHART = REPO_ROOT / "flow" / "statechart.json"
ENGINE = REPO_ROOT / "flow" / "engine.py"
WORKFLOW_STATE_CLI = REPO_ROOT / "scripts" / "workflow_state.py"
ARCHIVE_PLATFORM_GATE_EVENTS = (
    REPO_ROOT / "openspec" / "changes" / "archive" / "2026-08-16-platform-gate" / "workflow-events.jsonl"
)


# ── 共享 helpers ─────────────────────────────────────────────────────


def _load_engine(statechart_path: Path | None = None) -> FlowEngine:
    return FlowEngine(FlowStatechart.load(statechart_path))


def _events_of(change_dir: Path) -> list[dict]:
    """读回 change_dir 的事件记录（含 schema/seq），供引擎派生与 parity 对比。"""
    return python_read_events(change_dir / "workflow-events.jsonl")


def _all_declared_states() -> list[str]:
    return list(FlowStatechart.load(SUBMITTED_STATECHART).states.keys())


# ── 2.1 statechart 合法性测试 ─────────────────────────────────────────


class TestStatechartValidity:
    def test_submitted_statechart_passes_validate(self):
        """提交的 statechart 结构 + parity 交叉校验全过（Q7：CI 拦截漂移）。"""
        engine = _load_engine()
        assert engine.validate() == []

    def test_validate_rejects_missing_initial(self):
        data = _base_statechart()
        del data["initial"]
        assert "missing initial" in _validate_errors(data)

    def test_validate_rejects_initial_undeclared(self):
        data = _base_statechart()
        data["initial"] = "planning.nonexistent"
        errors = _validate_errors(data)
        assert any("initial references undeclared state" in e for e in errors)

    def test_validate_rejects_transition_to_undeclared_state(self):
        data = _base_statechart()
        data["states"]["planning.exploring"]["on"] = [
            {"trigger": "auto", "to": "planning.nonexistent"}
        ]
        errors = _validate_errors(data)
        assert any("references undeclared state" in e for e in errors)

    def test_validate_rejects_invalid_trigger(self):
        data = _base_statechart()
        data["states"]["planning.exploring"]["on"] = [
            {"trigger": "bogus", "to": "planning.writing_proposal"}
        ]
        assert any("invalid trigger" in e for e in _validate_errors(data))

    def test_validate_rejects_orphan_state(self):
        data = _base_statechart()
        data["states"]["planning.flyaway"] = {"on": []}  # 无入边、非 initial、非豁免 phase
        errors = _validate_errors(data)
        assert any("orphan state" in e for e in errors)

    def test_validate_rejects_recovery_default_undeclared(self):
        data = _base_statechart()
        data["states"]["blocked.awaiting_proposal_confirmation"]["recovery_default"] = {
            "phase": "planning",
            "sub_state": "nonexistent",
        }
        assert any("recovery_default references undeclared state" in e for e in _validate_errors(data))

    def test_validate_parity_cross_check_rejects_python_illegal_transition(self):
        """声明了 Python 判非法的转移（跨 phase 非 gate 前进）→ parity 交叉校验报错。"""
        data = _base_statechart()
        data["states"]["planning.exploring"]["on"] = [
            {"trigger": "auto", "to": "building.writing_tests"}  # Python 拒绝：非 gate 跨 phase
        ]
        errors = _validate_errors(data)
        assert any("validate_transition rejects" in e for e in errors)

    def test_validate_accepts_blocked_awaiting_states(self):
        """blocked.awaiting_* 是合法状态（awaiting 建模），validate 不报 sub_state 错误。"""
        engine = _load_engine()
        assert engine.chart.awaiting_sub_states() == [
            "awaiting_proposal_confirmation",
            "awaiting_human_review",
            "awaiting_user_confirmation",
        ]

    def test_validate_rejects_done_sub_state(self):
        data = _base_statechart()
        data["states"]["done.something"] = {"on": []}
        with pytest.raises(StatechartError, match="done phase cannot declare sub_states"):
            FlowStatechart(data)


def _base_statechart() -> dict:
    return json.loads(SUBMITTED_STATECHART.read_text(encoding="utf-8"))


def _validate_errors(data: dict) -> list[str]:
    return FlowEngine(FlowStatechart(data)).validate()


# ── 2.2 parity 测试（gen-2 only，完整投影 + 逐态合法等价）──────────────


class TestParity:
    @pytest.mark.parametrize(
        "builder",
        [
            "seed_with_milestones",
            "transition_applied",
            "blocked_entered",
            "blocked_unblocked",
            "no_seed_tolerated",
        ],
    )
    def test_derive_state_matches_project_workflow_state(self, tmp_path, builder):
        """同一事件序列：引擎完整投影 == Python project_workflow_state（Q8 复用 fixture）。"""
        change_dir = el_seed_new_gen_change(tmp_path)
        if builder == "seed_with_milestones":
            el_append_raw_event(change_dir, "backlog_updated", 2, artifact_path="docs/x.md")
            el_append_raw_event(change_dir, "grill_completed", 3)
            el_append_raw_event(change_dir, "design_reviewed", 4)
            el_append_raw_event(change_dir, "known_debt_updated", 5, artifact_path="docs/known-debt.md")
        elif builder == "transition_applied":
            el_append_raw_event(
                change_dir, "transition_applied", 2,
                transition=el_transition(
                    {"phase": "planning", "sub_state": "exploring"},
                    {"phase": "planning", "sub_state": "writing_proposal"},
                ),
            )
        elif builder == "blocked_entered":
            el_append_raw_event(
                change_dir, "blocked_entered", 2,
                transition=el_transition(
                    {"phase": "planning", "sub_state": "writing_design"},
                    {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
                ),
                blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "proposal done"},
            )
        elif builder == "blocked_unblocked":
            el_append_raw_event(
                change_dir, "blocked_entered", 2,
                transition=el_transition(
                    {"phase": "planning", "sub_state": "writing_design"},
                    {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
                ),
                blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "proposal done"},
            )
            el_append_raw_event(
                change_dir, "blocked_resolved", 3,
                transition=el_transition(
                    {"phase": "blocked", "sub_state": "awaiting_proposal_confirmation"},
                    {"phase": "planning", "sub_state": "writing_design"},
                ),
            )
        elif builder == "no_seed_tolerated":
            change_dir = tmp_path / "openspec" / "changes" / "gen0-change"
            change_dir.mkdir(parents=True)
            el_append_raw_event(change_dir, "backlog_updated", 1, change_id="gen0-change", artifact_path="docs/x.md")
            el_append_raw_event(change_dir, "current_spec_synced", 2, change_id="gen0-change", artifact_path="openspec/specs/x.md")

        python_projection = project_workflow_state(change_dir)
        engine_projection = _load_engine().derive_state(_events_of(change_dir))

        assert engine_projection == python_projection  # 完整投影 dict（confirmed 6）

    def test_derive_state_unknown_event_raises(self, tmp_path):
        change_dir = el_seed_new_gen_change(tmp_path)
        el_append_raw_event(change_dir, "mystery_event", 2)
        with pytest.raises(StatechartError, match="unknown workflow event type"):
            _load_engine().derive_state(_events_of(change_dir))

    def test_derive_state_rejects_blocked_non_awaiting(self, tmp_path):
        change_dir = el_seed_new_gen_change(tmp_path)
        el_append_raw_event(
            change_dir, "blocked_entered", 2,
            transition=el_transition(
                {"phase": "planning", "sub_state": "writing_design"},
                {"phase": "blocked", "sub_state": "weird_blocked"},
            ),
            blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "x"},
        )
        with pytest.raises(StatechartError, match="awaiting type or null"):
            _load_engine().derive_state(_events_of(change_dir))

    def test_legal_targets_parity_all_declared_states(self):
        """逐态 legal_targets 等价（合法等价才是真 parity，confirmed 6）。"""
        engine = _load_engine()
        for state in _all_declared_states():
            phase, sub = parse_state(state)
            python_targets = sorted(
                state_name(t.phase, t.sub_state)
                for t in get_legal_targets(StateSnapshot(phase=phase, sub_state=sub))
            )
            engine_targets = sorted(engine.legal_targets(state))
            assert engine_targets == python_targets, f"legal_targets mismatch for {state}"

    def test_can_transition_parity_all_combos(self):
        """逐态 can_transition == validate_transition（全部状态 × 全部 trigger）。"""
        engine = _load_engine()
        states = _all_declared_states()
        triggers = ("auto", "handoff", "human_review", "human_rollback")
        for from_state in states:
            from_phase, from_sub = parse_state(from_state)
            for to_state in states + ["blocked", "done"]:
                to_phase, to_sub = parse_state(to_state)
                for trigger in triggers:
                    try:
                        validate_transition(
                            StateSnapshot(phase=from_phase, sub_state=from_sub),
                            StateSnapshot(phase=to_phase, sub_state=to_sub),
                            trigger,
                        )
                        python_ok = True
                    except StateMachineError:
                        python_ok = False
                    engine_ok = engine.can_transition(from_state, to_state, trigger)
                    assert engine_ok == python_ok, (
                        f"can_transition mismatch: {from_state} -> {to_state} ({trigger})"
                    )


# ── 2.3 演示测试（fixture：awaiting_design_confirmation，Q1/Q6）─────────


def _demo_statechart() -> FlowStatechart:
    """提交 statechart + 测试内注入演示态（跑完即弃，不进提交文件）。"""
    data = json.loads(SUBMITTED_STATECHART.read_text(encoding="utf-8"))
    data["states"]["blocked.awaiting_design_confirmation"] = {
        "_description": "演示态（test-only fixture）：等待 design 确认",
        "recovery": "from_blocked_from",
        "recovery_default": {"phase": "planning", "sub_state": "writing_design"},
        "on": [],
    }
    return FlowStatechart(data)


class TestDemoFixture:
    def test_submitted_statechart_has_no_demo_state(self):
        """提交的 flow/statechart.json 干净，不含演示态（Q6）。"""
        states = FlowStatechart.load(SUBMITTED_STATECHART).states
        assert "blocked.awaiting_design_confirmation" not in states

    def test_engine_derives_demo_state_and_recovery(self):
        """引擎从注入 statechart 正确派生新态 + 恢复（改规则不改 Python 的证据）。"""
        engine = FlowEngine(_demo_statechart())
        events = [
            {"event_type": "change_created", "change_id": "demo"},
            {
                "event_type": "blocked_entered",
                "change_id": "demo",
                "transition": el_transition(
                    {"phase": "planning", "sub_state": "writing_design"},
                    {"phase": "blocked", "sub_state": "awaiting_design_confirmation"},
                ),
                "blocker": {"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "design done"},
            },
        ]
        projection = engine.derive_state(events)
        assert projection["state"] == {"phase": "blocked", "sub_state": "awaiting_design_confirmation"}
        assert engine.chart.is_awaiting_state_name("blocked.awaiting_design_confirmation")

        # 恢复目标数据依赖：blocked_from 优先，否则 recovery_default 兜底
        assert engine.recovery_target(events, "blocked.awaiting_design_confirmation") == {
            "phase": "planning",
            "sub_state": "writing_design",
        }
        assert engine.can_transition("blocked.awaiting_design_confirmation", "planning.writing_design", "auto")
        assert engine.legal_targets("blocked.awaiting_design_confirmation") == []

    def test_old_python_raises_on_demo_state_known_boundary(self, tmp_path):
        """旧 Python 对演示态 raise 属已知边界：本 change 不要求它处理（Q1）。"""
        change_dir = el_seed_new_gen_change(tmp_path)
        el_append_raw_event(
            change_dir, "blocked_entered", 2,
            transition=el_transition(
                {"phase": "planning", "sub_state": "writing_design"},
                {"phase": "blocked", "sub_state": "awaiting_design_confirmation"},
            ),
            blocker={"blocked_from": {"phase": "planning", "sub_state": "writing_design"}, "reason": "design done"},
        )
        with pytest.raises(StateMachineError, match="awaiting type or null"):
            project_workflow_state(change_dir)


# ── 2.4 workflow_methods 兼容测试（Q3）────────────────────────────────


class TestWorkflowMethodsCompat:
    def test_phase_sub_state_sections_present(self):
        """不删 phase/sub_state 段：四 phase 键 + 每 sub_state 键都在。"""
        methods = json.loads((REPO_ROOT / "scripts" / "workflow_methods.json").read_text(encoding="utf-8"))
        for phase in ("wayfinding", "planning", "building", "closing"):
            assert phase in methods, f"workflow_methods 缺 phase 段: {phase}"
        from agent.workflow.models import PHASE_SUB_STATES

        for phase, subs in PHASE_SUB_STATES.items():
            for sub in subs:
                assert sub in methods[phase], f"workflow_methods 缺 sub_state 段: {phase}.{sub}"

    def test_method_hint_direct_index_unchanged(self):
        """_method_hint 直接 methods[phase][sub_state]['hint'] 索引行为不变。"""
        from scripts.workflow_state import _method_hint

        hint = _method_hint("planning", "exploring")
        assert hint == json.loads(
            (REPO_ROOT / "scripts" / "workflow_methods.json").read_text(encoding="utf-8")
        )["planning"]["exploring"]["hint"]

    def test_build_path_includes_all_sub_states(self):
        """_build_path 遍历 PHASE_SUB_STATES 输出状态路径（completed/current/pending）。"""
        from scripts.workflow_state import _build_path

        path = _build_path("planning", "writing_design")
        assert [step["sub_state"] for step in path] == list(PHASE_SUB_STATES["planning"])
        statuses = [step["status"] for step in path]
        assert statuses[1] == "completed"  # exploring 已完成
        assert statuses[2] == "current"    # writing_design 当前
        assert statuses[-1] == "pending"   # 之后待办


# ── 2.5 e2e 1：引擎 CLI 冒烟（真实归档 change）────────────────────────


class TestE2eEngineCliSmoke:
    def test_derive_state_cli_matches_flow_status(self):
        """真实归档 change 事件文件跑引擎 CLI，输出 == flow status（state/milestones/seq）。"""
        assert ARCHIVE_PLATFORM_GATE_EVENTS.exists(), "归档 change 事件文件缺失"
        engine_result = subprocess.run(
            [sys.executable, str(ENGINE), "derive-state", "--events", str(ARCHIVE_PLATFORM_GATE_EVENTS)],
            capture_output=True,
            text=True,
        )
        assert engine_result.returncode == 0, engine_result.stderr
        engine_projection = json.loads(engine_result.stdout)

        flow_result = subprocess.run(
            [sys.executable, str(WORKFLOW_STATE_CLI), "flow", "status", "--change", "2026-08-16-platform-gate"],
            capture_output=True,
            text=True,
        )
        assert flow_result.returncode == 0, flow_result.stderr
        flow_projection = json.loads(flow_result.stdout)

        assert engine_projection["state"] == flow_projection["state"]
        assert engine_projection["milestones"] == flow_projection["milestones"]
        assert engine_projection["source_event_seq"] == flow_projection["source_event_seq"]
        assert engine_projection["change_id"] == flow_projection["change_id"]

    def test_engine_cli_validate_exit_code(self):
        result = subprocess.run(
            [sys.executable, str(ENGINE), "validate"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


# ── 2.6 e2e 2：真实生命周期（flow block → confirm → advance → 归档）──────


class TestE2eRealLifecycle:
    def _seed(self, tmp_path, change_id: str):
        return cli_seed_gen2_change(tmp_path, change_id)

    def _flow(self, tmp_path, *args) -> subprocess.CompletedProcess:
        return cli_run_cli(tmp_path, *args)

    def test_block_confirm_advance_archive_projection(self, tmp_path):
        change_id = "e2e-lifecycle"
        change_dir = self._seed(tmp_path, change_id)

        # advance: exploring → writing_proposal
        result = self._flow(tmp_path, "flow", "advance", "--change", change_id, "--to", "writing_proposal")
        assert result.returncode == 0, result.stderr
        # block: writing_proposal → blocked.awaiting_proposal_confirmation
        result = self._flow(
            tmp_path, "flow", "block", "--change", change_id, "--awaiting", "awaiting_proposal_confirmation"
        )
        assert result.returncode == 0, result.stderr
        # confirm: blocked.awaiting_proposal_confirmation → writing_proposal（blocked_from）
        result = self._flow(tmp_path, "flow", "confirm", "--change", change_id)
        assert result.returncode == 0, result.stderr

        events = _events_of(change_dir)
        engine_projection = _load_engine().derive_state(events)
        disk_projection = json.loads((change_dir / "workflow-state.json").read_text(encoding="utf-8"))
        python_projection = project_workflow_state(change_dir)

        assert engine_projection["state"] == {"phase": "planning", "sub_state": "writing_proposal"}
        assert engine_projection == python_projection
        assert disk_projection["state"] == engine_projection["state"]

        # 目标驱动 API + blocked 恢复语义（Q5/Q4）
        engine = _load_engine()
        assert engine.recovery_target(events, "blocked.awaiting_proposal_confirmation") == {
            "phase": "planning",
            "sub_state": "writing_proposal",
        }
        assert "planning.writing_design" in engine.legal_targets("planning.writing_proposal")
        assert engine.can_transition("planning.writing_proposal", "planning.writing_design", "auto")

        # 归档（同目录 mv 到 archive/）后只读查询：投影仍正确
        archive_dir = tmp_path / "openspec" / "changes" / "archive" / f"2026-08-16-{change_id}"
        archive_dir.parent.mkdir(parents=True, exist_ok=True)
        change_dir.rename(archive_dir)

        flow_result = self._flow(
            tmp_path, "flow", "status", "--change", f"2026-08-16-{change_id}"
        )
        assert flow_result.returncode == 0, flow_result.stderr
        archived_flow = json.loads(flow_result.stdout)
        archived_events = _events_of(archive_dir)
        assert _load_engine().derive_state(archived_events)["state"] == archived_flow["state"]


# ── 2.7 e2e 3：演示集成（注入新态后引擎驱动 flow 生命周期）───────────────


class TestE2eDemoIntegration:
    def test_engine_drives_demo_awaiting_lifecycle(self, tmp_path):
        """演示集成：注入 awaiting_design_confirmation 后，引擎端到端驱动
        block → confirm 生命周期（旧 Python 无法处理的态），"改规则不改 Python"证据。"""
        change_id = "demo-integration"
        change_dir = tmp_path / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True)
        cli_append_ev(change_dir, "change_created", 1, change_id)
        cli_append_ev(
            change_dir,
            "transition_applied",
            2,
            change_id,
            transition=cli_tr(
                {"phase": "planning", "sub_state": "exploring"},
                {"phase": "planning", "sub_state": "writing_proposal"},
            ),
        )

        engine = FlowEngine(_demo_statechart())

        # 引擎驱动 block：legal_targets 把 blocked 作为合法目标，can_transition 接受 demo awaiting
        assert "blocked" in engine.legal_targets("planning.writing_proposal")
        assert engine.can_transition(
            "planning.writing_proposal", "blocked.awaiting_design_confirmation", "auto"
        )
        blocked_events = _events_of(change_dir) + [
            {
                "event_type": "blocked_entered",
                "change_id": change_id,
                "transition": {
                    "from": {"phase": "planning", "sub_state": "writing_proposal"},
                    "to": {"phase": "blocked", "sub_state": "awaiting_design_confirmation"},
                    "trigger": "auto",
                },
            }
        ]
        assert engine.derive_state(blocked_events)["state"] == {
            "phase": "blocked",
            "sub_state": "awaiting_design_confirmation",
        }

        # 引擎驱动 confirm：恢复目标 = blocked_from（writing_proposal），数据依赖
        recovery = engine.recovery_target(blocked_events, "blocked.awaiting_design_confirmation")
        assert recovery == {"phase": "planning", "sub_state": "writing_proposal"}
        confirmed_events = blocked_events + [
            {
                "event_type": "blocked_resolved",
                "change_id": change_id,
                "transition": {
                    "from": {"phase": "blocked", "sub_state": "awaiting_design_confirmation"},
                    "to": recovery,
                    "trigger": "auto",
                },
            }
        ]
        assert engine.derive_state(confirmed_events)["state"] == recovery

        # 无 blocked_entered 时的兜底：recovery_default
        default_events = [{"event_type": "change_created", "change_id": change_id}]
        assert engine.recovery_target(default_events, "blocked.awaiting_design_confirmation") == {
            "phase": "planning",
            "sub_state": "writing_design",
        }

    def test_old_python_rejects_demo_block(self, tmp_path):
        """旧 Python flow block 的 --awaiting choices 不含演示态：确认已知边界。"""
        change_id = "demo-block"
        change_dir = cli_seed_gen2_change(tmp_path, change_id)
        result = cli_run_cli(
            tmp_path, "flow", "block", "--change", change_id, "--awaiting", "awaiting_design_confirmation"
        )
        assert result.returncode != 0
        # argparse choices 校验在 cmd_flow_block 之前拦截：仅三个产品 awaiting 态可选
        assert "invalid choice" in result.stderr
        # 失败不写事件：引擎投影仍为 seed 态
        assert _load_engine().derive_state(_events_of(change_dir))["state"] == {
            "phase": "planning",
            "sub_state": "exploring",
        }

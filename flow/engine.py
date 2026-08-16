#!/usr/bin/env python3
"""声明化流程引擎（P4，declarative-flow-engine，issue #141）。

stdlib-only 薄引擎消费 ``flow/statechart.json``，提供与现有 Python 状态机
（``agent/workflow/event_log.py`` 的投影派生 + ``agent/workflow/state_machine.py``
的合法性校验）**等价**的派生、合法性校验与合法目标查询。parity 等价 pin 由
``tests/test_declarative_flow_engine.py`` 机械断言（gen-2 only，完整投影）。

核心 API 只依赖 stdlib（json/argparse），不 import ``agent/`` 包，满足
「引擎收进 ``flow/`` 目录、可拆缝平移」（#124）。``validate(parity=True)``
的 parity 交叉校验在对现有 Python ``validate_transition`` 时才懒加载 ``agent`` 包，
是本仓库特有的结构+语义双保险，不属于核心引擎依赖。

语义锚定现有代码（design D1-D8 + grill Q1-Q9）：
- 派生跟随每条状态事件的 ``transition.to``，从不查转移表（与 Python 投影一致）；
  未知事件类型 raise（Q2）、``NON_STATE`` 跳过、milestones 只收集。
- 转移合法性：``can_transition`` 镜像 ``validate_transition``（blocked 进入/恢复、
  done、self-loop handoff、human_rollback 均为动态规则，on 表声明静态邻接）。
- ``legal_targets`` 镜像 ``get_legal_targets``（phase 内邻接 + blocked + gate 跨 phase）。
- awaiting 态恢复目标是**数据依赖**（Q4）：最后 ``blocked_entered`` 的
  ``transition.from``，兜底 statechart 的 ``recovery_default``（镜像
  ``workflow_state._AWAITING_RECOVERY_DEFAULTS``）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "statechart/v1"
DEFAULT_STATECHART_PATH = Path(__file__).resolve().parent / "statechart.json"
WORKFLOW_STATE_SCHEMA = "workflow-state/v1"

CHANGE_CREATED_EVENT_TYPE = "change_created"
BLOCKED_EVENT_TYPE = "blocked_entered"
UNBLOCKED_EVENT_TYPE = "blocked_resolved"
ROUTING_UPDATED_EVENT_TYPE = "routing_updated"
WAYFINDING_CHILDREN_EVENT_TYPE = "wayfinding_children_spawned"

# 镜像 agent/workflow/event_log.py 常量（双源真值已知债务，D6）。
NON_STATE_EVENT_TYPES = {
    "protected_artifact_explained",
    "current_spec_synced",
    "backlog_updated",
    "change_archived",
    "resume_audit_reconciled",
}
MILESTONE_EVENT_TYPES = {
    "grill_completed",
    "design_reviewed",
    "design_review_completed",
    "building_review_completed",
    "known_debt_updated",
}

TRIGGERS = ("auto", "handoff", "human_review", "human_rollback")
PHASE_ORDER = {"wayfinding": 0, "planning": 1, "building": 2, "closing": 3, "blocked": -1, "done": 4}
GATE_SUB_STATE = "ready_for_review"
DEFAULT_SEED_STATE = {"phase": "planning", "sub_state": "exploring"}


class StatechartError(ValueError):
    """引擎语义错误（镜像 StateMachineError 的角色）。"""


def parse_state(state: str | dict | tuple) -> tuple[str, str | None]:
    """状态归一化为 ``(phase, sub_state)``。

    接受 ``"planning.exploring"`` 字符串、``{"phase": ..., "sub_state": ...}`` dict
    或 ``(phase, sub_state)`` 二元组。sub_state 为 None 时状态名 = phase（如 ``"blocked"``）。
    """
    if isinstance(state, str):
        if "." in state:
            phase, sub = state.split(".", 1)
        else:
            phase, sub = state, None
    elif isinstance(state, dict):
        phase = state.get("phase")
        sub = state.get("sub_state")
    else:
        phase, sub = state
    return phase, sub


def state_name(phase: str, sub_state: str | None) -> str:
    """``(phase, sub_state)`` → 状态名；sub_state 为 None 时状态名 = phase。"""
    return phase if sub_state is None else f"{phase}.{sub_state}"


class FlowStatechart:
    """``flow/statechart.json`` 的加载与查询（状态集 / on 表 / recovery 声明）。"""

    def __init__(self, data: dict):
        self.data = data
        self.id = data.get("id")
        self.initial = data.get("initial")
        self.states = data.get("states", {})
        if not isinstance(self.states, dict):
            raise StatechartError("states must be an object")
        # phase -> [sub_state, ...]（按声明顺序，rollback 语义需要先后关系）
        self._phase_sub_states: dict[str, list[str]] = {}
        self._state_set: set[str] = set()
        self._on_table: dict[str, list[dict]] = {}
        self._recovery: dict[str, dict] = {}
        for name, spec in self.states.items():
            if not isinstance(spec, dict):
                raise StatechartError(f"state {name!r} must be an object")
            phase, sub = parse_state(name)
            if phase not in PHASE_ORDER:
                raise StatechartError(f"invalid phase in state name: {name!r}")
            if sub is not None:
                if phase == "done":
                    raise StatechartError(f"done phase cannot declare sub_states: {name!r}")
                self._phase_sub_states.setdefault(phase, [])
                if sub not in self._phase_sub_states[phase]:
                    self._phase_sub_states[phase].append(sub)
            self._state_set.add(name)
            self._on_table[name] = [t for t in spec.get("on", []) if isinstance(t, dict)]
            if spec.get("recovery") is not None:
                self._recovery[name] = {
                    "mode": spec.get("recovery"),
                    "default": spec.get("recovery_default"),
                }

    @classmethod
    def load(cls, path: str | Path | None = None) -> "FlowStatechart":
        path = Path(path) if path else DEFAULT_STATECHART_PATH
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StatechartError(f"cannot load statechart {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise StatechartError(f"statechart {path} must be a JSON object")
        if data.get("_schema") != SCHEMA:
            raise StatechartError(f"unexpected statechart _schema: {data.get('_schema')!r}")
        return cls(data)

    # ── 查询 API ──────────────────────────────────────────────────────

    def has_state(self, name: str) -> bool:
        return name in self._state_set

    def sub_states(self, phase: str) -> list[str]:
        """某 phase 声明的 sub_state 序列（镜像 PHASE_SUB_STATES）。"""
        return list(self._phase_sub_states.get(phase, []))

    def transitions(self, name: str) -> list[dict]:
        """状态名的 on 表条目（``{trigger, to, _description?}``）。"""
        return self._on_table.get(name, [])

    def adjacent_sub_states(self, phase: str, sub: str) -> list[str]:
        """phase 内邻接目标（on 表同 phase 目标，忽略 trigger）→ 镜像 WITHIN_PHASE_ADJACENT。"""
        result: list[str] = []
        for t in self.transitions(state_name(phase, sub)):
            t_phase, t_sub = parse_state(t.get("to", ""))
            if t_phase == phase and t_sub is not None:
                result.append(t_sub)
        return result

    def cross_phase_targets(self, phase: str, sub: str) -> list[tuple[str, str | None]]:
        """gate 跨 phase 前进目标（on 表跨 phase 目标）→ 镜像 CROSS_PHASE_FORWARD。"""
        result: list[tuple[str, str | None]] = []
        for t in self.transitions(state_name(phase, sub)):
            t_phase, t_sub = parse_state(t.get("to", ""))
            if t_phase != phase:
                result.append((t_phase, t_sub))
        return result

    def awaiting_sub_states(self) -> list[str]:
        """blocked.awaiting_* 子态名（声明了 recovery 的 blocked 子态）→ 镜像 AWAITING_SUB_STATES。"""
        result: list[str] = []
        for name in self.states:
            phase, sub = parse_state(name)
            if phase == "blocked" and sub is not None:
                result.append(sub)
        return result

    def is_awaiting_state_name(self, name: str) -> bool:
        phase, sub = parse_state(name)
        return phase == "blocked" and sub in self.awaiting_sub_states()

    def recovery_mode(self, name: str) -> str | None:
        rec = self._recovery.get(name)
        return rec["mode"] if rec else None

    def recovery_default(self, name: str) -> dict | None:
        rec = self._recovery.get(name)
        return dict(rec["default"]) if rec and isinstance(rec["default"], dict) else None


class FlowEngine:
    """声明化薄引擎：派生 / 合法性 / 合法目标 / on 表查询。"""

    def __init__(self, statechart: FlowStatechart):
        self.chart = statechart

    # ── 派生（镜像 project_workflow_state 的 gen-2 路径）─────────────────

    def derive_state(self, events: list[dict], change_id_hint: str | None = None) -> dict:
        """从事件序列派生完整投影（state + milestones + source_event_seq）。

        语义严格对齐 Python（Q2）：未知事件类型 raise、NON_STATE 跳过、
        milestones 只收集、容忍仅「无 seed 事件」。gen-1（initialized 开头）
        不在引擎范围（design D4 排除，归档兼容逻辑与声明化目标无关）。
        """
        events = list(events)
        if not events:
            raise StatechartError("workflow-events.jsonl is empty")
        change_id = events[0].get("change_id") or change_id_hint or "unknown"
        state = dict(DEFAULT_SEED_STATE)
        milestones: list[str] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise StatechartError(f"event at index {index} is not an object")
            event_type = event.get("event_type")
            if event_type == CHANGE_CREATED_EVENT_TYPE and index == 0:
                continue  # seed 已应用（默认 planning.exploring）
            if event_type in NON_STATE_EVENT_TYPES:
                continue
            if event_type in MILESTONE_EVENT_TYPES:
                if event_type not in milestones:
                    milestones.append(event_type)
                continue
            if event_type == "transition_applied":
                self._apply_transition_to_state(state, event)
            elif event_type == BLOCKED_EVENT_TYPE:
                self._apply_blocked_to_state(state, event)
            elif event_type == UNBLOCKED_EVENT_TYPE:
                self._apply_unblocked_to_state(state, event)
            elif event_type in (ROUTING_UPDATED_EVENT_TYPE, WAYFINDING_CHILDREN_EVENT_TYPE):
                continue  # 不属于 workflow-state 形状（state/milestones）
            else:
                raise StatechartError(f"unknown workflow event type: {event_type}")
        return {
            "schema": WORKFLOW_STATE_SCHEMA,
            "change_id": change_id,
            "state": state,
            "milestones": milestones,
            "source_event_seq": len(events),
        }

    def _apply_transition_to_state(self, state: dict, event: dict) -> None:
        transition = event.get("transition")
        if not isinstance(transition, dict):
            raise StatechartError("transition_applied event missing transition")
        self._validate_transition(transition)
        state.clear()
        state.update(dict(transition["to"]))

    def _apply_blocked_to_state(self, state: dict, event: dict) -> None:
        transition = event.get("transition")
        if not isinstance(transition, dict):
            raise StatechartError("blocked_entered event missing transition")
        self._validate_transition(transition)
        to_phase, to_sub = parse_state(transition["to"])
        if to_phase != "blocked":
            raise StatechartError("blocked event must transition to blocked")
        # 镜像 event_log._apply_blocked_to_state：blocked sub_state 必须是声明 awaiting 类型或 None
        if to_sub is not None and to_sub not in self.chart.awaiting_sub_states():
            raise StatechartError(
                f"blocked sub_state must be an awaiting type or null: {to_sub!r}"
            )
        state.clear()
        state.update(dict(transition["to"]))

    def _apply_unblocked_to_state(self, state: dict, event: dict) -> None:
        transition = event.get("transition")
        if not isinstance(transition, dict):
            raise StatechartError("blocked_resolved event missing transition")
        self._validate_transition(transition)
        from_phase, _ = parse_state(transition["from"])
        if from_phase != "blocked":
            raise StatechartError("unblocked event must transition from blocked")
        state.clear()
        state.update(dict(transition["to"]))

    def _validate_transition(self, transition: dict) -> None:
        """校验单条 transition dict，非法 raise（镜像 _validate_transition_dict）。"""
        from_state = parse_state(transition.get("from"))
        to_state = parse_state(transition.get("to"))
        trigger = transition.get("trigger")
        if trigger not in TRIGGERS:
            raise StatechartError(f"invalid trigger: {trigger!r}")
        if not self.can_transition(from_state, to_state, trigger):
            raise StatechartError(
                f"invalid transition: {state_name(*from_state)} -> {state_name(*to_state)} "
                f"(trigger={trigger})"
            )

    # ── 合法性（镜像 validate_transition）──────────────────────────────

    def can_transition(
        self,
        from_state: str | dict | tuple,
        to_state: str | dict | tuple,
        trigger: str,
    ) -> bool:
        """``(from, to, trigger)`` 是否合法——镜像 ``validate_transition`` 的判定。

        on 表只声明静态邻接；blocked 进入/恢复、done、self-loop handoff、
        human_rollback 是动态规则（与 Python 语义锚定）。
        """
        from_phase, from_sub = parse_state(from_state)
        to_phase, to_sub = parse_state(to_state)
        if trigger not in TRIGGERS:
            return False

        # sub_state 成员校验（镜像 _validate_sub_state，blocked/done 无 sub_state）
        if from_phase not in ("blocked", "done"):
            if from_sub is None or from_sub not in self.chart.sub_states(from_phase):
                return False
        if to_phase not in ("blocked", "done"):
            if to_sub is None or to_sub not in self.chart.sub_states(to_phase):
                return False

        # blocked 进入：任意非 blocked/done → blocked 合法（awaiting 子态由事件层校验）
        if to_phase == "blocked":
            if from_phase == "blocked":
                return False
            if from_phase == "done":
                return False
            return True

        # blocked 恢复：blocked → 任意目标合法（目标由 caller 决定，数据依赖 Q4）
        if from_phase == "blocked":
            return True

        # done 转移：仅 closing.ready_for_review → done，且不允许 human_rollback
        if to_phase == "done":
            if from_phase != "closing" or from_sub != GATE_SUB_STATE:
                return False
            if trigger == "human_rollback":
                return False
            return True

        # self-loop：仅 handoff trigger 合法（标记 handoff 时刻）
        if from_phase == to_phase and from_sub == to_sub:
            return trigger == "handoff"

        # phase 内 human_rollback：可跳回任意更早 sub_state
        if trigger == "human_rollback" and from_phase == to_phase:
            subs = self.chart.sub_states(from_phase)
            if from_sub not in subs or to_sub not in subs:
                return False
            if subs.index(to_sub) >= subs.index(from_sub):
                return False
            return True

        # 同 phase：on 表邻接
        if from_phase == to_phase:
            return to_sub in self.chart.adjacent_sub_states(from_phase, from_sub)

        # 跨 phase：human_rollback → 更早 phase；否则 gate 前进
        if trigger == "human_rollback":
            from_idx = PHASE_ORDER.get(from_phase, -999)
            to_idx = PHASE_ORDER.get(to_phase, -999)
            if to_idx < 0:
                return False
            if to_idx >= from_idx:
                return False
            if to_sub is None or to_sub not in self.chart.sub_states(to_phase):
                return False
            return True

        if from_sub != GATE_SUB_STATE:
            return False  # 跨 phase 前进必须从 gate
        return (to_phase, to_sub) in self.chart.cross_phase_targets(from_phase, from_sub)

    # ── 合法目标（镜像 get_legal_targets）──────────────────────────────

    def legal_targets(self, state: str | dict | tuple) -> list[str]:
        """给定状态的全部合法下一状态名列表（phase 内邻接 + blocked + gate 跨 phase）。"""
        phase, sub = parse_state(state)
        if phase in ("blocked", "done"):
            return []  # blocked 恢复目标数据依赖；done 终态
        targets: list[str] = []
        for t_sub in self.chart.adjacent_sub_states(phase, sub):
            targets.append(state_name(phase, t_sub))
        targets.append("blocked")
        if sub == GATE_SUB_STATE:
            for t_phase, t_sub in self.chart.cross_phase_targets(phase, sub):
                targets.append(state_name(t_phase, t_sub))
        return targets

    # ── awaiting 恢复目标（镜像 workflow_state._awaiting_recovery_target）──

    def recovery_target(self, events: list[dict], state: str | dict | tuple) -> dict:
        """flow confirm 的恢复目标：优先最后 blocked_entered 的 transition.from，
        否则按 awaiting 类型 recovery_default（数据依赖，Q4）。"""
        for event in reversed(list(events)):
            if not isinstance(event, dict):
                continue
            if event.get("event_type") == BLOCKED_EVENT_TYPE:
                trans = event.get("transition")
                if isinstance(trans, dict) and trans.get("from"):
                    return dict(trans["from"])
        phase, sub = parse_state(state)
        default = self.chart.recovery_default(state_name(phase, sub)) if sub else None
        return dict(default) if default else dict(DEFAULT_SEED_STATE)

    # ── on 表查询（声明阅读用，非 flow 命令驱动入口，Q5）────────────────

    def apply_transition(self, state: str | dict | tuple, event: str) -> str:
        """按 on 表返回 ``trigger == event`` 的首个目标状态名；未声明则保持当前状态。

        仅供声明文件阅读/演示；**不是** flow 命令的驱动入口——派生由
        ``derive_state``（跟随 transition.to）驱动（D7）。同 trigger 多条转移时
        返回首条，语义歧义由调用方自行规避。
        """
        name = state if isinstance(state, str) else state_name(*parse_state(state))
        for t in self.chart.transitions(name):
            if t.get("trigger") == event:
                return t["to"]
        return name

    # ── 结构 + parity 校验 ─────────────────────────────────────────────

    def validate(self, parity: bool = True) -> list[str]:
        """结构校验（引用完整性 / initial 存在 / 无孤立状态）+ parity 交叉校验。

        parity 交叉校验把声明的每条转移 ``(from, to, trigger)`` 对现有 Python
        ``validate_transition`` 逐条验证（confirmed 4）：声明了 Python 判非法的
        转移即报错（语义漂移事前机械拦截）。
        """
        errors: list[str] = []
        data = self.chart.data
        if data.get("_schema") != SCHEMA:
            errors.append(f"missing or unexpected _schema: {data.get('_schema')!r}")
        if not data.get("id"):
            errors.append("missing id")
        initial = data.get("initial")
        if not initial:
            errors.append("missing initial")
        elif not self.chart.has_state(initial):
            errors.append(f"initial references undeclared state: {initial!r}")

        # 转移引用完整性 + trigger 合法性
        for name, spec in self.chart.states.items():
            for t in spec.get("on", []):
                if not isinstance(t, dict):
                    errors.append(f"{name}: on entry is not an object: {t!r}")
                    continue
                trigger = t.get("trigger")
                if trigger not in TRIGGERS:
                    errors.append(f"{name}: invalid trigger {trigger!r}")
                to = t.get("to")
                if not isinstance(to, str) or not self.chart.has_state(to):
                    errors.append(f"{name}: transition references undeclared state: {to!r}")

        # 孤立状态：非 initial、非目标、非外部进入/终态 phase 的声明态
        referenced: set[str] = set()
        for name, spec in self.chart.states.items():
            for t in spec.get("on", []):
                if isinstance(t, dict) and isinstance(t.get("to"), str):
                    referenced.add(t["to"])
        for name in self.chart.states:
            phase, _ = parse_state(name)
            if phase in ("wayfinding", "blocked", "done"):
                continue  # wayfinding 外部进入（handoff 直接建态）；blocked/done 动态/终态
            if name == initial:
                continue
            if name not in referenced:
                errors.append(f"orphan state (never a target, not initial): {name!r}")

        # awaiting recovery 完整性
        for name, spec in self.chart.states.items():
            if "recovery" not in spec:
                continue
            mode = spec.get("recovery")
            if mode != "from_blocked_from":
                errors.append(f"{name}: unsupported recovery mode {mode!r}")
            default = spec.get("recovery_default")
            if not isinstance(default, dict) or "phase" not in default:
                errors.append(f"{name}: recovery_default must be {{phase, sub_state}}")
            else:
                default_name = state_name(default.get("phase"), default.get("sub_state"))
                if not self.chart.has_state(default_name):
                    errors.append(
                        f"{name}: recovery_default references undeclared state: {default_name!r}"
                    )

        if parity:
            errors.extend(self._parity_cross_check())
        return errors

    def _parity_cross_check(self) -> list[str]:
        """对现有 Python ``validate_transition`` 逐条验证声明的转移（confirmed 4）。"""
        try:
            from agent.workflow.state_machine import (  # lazy：仅 parity 用
                StateMachineError,
                StateSnapshot,
                validate_transition,
            )
        except ImportError as exc:  # pragma: no cover - 核心引擎外路径
            return [f"parity cross-check unavailable: {exc}"]
        errors: list[str] = []
        for name, spec in self.chart.states.items():
            from_phase, from_sub = parse_state(name)
            for t in spec.get("on", []):
                if not isinstance(t, dict):
                    continue
                to_phase, to_sub = parse_state(t.get("to", ""))
                try:
                    validate_transition(
                        StateSnapshot(phase=from_phase, sub_state=from_sub),
                        StateSnapshot(phase=to_phase, sub_state=to_sub),
                        t.get("trigger", "auto"),
                    )
                except StateMachineError as exc:
                    errors.append(
                        f"{name} -> {t.get('to')} (trigger={t.get('trigger')}): "
                        f"Python validate_transition rejects: {exc}"
                    )
        return errors


# ── CLI ──────────────────────────────────────────────────────────────


def _load_engine(args) -> FlowEngine:
    return FlowEngine(FlowStatechart.load(getattr(args, "statechart", None)))


def _read_events(path: str | Path) -> list[dict]:
    events: list[dict] = []
    p = Path(path)
    if not p.exists():
        raise StatechartError(f"event log missing: {p}")
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise StatechartError(f"invalid workflow event JSON at line {lineno}: {exc}") from exc
        events.append(event)
    return events


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        engine = _load_engine(args)
        errors = engine.validate(parity=not args.no_parity)
    except StatechartError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 2
    print("statechart 校验通过（结构 + parity 交叉校验）")
    return 0


def cmd_derive_state(args: argparse.Namespace) -> int:
    try:
        engine = _load_engine(args)
        projection = engine.derive_state(_read_events(args.events), change_id_hint=args.change_id)
    except StatechartError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(projection, indent=2, ensure_ascii=False))
    return 0


def cmd_legal_targets(args: argparse.Namespace) -> int:
    try:
        engine = _load_engine(args)
        targets = engine.legal_targets(args.state)
    except StatechartError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(targets, indent=2, ensure_ascii=False))
    return 0


def cmd_can_transition(args: argparse.Namespace) -> int:
    try:
        engine = _load_engine(args)
        ok = engine.can_transition(args.from_state, args.to_state, args.trigger)
    except StatechartError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(ok, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_recovery_target(args: argparse.Namespace) -> int:
    try:
        engine = _load_engine(args)
        target = engine.recovery_target(_read_events(args.events), args.state)
    except StatechartError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(target, indent=2, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="声明化流程引擎 CLI（flow/statechart.json + flow/engine.py）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="结构校验 + parity 交叉校验（非法 exit 2）")
    p.add_argument("--statechart", default=None)
    p.add_argument("--no-parity", action="store_true", help="跳过对 Python validate_transition 的交叉校验")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("derive-state", help="从 workflow-events.jsonl 派生完整投影（JSON）")
    p.add_argument("--events", required=True)
    p.add_argument("--change-id", default=None)
    p.add_argument("--statechart", default=None)
    p.set_defaults(func=cmd_derive_state)

    p = sub.add_parser("legal-targets", help="输出状态的合法下一状态列表")
    p.add_argument("--state", required=True)
    p.add_argument("--statechart", default=None)
    p.set_defaults(func=cmd_legal_targets)

    p = sub.add_parser("can-transition", help="校验 (from, to, trigger) 是否合法（True exit 0 / False exit 1）")
    p.add_argument("--from", dest="from_state", required=True)
    p.add_argument("--to", dest="to_state", required=True)
    p.add_argument("--trigger", required=True, choices=list(TRIGGERS))
    p.add_argument("--statechart", default=None)
    p.set_defaults(func=cmd_can_transition)

    p = sub.add_parser("recovery-target", help="输出 awaiting 态恢复目标（数据依赖 + recovery_default）")
    p.add_argument("--state", required=True)
    p.add_argument("--events", required=True)
    p.add_argument("--statechart", default=None)
    p.set_defaults(func=cmd_recovery_target)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

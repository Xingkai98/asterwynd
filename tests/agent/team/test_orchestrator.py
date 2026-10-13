# tests/agent/team/test_orchestrator.py
"""群聊轮次编排（tasks 2.2 / 3.6）：slot 序列、@ 解析、静默、上限、
轮次终止三出口、轮次中用户消息、房间级互斥、成员中途变更、notice 注入。

编排器只依赖 ``SessionRunner`` 与 ``SessionResolver`` 抽象，本文件用假实现驱动
（真实 web 层实现在 ``tests/web_tests/test_group_chat_runner.py``）。
"""
import asyncio
from pathlib import Path

import pytest

from agent.team.models import Persona, Room
from agent.team.orchestrator import RoomOrchestrator
from agent.team.runner import SILENT_MARKER, TurnOutcome
from agent.team.store import TeamStore


class FakeRunner:
    """可编程的成员 runner：按 persona 队列给出出口，可阻塞以测并发。"""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.script: dict[str, list[TurnOutcome]] = {}
        self.default = TurnOutcome(status="text", text="默认发言")
        self.gate: asyncio.Event | None = None
        #: 只阻塞这些 session（``None`` = 阻塞全部）——用于「另一个房间不受影响」类用例。
        self.gate_sessions: set[str] | None = None
        self.started = asyncio.Event()
        self.timeouts: list[float | None] = []

    def push(self, persona_id: str, *outcomes: TurnOutcome) -> None:
        self.script.setdefault(persona_id, []).extend(outcomes)

    async def run(self, session_id, message, *, timeout=None, silent_marker=None):
        self.calls.append((session_id, message))
        self.timeouts.append(timeout)
        self.started.set()
        if self.gate is not None and (
            self.gate_sessions is None or session_id in self.gate_sessions
        ):
            await self.gate.wait()
        queue = self.script.get(session_id)
        outcome = queue.pop(0) if queue else self.default
        if outcome.status == "text" and silent_marker and outcome.text.strip() == silent_marker:
            return TurnOutcome(status="silent")
        return outcome


class FakeResolver:
    def __init__(self):
        self.created: list[tuple[str, str]] = []

    async def ensure_room_session(self, room_id: str, persona_id: str) -> str:
        self.created.append((room_id, persona_id))
        return f"room-{persona_id}"

    async def ensure_persona_chat_session(self, persona_id: str) -> str:
        return f"persona-{persona_id}"


@pytest.fixture
def team(tmp_path: Path):
    store = TeamStore(tmp_path)
    personas = {}
    for pid in ("pA", "pB", "pC"):
        store.upsert_persona(Persona(name=pid.upper(), id=pid))
        personas[pid] = pid
    room = Room(name="r", members=["pA", "pB", "pC"], admin="pA")
    store.save_room(room)
    runner = FakeRunner()
    resolver = FakeResolver()
    orch = RoomOrchestrator(store=store, resolver=resolver, runner=runner)
    return store, room, runner, resolver, orch


def _posts(store, room):
    return [e for e in store.read_room_log(room.id) if e.kind == "post"]


def _systems(store, room):
    return [e for e in store.read_room_log(room.id) if e.kind == "system"]


def _no_admin(store, room):
    """去掉房间 admin：开局 slot 退化为「成员顺序」，让整条成员循环成为主路径。"""
    room.admin = None
    store.save_room(room)
    return room


class TestSlotSequence:
    @pytest.mark.asyncio
    async def test_leading_mention_is_first_speaker(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "@PB 你觉得呢")
        assert runner.calls[0][0] == "room-pB"

    @pytest.mark.asyncio
    async def test_plain_message_goes_to_admin_first(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "大家好")
        assert runner.calls[0][0] == "room-pA"

    @pytest.mark.asyncio
    async def test_plain_message_falls_back_to_first_main_bot(self, team):
        store, room, runner, _, orch = team
        room.admin = None
        room.members = ["pB", "pC", "pA"]
        store.save_room(room)
        store.set_main_bot_ids(["pA"])
        await orch.submit_user_message(room.id, "大家好")
        assert runner.calls[0][0] == "room-pA"

    @pytest.mark.asyncio
    async def test_plain_message_without_admin_or_chief_uses_member_order(self, team):
        store, room, runner, _, orch = team
        room.admin = None
        store.save_room(room)
        await orch.submit_user_message(room.id, "大家好")
        assert [sid for sid, _ in runner.calls][0] == "room-pA"

    @pytest.mark.asyncio
    async def test_multiple_leading_mentions_in_appearance_order(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "@PC @PB 你们两个说")
        assert [sid for sid, _ in runner.calls[:2]] == ["room-pC", "room-pB"]

    @pytest.mark.asyncio
    async def test_duplicate_leading_mention_counts_once(self, team):
        store, room, runner, _, orch = team
        runner.default = TurnOutcome(status="silent")
        await orch.submit_user_message(room.id, "@PB @PB 说两句")
        assert [sid for sid, _ in runner.calls] == ["room-pB"]


class TestMentionBoundaries:
    @pytest.mark.asyncio
    async def test_unknown_name_ignored_without_error(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "@不存在的名字 在吗")
        # 无效点名不报错，回落默认应答者（房间 admin）
        assert runner.calls[0][0] == "room-pA"

    @pytest.mark.asyncio
    async def test_member_mention_in_the_middle_of_a_post_chains(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="text", text="@PB 你来补充一下"))
        await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls[:3]] == ["room-pA", "room-pB", "room-pC"]

    @pytest.mark.asyncio
    async def test_member_mentioning_itself_or_unknown_is_ignored(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push(
            "room-pA",
            TurnOutcome(status="text", text="我 @PA 自己，还有 @张三 都不算"),
        )
        await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls[:3]] == ["room-pA", "room-pB", "room-pC"]

    @pytest.mark.asyncio
    async def test_member_mentioning_same_peer_twice_appends_once(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="text", text="@PC @PC 请回答"))
        runner.push("room-pB", TurnOutcome(status="silent"))
        await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pC", "room-pB"]


class TestSilence:
    @pytest.mark.asyncio
    async def test_silent_member_posts_nothing_and_round_continues(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="silent"))
        result = await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        assert [e.speaker for e in _posts(store, room)] == ["pB", "pC"]
        assert result.termination == "completed"

    @pytest.mark.asyncio
    async def test_pass_sentinel_is_treated_as_silence(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        for pid in ("pA", "pB", "pC"):
            runner.push(f"room-{pid}", TurnOutcome(status="text", text=SILENT_MARKER))
        await orch.submit_user_message(room.id, "开始")
        assert _posts(store, room) == []

    @pytest.mark.asyncio
    async def test_silent_turn_still_advances_the_injection_cursor(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="silent"))
        runner.push("room-pB", TurnOutcome(status="silent"))
        runner.push("room-pC", TurnOutcome(status="silent"))
        await orch.submit_user_message(room.id, "第一轮")
        # 回合开始推进到「当时」的 seq（= 开局用户消息那条），静默回合也推进。
        assert store.get_room(room.id).seen["pA"] == 1

        runner.calls.clear()
        runner.default = TurnOutcome(status="silent")
        await orch.submit_user_message(room.id, "第二轮")
        # 第二轮 pA 的注入切片里不应再出现第一轮用户消息（游标已推进）
        prompt = [m for sid, m in runner.calls if sid == "room-pA"][0]
        assert "第一轮" not in prompt
        assert "第二轮" in prompt


class TestPerMemberTurnCap:
    @pytest.mark.asyncio
    async def test_non_admin_capped_at_two_turns_per_round(self, team):
        store, room, runner, _, orch = team
        # 每个非 admin 成员都想把别人 @ 一遍，形成最长的接力链。
        for pid in ("pA", "pB", "pC"):
            runner.push(f"room-{pid}", *[TurnOutcome(status="text", text="@PA @PB @PC 接力")] * 8)
        await orch.submit_user_message(room.id, "开始")
        counts: dict[str, int] = {}
        for sid, _ in runner.calls:
            counts[sid] = counts.get(sid, 0) + 1
        assert counts["room-pB"] <= 2
        assert counts["room-pC"] <= 2
        assert counts["room-pA"] <= 4


class TestRoundTermination:
    @pytest.mark.asyncio
    async def test_completed_when_all_slots_done(self, team):
        store, room, runner, _, orch = team
        result = await orch.submit_user_message(room.id, "开始")
        assert result.termination == "completed"
        assert _systems(store, room) == []

    @pytest.mark.asyncio
    async def test_limit_exit_records_system_entry(self, team):
        store, room, runner, resolver, _ = team
        # 缺省额度（4/4）下 3 人房间的每人上限之和小于轮次上限，达上限路径不可达；
        # 这里注入小额度把「达上限」出口变成主路径（缺省值见 orchestrator 常量）。
        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner,
            extra_turns=1, admin_extra_turns=0,
        )
        for pid in ("pA", "pB", "pC"):
            runner.push(f"room-{pid}", *[TurnOutcome(status="text", text="@PA @PB @PC 接力")] * 12)
        result = await orch.submit_user_message(room.id, "开始")
        assert result.termination == "limit"
        texts = [e.text for e in _systems(store, room)]
        assert any("因达上限结束" in t for t in texts)
        # 达上限后 SHALL NOT 自行开新一轮
        assert len([e for e in store.read_room_log(room.id) if e.kind == "user"]) == 1

    @pytest.mark.asyncio
    async def test_failed_member_records_system_and_round_continues(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="failed", code="llm", message="boom"))
        result = await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        assert any("PA" in e.text for e in _systems(store, room))
        assert result.termination == "completed"

    @pytest.mark.asyncio
    async def test_timeout_records_system_and_round_continues(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="timeout"))
        await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        assert any("超时" in e.text or "timeout" in e.text for e in _systems(store, room))

    @pytest.mark.asyncio
    async def test_all_failed_exit(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        runner.default = TurnOutcome(status="failed", code="llm", message="boom")
        result = await orch.submit_user_message(room.id, "开始")
        assert result.termination == "all_failed"
        assert len(_systems(store, room)) == 3

    @pytest.mark.asyncio
    async def test_no_new_round_starts_without_user_message(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "开始")
        calls_after_first = len(runner.calls)
        await asyncio.sleep(0)          # 让出控制权：不应有自发的第二轮
        assert len(runner.calls) == calls_after_first


class TestRoundTimeouts:
    @pytest.mark.asyncio
    async def test_turn_timeout_is_configured(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "开始")
        assert all(t == pytest.approx(240.0) for t in runner.timeouts)


class TestMidRoundUserMessages:
    @pytest.mark.asyncio
    async def test_queued_message_is_logged_and_does_not_open_a_second_round(self, team):
        store, room, runner, _, orch = team
        gate = asyncio.Event()
        runner.gate = gate
        first = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await runner.started.wait()

        second = await orch.submit_user_message(room.id, "@PC 补充一句")
        assert second.queued is True
        assert second.termination == "queued"
        # 消息立刻进了房间日志（用户可见）
        assert any(e.kind == "user" and e.text == "@PC 补充一句"
                   for e in store.read_room_log(room.id))

        gate.set()
        result = await first
        assert result.queued is False
        assert len([e for e in store.read_room_log(room.id) if e.kind == "user"]) == 2

    @pytest.mark.asyncio
    async def test_queued_message_mention_is_appended_after_current_position(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        gate = asyncio.Event()
        runner.gate = gate
        runner.default = TurnOutcome(status="silent")
        first = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await runner.started.wait()
        await orch.submit_user_message(room.id, "@PC 你来说")
        gate.set()
        await first
        # 开局默认序 pA → pB → pC；中途 @PC 追加在**当前位次之后**（pA 之后）→ pC 排在 pB 前
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pC", "room-pB"]

    @pytest.mark.asyncio
    async def test_queued_message_does_not_change_the_limit_base(self, team):
        store, room, runner, _, orch = team
        gate = asyncio.Event()
        runner.gate = gate
        runner.default = TurnOutcome(status="silent")
        first = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await runner.started.wait()
        await orch.submit_user_message(room.id, "@PA @PB @PC 都说说")
        gate.set()
        result = await first
        # 上限按**开局** slot 数（1 个 admin）计算：1 + 4 + 4 = 9，不因中途消息变基。
        assert result.limit == 9


class TestRoomMutex:
    @pytest.mark.asyncio
    async def test_two_concurrent_messages_do_not_open_two_rounds(self, team):
        store, room, runner, _, orch = team
        gate = asyncio.Event()
        runner.gate = gate
        runner.default = TurnOutcome(status="silent")
        first = asyncio.create_task(orch.submit_user_message(room.id, "第一条"))
        await runner.started.wait()
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二条"))
        await asyncio.sleep(0)
        assert len(runner.calls) == 1, "第二个请求不得并行开第二轮"
        gate.set()
        await first
        await second
        assert orch.is_round_active(room.id) is False

    @pytest.mark.asyncio
    async def test_different_rooms_run_independently(self, team):
        store, room, runner, _, orch = team
        other = Room(name="other", members=["pB"], admin="pB")
        store.save_room(other)
        gate = asyncio.Event()
        runner.gate = gate
        runner.gate_sessions = {"room-pA"}      # 只挡住第一个房间的成员
        runner.default = TurnOutcome(status="silent")
        first = asyncio.create_task(orch.submit_user_message(room.id, "a"))
        await runner.started.wait()
        result = await orch.submit_user_message(other.id, "b")
        assert result.queued is False
        gate.set()
        await first


class TestMembershipChanges:
    @pytest.mark.asyncio
    async def test_member_removed_mid_round_is_skipped(self, team):
        store, room, runner, _, orch = team
        _no_admin(store, room)
        gate = asyncio.Event()
        runner.gate = gate
        runner.gate_sessions = {"room-pA"}
        first = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await runner.started.wait()
        room.members = ["pA", "pC"]      # pB 中途被移出
        store.save_room(room)
        gate.set()
        result = await first
        assert "room-pB" not in [sid for sid, _ in runner.calls]
        assert [e.speaker for e in _posts(store, room)] == ["pA", "pC"]
        assert result.termination == "completed"


class TestNoticeInjection:
    @pytest.mark.asyncio
    async def test_notice_is_injected_into_room_session_prompt(self, team):
        store, room, runner, _, orch = team
        room.notice = "先说结论，再说理由"
        store.save_room(room)
        await orch.submit_user_message(room.id, "开始")
        assert all("先说结论，再说理由" in msg for _, msg in runner.calls)

    @pytest.mark.asyncio
    async def test_empty_notice_adds_nothing(self, team):
        store, room, runner, _, orch = team
        await orch.submit_user_message(room.id, "开始")
        assert all("Group notice" not in msg for _, msg in runner.calls)


class TestReviewSink:
    @pytest.mark.asyncio
    async def test_speaking_turn_notifies_sink_but_silent_does_not(self, team):
        store, room, runner, resolver, _ = team
        seen: list[tuple[str, str, str]] = []

        class Sink:
            async def on_member_turn(self, *, room_id, persona_id, outcome):
                seen.append((room_id, persona_id, outcome.status))

        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner, review_sink=Sink()
        )
        _no_admin(store, room)
        runner.push("room-pA", TurnOutcome(status="silent"))
        runner.push("room-pB", TurnOutcome(status="timeout"))
        await orch.submit_user_message(room.id, "开始")
        by_persona = {p: s for _, p, s in seen}
        assert by_persona["pA"] == "silent"
        assert by_persona["pB"] == "timeout"
        assert by_persona["pC"] == "text"


class TestSessionCreationFailure:
    @pytest.mark.asyncio
    async def test_session_failure_records_system_and_continues(self, team):
        store, room, runner, _, orch = team

        class BoomResolver(FakeResolver):
            async def ensure_room_session(self, room_id, persona_id):
                if persona_id == "pA":
                    raise RuntimeError("no slot")
                return await super().ensure_room_session(room_id, persona_id)

        _no_admin(store, room)
        orch = RoomOrchestrator(store=store, resolver=BoomResolver(), runner=runner)
        result = await orch.submit_user_message(room.id, "开始")
        assert [sid for sid, _ in runner.calls] == ["room-pB", "room-pC"]
        assert any("PA" in e.text for e in _systems(store, room))
        assert result.termination == "completed"

# tests/agent/team/test_orchestrator.py
"""群聊轮次编排（tasks 2.2 / 3.6）：slot 序列、@ 解析、静默、上限、
轮次终止三出口、轮次中用户消息、房间级互斥、成员中途变更、notice 注入。

编排器只依赖 ``SessionRunner`` 与 ``SessionResolver`` 抽象，本文件用假实现驱动
（真实 web 层实现在 ``tests/web_tests/test_group_chat_team.py``）。
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
        #: 可选的进度信号脚本（session_id -> [(kind, data), ...]）。
        self.progress_script: dict[str, list[tuple[str, dict]]] = {}
        self.progress_calls: list[tuple[str, str, dict]] = []

    def push(self, persona_id: str, *outcomes: TurnOutcome) -> None:
        self.script.setdefault(persona_id, []).extend(outcomes)

    async def run(
        self, session_id, message, *, timeout=None, silent_marker=None,
        on_progress=None,
    ):
        self.calls.append((session_id, message))
        self.timeouts.append(timeout)
        self.started.set()
        if self.gate is not None and (
            self.gate_sessions is None or session_id in self.gate_sessions
        ):
            await self.gate.wait()
        if on_progress is not None:
            for kind, data in self.progress_script.get(session_id, []):
                self.progress_calls.append((session_id, kind, data))
                await on_progress(kind, data)
                # 给合并发射器一个让出点，测试才能观察到中间表。
                await asyncio.sleep(0)
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


class TestReplyMode:
    """Decision 19：房间应答模式（admin 默认 / everyone 全员各得一次机会）。"""

    @pytest.mark.asyncio
    async def test_admin_mode_only_admin_speaks_first(self, team):
        store, room, runner, _, orch = team
        assert room.reply_mode == "admin"
        await orch.submit_user_message(room.id, "大家好")
        assert [sid for sid, _ in runner.calls] == ["room-pA"]

    @pytest.mark.asyncio
    async def test_everyone_mode_gives_every_member_one_chance(self, team):
        store, room, runner, _, orch = team
        room.reply_mode = "everyone"
        store.save_room(room)
        await orch.submit_user_message(room.id, "大家好")
        # admin 先，其余按成员顺序；每名成员各一次
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        assert [e.speaker for e in _posts(store, room)] == ["pA", "pB", "pC"]

    @pytest.mark.asyncio
    async def test_everyone_mode_lets_members_stay_silent(self, team):
        store, room, runner, _, orch = team
        room.reply_mode = "everyone"
        store.save_room(room)
        runner.push("room-pA", TurnOutcome(status="silent"))
        runner.push("room-pB", TurnOutcome(status="text", text=SILENT_MARKER))
        result = await orch.submit_user_message(room.id, "大家好")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        assert [e.speaker for e in _posts(store, room)] == ["pC"]
        assert result.termination == "completed"

    @pytest.mark.asyncio
    async def test_everyone_mode_without_admin_uses_member_order(self, team):
        store, room, runner, _, orch = team
        room.reply_mode = "everyone"
        room.admin = None
        store.save_room(room)
        await orch.submit_user_message(room.id, "大家好")
        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]

    @pytest.mark.asyncio
    async def test_mention_overrides_both_modes(self, team):
        store, room, runner, _, orch = team
        room.reply_mode = "everyone"
        store.save_room(room)
        await orch.submit_user_message(room.id, "@PB 你说")
        assert [sid for sid, _ in runner.calls] == ["room-pB"]

    @pytest.mark.asyncio
    async def test_per_member_cap_still_applies_in_everyone_mode(self, team):
        store, room, runner, resolver, _ = team
        room.reply_mode = "everyone"
        room.admin = None
        store.save_room(room)
        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner,
            extra_turns=1, admin_extra_turns=0,
        )
        for pid in ("pA", "pB", "pC"):
            runner.push(f"room-{pid}", *[TurnOutcome(status="text", text="@PA @PB @PC 接力")] * 12)
        result = await orch.submit_user_message(room.id, "开始")
        counts: dict[str, int] = {}
        for sid, _ in runner.calls:
            counts[sid] = counts.get(sid, 0) + 1
        assert all(n <= 2 for n in counts.values())
        assert result.termination == "limit"


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


class TestRoomMutexUnderSuspendingSink:
    """I2 回归：``on_event`` 会挂起时，「查—建」仍必须是**无 await 介入**的原子段。

    生产路径的 ``on_event`` 必然挂起（房间 WS 的 ``await ws.send_json``），所以旧实现
    「先 emit 再注册」会让同 tick 的两次提交都通过「查—建」检查、都开轮。
    """

    @pytest.mark.asyncio
    async def test_concurrent_submits_with_suspending_sink_open_one_round(self, team):
        store, room, runner, resolver, _ = team
        gate = asyncio.Event()
        events: list[str] = []

        async def sink(event_type, data):
            events.append(event_type)
            await gate.wait()          # 必然挂起：模拟房间 WS 的 send_json

        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner, on_event=sink
        )
        runner.default = TurnOutcome(status="silent")

        first = asyncio.create_task(orch.submit_user_message(room.id, "第一条"))
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二条"))
        await asyncio.sleep(0)         # 让两个任务都跑到各自的第一个挂起点
        await asyncio.sleep(0)

        assert orch.is_round_active(room.id) is True, "轮次已在跑，轮中必须报 active"
        assert runner.calls == [], "第二个提交不得并行驱动成员"

        gate.set()
        r1, r2 = await asyncio.gather(first, second)
        assert sorted([r1.queued, r2.queued]) == [False, True], "只应开一轮，另一条排队"
        assert len([e for e in store.read_room_log(room.id) if e.kind == "user"]) == 2
        assert orch.is_round_active(room.id) is False, "轮末必须清掉认领"

    @pytest.mark.asyncio
    async def test_round_can_start_again_after_the_previous_one_ends(self, team):
        store, room, runner, resolver, _ = team
        orch = RoomOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="silent")
        await orch.submit_user_message(room.id, "第一轮")
        result = await orch.submit_user_message(room.id, "第二轮")
        assert result.queued is False
        assert len([e for e in store.read_room_log(room.id) if e.kind == "user"]) == 2


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


class _EventedOrchestrator(RoomOrchestrator):
    """测试用编排器：把 on_event 收进列表，便于断言状态协议。"""

    def __init__(self, **kwargs):
        self.events: list[tuple[str, dict]] = []
        user_sink = kwargs.pop("on_event", None)

        async def sink(event_type, data):
            self.events.append((event_type, data))
            if user_sink is not None:
                await user_sink(event_type, data)

        super().__init__(on_event=sink, **kwargs)

    def by_type(self, event_type):
        return [data for kind, data in self.events if kind == event_type]


class _FailingResolver(FakeResolver):
    def __init__(self, fail_ids):
        super().__init__()
        self.fail_ids = set(fail_ids)

    async def ensure_room_session(self, room_id, persona_id):
        if persona_id in self.fail_ids:
            raise RuntimeError("session unavailable")
        return await super().ensure_room_session(room_id, persona_id)


class _RaisingRunner(FakeRunner):
    async def run(self, session_id, message, *, timeout=None, silent_marker=None,
                  on_progress=None):
        await super().run(
            session_id, message, timeout=timeout, silent_marker=silent_marker,
            on_progress=on_progress,
        )
        raise RuntimeError("boom")


class _GatedReview:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def on_member_turn(self, *, room_id, persona_id, outcome):
        return None

    async def on_round_end(self, *, room_id):
        self.calls += 1
        self.entered.set()
        await self.release.wait()


async def _wait_teardowns(orch, limit=200):
    for _ in range(limit):
        if not orch._teardown_tasks:
            return
        await asyncio.sleep(0)
    await asyncio.gather(*list(orch._teardown_tasks), return_exceptions=True)


class TestMemberStatusEvents:
    @pytest.mark.asyncio
    async def test_normal_turn_emits_full_tables_and_resets(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="text", text="答")
        runner.progress_script["room-pA"] = [
            ("run_started", {}),
            ("iteration_started", {}),
            ("assistant_delta", {}),
            ("tool_started", {"tool_id": "t1", "tool_name": "Bash"}),
            ("tool_finished", {"tool_id": "t1", "tool_name": "Bash"}),
            ("iteration_started", {}),
            ("run_completed", {}),
        ]
        await orch.submit_user_message(room.id, "你好")

        tables = orch.by_type("member_status")
        assert tables, "至少应发布一次 member_status"
        phases = [s["phase"] for data in tables for s in data["statuses"]
                  if s["persona_id"] == "pA"]
        assert "thinking" in phases
        assert "typing" in phases
        assert "tool" in phases
        tool_tables = [s for data in tables for s in data["statuses"]
                       if s["phase"] == "tool" and s["persona_id"] == "pA"]
        assert any(s["tools"] == ["Bash"] for s in tool_tables)

        terminals = orch.by_type("member_post")
        assert len(terminals) == 1
        assert isinstance(terminals[0]["status_seq"], int)
        statuses, seq = orch.status_snapshot(room.id)
        assert statuses == []
        assert seq >= terminals[0]["status_seq"]

    @pytest.mark.asyncio
    async def test_empty_output_emits_member_silent_and_idles(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="text", text="")
        await orch.submit_user_message(room.id, "你好")
        silent = orch.by_type("member_silent")
        assert len(silent) == 1
        assert orch.status_snapshot(room.id)[0] == []

    @pytest.mark.asyncio
    async def test_session_creation_failure_emits_member_failed_with_name(self, team):
        store, room, runner, _, _ = team
        resolver = _FailingResolver({"pA"})
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="silent")
        await orch.submit_user_message(room.id, "你好")
        failed = orch.by_type("member_failed")
        assert len(failed) == 1
        assert failed[0]["status"] == "failed"
        assert failed[0]["name"] == "PA"
        assert orch.status_snapshot(room.id)[0] == []

    @pytest.mark.asyncio
    async def test_cancelled_round_emits_round_ended_cancelled(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.gate = asyncio.Event()
        task = asyncio.create_task(orch.submit_user_message(room.id, "你好"))
        await runner.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _wait_teardowns(orch)
        ended = orch.by_type("round_ended")
        assert len(ended) == 1
        assert ended[0]["termination"] == "cancelled"
        assert isinstance(ended[0]["status_seq"], int)
        assert orch.status_snapshot(room.id)[0] == []

    @pytest.mark.asyncio
    async def test_unexpected_exception_emits_round_ended_error(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        raising = _RaisingRunner()
        orch._runner = raising
        raising.default = TurnOutcome(status="silent")
        with pytest.raises(RuntimeError):
            await orch.submit_user_message(room.id, "你好")
        await _wait_teardowns(orch)
        ended = orch.by_type("round_ended")
        assert len(ended) == 1
        assert ended[0]["termination"] == "error"
        assert orch.status_snapshot(room.id)[0] == []

    @pytest.mark.asyncio
    async def test_status_only_emitted_on_change(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="text", text="答")
        runner.progress_script["room-pA"] = [
            ("iteration_started", {}),
            ("assistant_delta", {}),
            ("assistant_delta", {}),
            ("assistant_delta", {}),
        ]
        await orch.submit_user_message(room.id, "你好")
        tables = orch.by_type("member_status")
        typing = [
            data for data in tables
            if any(s["phase"] == "typing" for s in data["statuses"])
        ]
        assert len(typing) == 1

    @pytest.mark.asyncio
    async def test_cross_round_terminal_has_lower_seq_than_new_round(self, team):
        store, room, runner, resolver, _ = team
        review = _GatedReview()
        orch = _EventedOrchestrator(
            store=store, resolver=resolver, runner=runner, review_sink=review
        )
        runner.default = TurnOutcome(status="text", text="答")
        first = asyncio.create_task(orch.submit_user_message(room.id, "第一轮"))
        await review.entered.wait()          # 第一轮已 pop，旧 round_ended 尚未发出
        before = max(
            (data["status_seq"] for data in orch.by_type("member_status")),
            default=0,
        )
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二轮"))
        new_seq = None
        for _ in range(200):
            newer = [
                data["status_seq"] for data in orch.by_type("member_status")
                if data["status_seq"] > before
            ]
            if newer and len(runner.calls) >= 2:
                new_seq = max(newer)
                break
            await asyncio.sleep(0)
        assert orch.is_round_active(room.id) is True
        assert new_seq is not None, "第二轮必须发出比旧轮更高的状态 seq"
        review.release.set()
        await asyncio.gather(first, second)
        ended = sorted(
            (data["status_seq"] for data in orch.by_type("round_ended"))
        )
        assert len(ended) == 2
        assert ended[0] < new_seq, "旧轮终态必须早于新一轮的首个状态 seq"

    @pytest.mark.asyncio
    async def test_cancelling_released_round_does_not_touch_new_round(self, team):
        store, room, runner, resolver, _ = team
        review = _GatedReview()
        orch = _EventedOrchestrator(
            store=store, resolver=resolver, runner=runner, review_sink=review
        )
        runner.default = TurnOutcome(status="text", text="答")
        first = asyncio.create_task(orch.submit_user_message(room.id, "第一轮"))
        await review.entered.wait()
        # 第一轮已跑完 runner；让第二轮的 runner 阻塞，确保取消第一轮时第二轮仍 active。
        gate = asyncio.Event()
        runner.gate = gate
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二轮"))
        for _ in range(200):
            if len(runner.calls) >= 2:
                break
            await asyncio.sleep(0)
        assert orch.is_round_active(room.id) is True
        before = orch.status_snapshot(room.id)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert orch.is_round_active(room.id) is True
        assert orch.status_snapshot(room.id) == before
        gate.set()
        review.release.set()
        await second

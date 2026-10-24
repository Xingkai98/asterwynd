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
from agent.team.orchestrator import ROOM_REPLY_INSTRUCTION, RoomOrchestrator
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

    @pytest.mark.asyncio
    async def test_snapshot_filters_members_removed_from_room(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        orch._set_signal(room.id, "pA", "slot_started", {})
        room.members = ["pB"]
        store.save_room(room)
        statuses, _ = orch.status_snapshot(room.id)
        assert all(item["persona_id"] != "pA" for item in statuses)

    @pytest.mark.asyncio
    async def test_message_during_round_end_flush_starts_new_round(self, team):
        """N1：reset+release 之后的 flush 窗口内到达的消息必须开启新一轮。"""
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="silent")

        original_flush = orch._flush_status_emits
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def gated_flush(room_id):
            nonlocal calls
            calls += 1
            if calls == 2:               # 第一轮的 round-end flush（成员终态 flush 是 1）
                entered.set()
                await release.wait()
            await original_flush(room_id)

        orch._flush_status_emits = gated_flush
        first = asyncio.create_task(orch.submit_user_message(room.id, "第一轮"))
        await asyncio.wait_for(entered.wait(), timeout=2)

        gate = asyncio.Event()
        runner.gate = gate               # 让第二轮停在 runner，保持 active
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二轮"))
        for _ in range(200):
            if len(runner.calls) >= 2:
                break
            await asyncio.sleep(0)
        assert orch.is_round_active(room.id) is True
        queued = await orch.submit_user_message(room.id, "第三轮")
        assert queued.queued is True, "第三轮必须排队进 R2，而不是开启 R3"

        release.set()
        await first
        assert orch.is_round_active(room.id) is True, "旧轮 flush 结束不得释放 R2"
        gate.set()
        await second
        assert len(runner.calls) == 2, "M3 不得驱动第三个成员回合"

    @pytest.mark.asyncio
    async def test_resume_round_first_thinking_comes_from_iteration_started(self, team):
        store, room, runner, resolver, _ = team
        orch = _EventedOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = TurnOutcome(status="silent")
        # resume run 没有 run_started；只有 iteration_started。
        runner.progress_script["room-pA"] = [("iteration_started", {})]
        await orch.submit_user_message(room.id, "你好")
        thinking = [
            data for data in orch.by_type("member_status")
            if any(s["phase"] == "thinking" for s in data["statuses"])
        ]
        assert thinking, "iteration_started 必须能独立把状态推到 thinking"


# ===========================================================================
# 讨论链（change group-unlimited-discussion，design v4 Decision 1–10）
# ===========================================================================
#
# 本段全部用例的期望值按 design Decision 3 的优先级表与 Decision 7/8/10 的
# 事件契约写死（文案、键集合、精确计数）。

#: 链级 system 文案（design Decision 3 钉死的可测口径）。
CONTINUE_2 = "讨论继续（第 2 轮）"
CONTINUE_3 = "讨论继续（第 3 轮）"
CONVERGED_TEXT = "讨论已收敛（本轮全员静默）"
STOPPED_TEXT = "讨论已由用户停止"
ALL_FAILED_TEXT = "讨论已中止（本轮无人发言，存在失败）"
ROUND_LIMIT_TEXT = "讨论因本轮达上限结束"
MAX_LIMIT_TEXT = "讨论达安全上限结束"
MODE_CHANGED_TEXT = "讨论已结束（模式已变更）"
DISCONNECTED_TEXT = "讨论因页面断开而中止"

#: unlimited 提示词共同句（design Decision 4）。
CONVERGENCE_HINT = (
    "If the discussion has converged or you have nothing new to add, reply [PASS] "
    "— do not repeat points already made; do not speak just to fill the round."
)


def _text(text: str) -> TurnOutcome:
    return TurnOutcome(status="text", text=text)


def _silent() -> TurnOutcome:
    return TurnOutcome(status="silent")


def _unlimited(store, room) -> Room:
    """把房间切成 everyone + unlimited（唯一合法组合）。"""
    room.reply_mode = "everyone"
    room.discussion_mode = "unlimited"
    store.save_room(room)
    return room


@pytest.fixture
def chain_team(tmp_path: Path):
    """3 人 everyone + unlimited 房（admin = pA，speaking order pA/pB/pC）。"""
    store = TeamStore(tmp_path)
    for pid in ("pA", "pB", "pC"):
        store.upsert_persona(Persona(name=pid.upper(), id=pid))
    room = Room(
        name="r",
        members=["pA", "pB", "pC"],
        admin="pA",
        reply_mode="everyone",
        discussion_mode="unlimited",
    )
    store.save_room(room)
    runner = FakeRunner()
    resolver = FakeResolver()
    orch = RoomOrchestrator(store=store, resolver=resolver, runner=runner)
    return store, room, runner, resolver, orch


class FakeClock:
    """可注入时钟（墙钟安全阀的 slot 间检查用例）。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> float:
        self.now += float(delta)
        return self.now


class CallBlock:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()


class GateRunner(FakeRunner):
    """在第 n 次调用某个 session 时挂起（停止/取消/竞态窗口用例）。

    与 ``FakeRunner.gate`` 的区别：可以精确指定「第几次调用、哪个 session」，
    因此能在「第 3 轮 pB 回合进行中」这种时刻请求停止，而不误伤前面的轮次。
    """

    def __init__(self) -> None:
        super().__init__()
        self.blocks: dict[tuple[str, int], CallBlock] = {}
        self._seen: dict[str, int] = {}

    def block(self, session_id: str, call_number: int) -> CallBlock:
        block = CallBlock()
        self.blocks[(session_id, call_number)] = block
        return block

    async def run(
        self, session_id, message, *, timeout=None, silent_marker=None,
        on_progress=None,
    ):
        count = self._seen.get(session_id, 0) + 1
        self._seen[session_id] = count
        block = self.blocks.get((session_id, count))
        if block is not None:
            block.entered.set()
            await block.release.wait()
        return await super().run(
            session_id, message, timeout=timeout, silent_marker=silent_marker,
            on_progress=on_progress,
        )


class TickingRunner(FakeRunner):
    """每次成员 run 推进一次可注入时钟（模拟墙钟流逝）。"""

    def __init__(self, clock: FakeClock, step: float) -> None:
        super().__init__()
        self.clock = clock
        self.step = step

    async def run(
        self, session_id, message, *, timeout=None, silent_marker=None,
        on_progress=None,
    ):
        try:
            return await super().run(
                session_id, message, timeout=timeout, silent_marker=silent_marker,
                on_progress=on_progress,
            )
        finally:
            self.clock.advance(self.step)


def _evented(store, resolver, runner, **kwargs) -> _EventedOrchestrator:
    return _EventedOrchestrator(
        store=store, resolver=resolver, runner=runner, **kwargs
    )


class TestDiscussionChainConvergence:
    """design Decision 3/4/10 ① ②：自动续轮、全员静默收敛、每轮每人一次。"""

    @pytest.mark.asyncio
    async def test_three_rounds_then_converged(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.push("room-pA", _text("R1"), _text("R2"), _silent())
        runner.push("room-pB", _text("R1"), _silent(), _silent())
        runner.push("room-pC", _text("R1"), _silent(), _silent())

        result = await orch.submit_user_message(room.id, "开始讨论")

        # --- RoundResult（Decision 9：链级字段） ---
        assert result.queued is False
        assert result.termination == "completed"
        assert result.discussion_mode == "unlimited"
        assert result.discussion_reason == "converged"
        assert result.chain_id == f"{room.id}:1"
        assert result.rounds == 3
        assert result.rounds_started == 3

        # --- 每轮每人一次、顺序 admin 先 ---
        assert [sid for sid, _ in runner.calls] == [
            "room-pA", "room-pB", "room-pC",
        ] * 3

        # --- round_ended：每轮一次、链内序号与续轮标记 ---
        rounds = orch.by_type("round_ended")
        assert [data["round_index"] for data in rounds] == [1, 2, 3]
        assert [data["chain_continues"] for data in rounds] == [True, True, False]
        assert [data["termination"] for data in rounds] == ["completed"] * 3
        assert all(data["chain_id"] == result.chain_id for data in rounds)
        assert set(rounds[0]) == {
            "room_id", "termination", "limit", "status_seq",
            "chain_id", "round_index", "chain_continues",
        }

        # --- discussion_ended：每链至多一次、精确计数 ---
        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "converged"
        assert ended[0]["chain_id"] == result.chain_id
        assert ended[0]["rounds"] == 3
        assert ended[0]["rounds_started"] == 3
        assert ended[0]["turns"] == 9
        assert ended[0]["status_seq"] == rounds[-1]["status_seq"]
        assert isinstance(ended[0]["elapsed_seconds"], float)

        # --- 链内 system 条目：续轮 / 收敛，且实时经 system_entry 广播 ---
        systems = _systems(store, room)
        assert [entry.text for entry in systems] == [
            CONTINUE_2, CONTINUE_3, CONVERGED_TEXT,
        ]
        entries = orch.by_type("system_entry")
        assert [entry["text"] for entry in entries] == [e.text for e in systems]
        assert [entry["seq"] for entry in entries] == [e.seq for e in systems]
        assert all(entry["chain_id"] == result.chain_id for entry in entries)

        # --- discussion_started 一次、payload 钉死 ---
        started = orch.by_type("discussion_started")
        assert len(started) == 1
        assert started[0] == {
            "room_id": room.id,
            "chain_id": result.chain_id,
            "discussion_mode": "unlimited",
            "members": ["pA", "pB", "pC"],
            "round_index": 1,
            "limits": {"max_rounds": 200, "max_turns": 600, "max_seconds": 6000.0},
        }

        # --- 事件顺序：链起点在成员事件前、链终点是最后一条 ---
        types = [event_type for event_type, _ in orch.events]
        assert types[0] == "user_message"
        assert types.index("discussion_started") < types.index("member_speaking")
        assert types[-1] == "discussion_ended"

    @pytest.mark.asyncio
    async def test_round_two_uses_full_everyone_roster_after_leading_mention(
        self, chain_team
    ):
        """grill I7：续轮 SHALL 传空 opening，否则第 2 轮只剩开局被点名者。"""
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.push("room-pB", _text("我先说"))
        runner.default = _silent()

        result = await orch.submit_user_message(room.id, "@PB 你先说")

        assert [sid for sid, _ in runner.calls] == [
            "room-pB",            # 第 1 轮：只有被点名的 pB
            "room-pA", "room-pB", "room-pC",   # 第 2 轮：全员各一次
        ]
        assert result.discussion_reason == "converged"
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_partial_silence_does_not_converge(self, chain_team):
        """design 场景「部分成员静默不终止」：第 2 轮只有 pA 发言 → 继续。"""
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.push("room-pA", _text("R1"), _text("R2 新观点"), _silent())
        runner.push("room-pB", _text("R1"), _silent(), _silent())
        runner.push("room-pC", _text("R1"), _silent(), _silent())

        result = await orch.submit_user_message(room.id, "开始讨论")

        rounds = orch.by_type("round_ended")
        assert [data["chain_continues"] for data in rounds] == [True, True, False]
        assert result.discussion_reason == "converged"
        assert result.rounds == 3

    @pytest.mark.asyncio
    async def test_unlimited_prompt_adds_round_context_before_reply_instruction(
        self, chain_team
    ):
        """design Decision 4：unlimited 在 ROOM_REPLY_INSTRUCTION 之前追加轮次上下文。"""
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.push("room-pA", _text("R1 发言"))
        runner.default = _silent()

        await orch.submit_user_message(room.id, "开始讨论")

        prompts = [message for _, message in runner.calls]
        assert len(prompts) == 6                      # R1 3 次 + R2 3 次
        round1_head = (
            "Round 1 of a continuous discussion; every member speaks at most "
            "once per round."
        )
        round2_head = (
            "Round 2 of a continuing discussion. There is no new user message "
            "this round; the discussion continues because the previous round "
            "produced new content."
        )
        assert all(round1_head in prompt for prompt in prompts[:3])
        assert all(round2_head in prompt for prompt in prompts[3:])
        assert all(CONVERGENCE_HINT in prompt for prompt in prompts)
        for prompt in prompts:
            assert prompt.endswith(ROOM_REPLY_INSTRUCTION)
            assert prompt.index(CONVERGENCE_HINT) < prompt.index(
                ROOM_REPLY_INSTRUCTION
            )


class TestSingleModeZeroChange:
    """design Decision 3.5 / 9：single 零变化（事件、payload、RoundResult、prompt）。"""

    @pytest.mark.asyncio
    async def test_single_round_metadata_and_events_unchanged(self, team):
        store, room, runner, resolver, _ = team
        orch = _evented(store, resolver, runner)

        result = await orch.submit_user_message(room.id, "开始")

        assert result.queued is False
        assert result.termination == "completed"
        # Decision 9 / grill L11：新字段保持默认值。
        assert result.discussion_mode == "single"
        assert result.discussion_reason is None
        assert result.chain_id is None
        assert result.rounds == 0
        assert result.rounds_started == 0

        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert set(rounds[0]) == {"room_id", "termination", "limit", "status_seq"}

        # 零新事件（整事件类型集合的负向断言）。
        forbidden = {
            "discussion_started", "system_entry", "discussion_ended",
            "discussion_stop_requested",
        }
        assert not ({event_type for event_type, _ in orch.events} & forbidden)
        # user_message payload 四键不变。
        assert len(orch.by_type("user_message")) == 1
        assert set(orch.by_type("user_message")[0]) == {
            "room_id", "text", "seq", "queued",
        }
        # 只有一条用户消息、没有链级 system。
        assert [e.kind for e in store.read_room_log(room.id)] == ["user", "post"]
        assert _systems(store, room) == []

    @pytest.mark.asyncio
    async def test_single_prompt_has_no_discussion_context(self, team):
        store, room, runner, resolver, _ = team
        orch = RoomOrchestrator(store=store, resolver=resolver, runner=runner)
        runner.default = _silent()

        await orch.submit_user_message(room.id, "开始")

        prompt = runner.calls[0][1]
        assert "continuous discussion" not in prompt
        assert "do not speak just to fill the round" not in prompt
        assert prompt.endswith(ROOM_REPLY_INSTRUCTION)

    @pytest.mark.asyncio
    async def test_single_request_stop_returns_false_and_emits_nothing(self, team):
        store, room, runner, resolver, _ = team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        block = gate_runner.block("room-pA", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)

        assert await orch.request_stop(room.id) is False
        assert orch.by_type("discussion_stop_requested") == []

        block.release.set()
        await task
        assert orch.by_type("discussion_ended") == []
        assert orch.by_type("system_entry") == []

    @pytest.mark.asyncio
    async def test_request_stop_without_active_chain_returns_false(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        assert await orch.request_stop(room.id) is False


class TestStopDiscussion:
    """design Decision 5 / 10 ⑤⑥：优雅停止、幂等、轮间窗口。"""

    @pytest.mark.asyncio
    async def test_stop_during_third_round_finishes_current_turn(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        for pid in ("pA", "pB", "pC"):
            gate_runner.push(
                f"room-{pid}",
                _text("第1轮"),
                _text("第2轮"),
                _text("第3轮"),
            )
        block = gate_runner.block("room-pB", 3)   # 第 3 轮 pB 回合进行中

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)

        assert await orch.request_stop(room.id) is True
        # 重复请求：返回 True 但不重复发事件（CQ11）。
        assert await orch.request_stop(room.id) is True
        assert len(orch.by_type("discussion_stop_requested")) == 1
        assert orch.is_round_active(room.id) is True

        block.release.set()
        result = await task

        # 当前回合跑完（pB 的「第3轮」记入日志）、剩余 slot 不跑（pC 只有 2 次）。
        assert [sid for sid, _ in gate_runner.calls] == [
            "room-pA", "room-pB", "room-pC",
        ] * 2 + ["room-pA", "room-pB"]

        assert result.termination == "stopped"
        assert result.discussion_reason == "stopped"
        assert result.rounds == 2          # 第 3 轮未正常收尾，不计入
        assert result.rounds_started == 3

        rounds = orch.by_type("round_ended")
        assert len(rounds) == 3
        assert rounds[-1]["termination"] == "stopped"
        assert rounds[-1]["round_index"] == 3
        assert rounds[-1]["chain_continues"] is False

        stopped = orch.by_type("discussion_stop_requested")
        assert stopped[0]["chain_id"] == result.chain_id

        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "stopped"
        assert ended[0]["rounds"] == 2
        assert ended[0]["rounds_started"] == 3
        assert ended[0]["turns"] == 8      # 3 + 3 + 2

        systems = [entry.text for entry in _systems(store, room)]
        assert STOPPED_TEXT in systems
        assert orch.discussion_snapshot(room.id) == {"round": 0, "reason": "stopped"}
        assert orch.is_round_active(room.id) is False
        # 停止后 system_entry 文案即链结束文案
        assert orch.by_type("system_entry")[-1]["text"] == STOPPED_TEXT

    @pytest.mark.asyncio
    async def test_stop_between_rounds_ends_chain_without_new_round(self, chain_team):
        """design 4a：轮间窗口请求停止 → 不建新轮、不补发 round_ended。"""
        store, room, runner, resolver, _ = chain_team
        review = _GatedReview()
        orch = _evented(store, resolver, runner, review_sink=review)
        runner.default = _text("发言")

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(review.entered.wait(), timeout=2)  # 第 1 轮 review 挂起
        assert await orch.request_stop(room.id) is True
        review.release.set()
        result = await task

        assert [sid for sid, _ in runner.calls] == ["room-pA", "room-pB", "room-pC"]
        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert rounds[0]["chain_continues"] is True
        assert rounds[0]["termination"] == "completed"
        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "stopped"
        assert ended[0]["rounds"] == 1
        assert ended[0]["rounds_started"] == 1
        assert result.termination == "completed"   # 上一轮正常走完
        assert result.discussion_reason == "stopped"
        assert result.rounds == 1
        assert result.rounds_started == 1
        systems = [entry.text for entry in _systems(store, room)]
        assert CONTINUE_2 not in systems
        assert systems[-1] == STOPPED_TEXT
        assert orch.by_type("system_entry")[-1]["text"] == STOPPED_TEXT

    @pytest.mark.asyncio
    async def test_request_stop_after_chain_end_is_noop(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.default = _silent()                 # 第 1 轮全静默 → 收敛
        await orch.submit_user_message(room.id, "开始讨论")
        assert await orch.request_stop(room.id) is False
        assert len(orch.by_type("discussion_stop_requested")) == 0


class TestSafetyValves:
    """design Decision 6 / 10 ⑦：轮数 / 回合 / 墙钟 / round_limit 四路。"""

    @pytest.mark.asyncio
    async def test_max_rounds(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(
            store, resolver, runner, discussion_max_rounds=2,
        )
        runner.default = _text("发言")

        result = await orch.submit_user_message(room.id, "开始讨论")

        assert result.discussion_reason == "max_rounds"
        assert result.termination == "completed"     # 最后一轮正常走完
        assert result.rounds == 2
        assert result.rounds_started == 2
        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "max_rounds"
        assert ended[0]["turns"] == 6
        assert [e.text for e in _systems(store, room)] == [
            CONTINUE_2, MAX_LIMIT_TEXT,
        ]

    @pytest.mark.asyncio
    async def test_max_turns_when_quota_exhausts_at_round_end(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner, discussion_max_turns=6)
        runner.default = _text("发言")

        result = await orch.submit_user_message(room.id, "开始讨论")

        assert result.discussion_reason == "max_turns"
        assert result.rounds == 2
        assert result.rounds_started == 2
        rounds = orch.by_type("round_ended")
        assert [data["termination"] for data in rounds] == ["completed", "completed"]
        # 第 2 轮 limit 被回合额度截成 3，但恰好在轮末耗尽 ⇒ 上报 max_turns。
        # 第 1 轮 limit 也按「本轮预算 11 与链剩余额度 6 取 min」= 6。
        assert [data["limit"] for data in rounds] == [6, 3]
        ended = orch.by_type("discussion_ended")
        assert ended[0]["turns"] == 6
        assert [e.text for e in _systems(store, room)] == [
            CONTINUE_2, MAX_LIMIT_TEXT,
        ]

    @pytest.mark.asyncio
    async def test_round_limit_when_quota_truncates_round(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner, discussion_max_turns=4)
        runner.default = _text("发言")

        result = await orch.submit_user_message(room.id, "开始讨论")

        assert result.discussion_reason == "round_limit"
        assert result.termination == "limit"
        assert result.rounds == 2
        assert result.rounds_started == 2
        rounds = orch.by_type("round_ended")
        assert rounds[-1]["termination"] == "limit"
        assert rounds[-1]["limit"] == 1
        systems = [entry.text for entry in _systems(store, room)]
        # 轮级「本轮因达上限结束」与链级「讨论因本轮达上限结束」各一条。
        assert systems == [
            CONTINUE_2, "本轮因达上限结束", ROUND_LIMIT_TEXT,
        ]
        # L18：轮级 system 不经 system_entry 广播（只有链级文案）。
        assert [entry["text"] for entry in orch.by_type("system_entry")] == [
            CONTINUE_2, ROUND_LIMIT_TEXT,
        ]
        ended = orch.by_type("discussion_ended")
        assert ended[0]["reason"] == "round_limit"
        assert ended[0]["turns"] == 4

    @pytest.mark.asyncio
    async def test_max_seconds_checked_between_slots(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        clock = FakeClock(1000.0)
        ticking = TickingRunner(clock, 60.0)
        orch = _evented(
            store, resolver, ticking, clock=clock, discussion_max_seconds=100.0,
        )
        ticking.default = _text("发言")

        result = await orch.submit_user_message(room.id, "开始讨论")

        # pA(0→60)、pB(60→120) 之后，第 3 个 slot 开始前墙钟已越界 ⇒ 不再开新回合。
        assert [sid for sid, _ in ticking.calls] == ["room-pA", "room-pB"]
        assert result.discussion_reason == "max_seconds"
        assert result.rounds == 1
        assert result.rounds_started == 1
        ended = orch.by_type("discussion_ended")
        assert ended[0]["turns"] == 2
        assert ended[0]["elapsed_seconds"] == 120.0
        assert MAX_LIMIT_TEXT in [entry.text for entry in _systems(store, room)]

    @pytest.mark.asyncio
    async def test_all_failed_ends_chain(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.default = TurnOutcome(status="failed", code="llm", message="boom")

        result = await orch.submit_user_message(room.id, "开始讨论")

        assert result.discussion_reason == "all_failed"
        assert result.termination == "all_failed"
        assert result.rounds == 1
        assert _systems(store, room)[-1].text == ALL_FAILED_TEXT
        # 成员失败类 system 仍由既有 member_failed 合成，不进 system_entry（L18）。
        assert [entry["text"] for entry in orch.by_type("system_entry")] == [
            ALL_FAILED_TEXT
        ]


class TestUnconsumedUserMessages:
    """design User Ruling Q1 / 10 ⑬：未消费用户消息强制再开一轮。"""

    @pytest.mark.asyncio
    async def test_message_after_last_slice_forces_another_round(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        gate_runner.default = _silent()
        block = gate_runner.block("room-pC", 1)   # 最后一名成员切片已构造

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        queued = await orch.submit_user_message(room.id, "刚才说的再展开点")
        assert queued.queued is True
        block.release.set()
        result = await task

        rounds = orch.by_type("round_ended")
        assert len(rounds) == 2
        assert rounds[0]["chain_continues"] is True    # 未消费消息 → 不收敛
        assert rounds[1]["chain_continues"] is False
        assert result.discussion_reason == "converged"
        assert result.rounds == 2
        # 第 2 轮的切片必须看到那条消息。
        round2_prompts = [message for _, message in gate_runner.calls[3:]]
        assert len(round2_prompts) == 3
        assert all("刚才说的再展开点" in prompt for prompt in round2_prompts)

    @pytest.mark.asyncio
    async def test_safety_cap_wins_over_unconsumed_message(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(
            store, resolver, gate_runner, discussion_max_turns=3,
        )
        gate_runner.default = _silent()
        block = gate_runner.block("room-pC", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        await orch.submit_user_message(room.id, "这条消息没有回合看到")
        block.release.set()
        result = await task

        # max_turns（优先级 6）先于「未消费消息强制续轮」（第 11 行）。
        assert result.discussion_reason == "max_turns"
        assert result.rounds == 1
        assert result.rounds_started == 1

    @pytest.mark.asyncio
    async def test_pending_mention_between_rounds_applies_once(self, chain_team):
        """design 场景「轮间窗口到达的消息不丢失点名」：待应用点名下一轮生效后清空。"""
        store, room, runner, resolver, _ = chain_team

        class GateFirstReview:
            """只拦第 1 轮的 review（用于制造轮间窗口），后续轮次直接放行。"""

            def __init__(self):
                self.entered = asyncio.Event()
                self.release = asyncio.Event()
                self.calls = 0

            async def on_member_turn(self, *, room_id, persona_id, outcome):
                return None

            async def on_round_end(self, *, room_id):
                self.calls += 1
                if self.calls == 1:
                    self.entered.set()
                    await self.release.wait()

        review = GateFirstReview()
        orch = _evented(store, resolver, runner, review_sink=review)
        runner.push("room-pA", _text("第 1 轮发言"))
        runner.default = _silent()

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(review.entered.wait(), timeout=2)   # 第 1 轮已收尾、待续
        queued = await orch.submit_user_message(room.id, "@PC @PC 你也说两句")
        assert queued.queued is True
        review.release.set()
        result = await task

        # 消息落在轮间窗口（current.closed）→ 点名只进 pending_mentions；
        # 第 2 轮 pC 置顶且去重，之后清空、不跨链。
        assert [sid for sid, _ in runner.calls] == [
            "room-pA", "room-pB", "room-pC",     # 第 1 轮
            "room-pC", "room-pA", "room-pB",     # 第 2 轮：pC 置顶
        ]
        assert result.rounds == 2
        assert result.discussion_reason == "converged"


class TestModeChanged:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "field,value",
        [("discussion_mode", "single"), ("reply_mode", "admin")],
    )
    async def test_mode_change_mid_chain_ends_with_mode_changed(
        self, chain_team, field, value
    ):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        gate_runner.default = _text("发言")
        block = gate_runner.block("room-pA", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        setattr(room, field, value)
        store.save_room(room)
        block.release.set()
        result = await task

        assert result.discussion_reason == "mode_changed"
        assert result.rounds == 1
        assert result.rounds_started == 1
        assert [sid for sid, _ in gate_runner.calls] == [
            "room-pA", "room-pB", "room-pC",
        ]
        assert _systems(store, room)[-1].text == MODE_CHANGED_TEXT


class TestEmptyMembersDegenerate:
    @pytest.mark.asyncio
    async def test_unlimited_empty_room_degrades_to_single_round(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        room.members = []
        room.admin = None
        store.save_room(room)
        orch = _evented(store, resolver, runner)

        result = await orch.submit_user_message(room.id, "有人吗")

        assert result.termination == "completed"
        assert result.rounds == 0
        assert result.rounds_started == 0
        assert result.discussion_mode == "unlimited"
        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert set(rounds[0]) == {"room_id", "termination", "limit", "status_seq"}
        assert orch.by_type("discussion_started") == []
        assert orch.by_type("discussion_ended") == []
        assert orch.by_type("system_entry") == []
        assert _systems(store, room) == []
        assert [e.kind for e in store.read_room_log(room.id)] == ["user"]
        assert runner.calls == []


class TestCancellationAndErrors:
    """design Decision 8 / 10 ⑩⑯：取消 / 异常的链级 teardown。"""

    @pytest.mark.asyncio
    async def test_unlimited_cancel_teardown_and_next_chain(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        gate_runner.default = _text("发言")
        block = gate_runner.block("room-pA", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _wait_teardowns(orch)

        assert orch.is_round_active(room.id) is False
        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert rounds[0]["termination"] == "cancelled"
        assert rounds[0]["chain_id"] == f"{room.id}:1"
        assert rounds[0]["chain_continues"] is False
        assert isinstance(rounds[0]["status_seq"], int)

        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "cancelled"
        assert ended[0]["chain_id"] == f"{room.id}:1"
        assert ended[0]["rounds"] == 0
        assert ended[0]["rounds_started"] == 1
        # 被取消的当前轮未收尾，不计入 chain.turns（只统计已完成的成员回合）。
        assert ended[0]["turns"] == 0
        assert isinstance(ended[0]["status_seq"], int)

        # Q2：断线取消写 system 并尽力经 system_entry 广播。
        assert [entry.text for entry in _systems(store, room)] == [
            DISCONNECTED_TEXT
        ]
        assert [entry["text"] for entry in orch.by_type("system_entry")] == [
            DISCONNECTED_TEXT
        ]
        assert orch.discussion_snapshot(room.id) == {
            "round": 0, "reason": "cancelled",
        }
        assert orch.status_snapshot(room.id)[0] == []

        # 取消后房间已释放：下一条消息开新链（queued=False、chain_id 单调）。
        gate_runner.default = _silent()
        result = await orch.submit_user_message(room.id, "继续")
        assert result.queued is False
        assert result.chain_id == f"{room.id}:2"
        assert result.discussion_reason == "converged"

    @pytest.mark.asyncio
    async def test_unlimited_error_teardown_emits_chain_end_without_log(
        self, chain_team
    ):
        store, room, runner, resolver, _ = chain_team
        raising = _RaisingRunner()
        raising.default = _silent()
        orch = _evented(store, resolver, raising)

        with pytest.raises(RuntimeError):
            await orch.submit_user_message(room.id, "开始讨论")
        await _wait_teardowns(orch)

        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert rounds[0]["termination"] == "error"
        assert rounds[0]["chain_continues"] is False
        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "error"
        # error 不写房间日志（Decision 8）。
        assert _systems(store, room) == []
        assert orch.by_type("system_entry") == []
        assert orch.discussion_snapshot(room.id) == {"round": 0, "reason": "error"}
        assert orch.is_round_active(room.id) is False

    @pytest.mark.asyncio
    async def test_single_cancel_keeps_legacy_payload_and_no_log(self, team):
        store, room, runner, resolver, _ = team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        block = gate_runner.block("room-pA", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _wait_teardowns(orch)

        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert set(rounds[0]) == {"room_id", "termination", "limit", "status_seq"}
        assert rounds[0]["termination"] == "cancelled"
        assert orch.by_type("discussion_ended") == []
        assert _systems(store, room) == []
        assert orch.is_round_active(room.id) is False


class TestDeleteRoomMidChain:
    @pytest.mark.asyncio
    async def test_delete_room_ends_completed_without_resurrecting_log(
        self, chain_team
    ):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        gate_runner.default = _text("发言")
        block = gate_runner.block("room-pA", 1)

        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        store.remove_room(room.id)
        block.release.set()
        result = await task

        assert result.discussion_reason == "completed"
        assert result.rounds == 1
        assert result.rounds_started == 1
        # 房间已删：不复活日志、不写链级 system。
        assert store.read_room_log(room.id) == []
        rounds = orch.by_type("round_ended")
        assert len(rounds) == 1
        assert rounds[0]["termination"] == "completed"
        ended = orch.by_type("discussion_ended")
        assert len(ended) == 1
        assert ended[0]["reason"] == "completed"
        assert orch.discussion_snapshot(room.id) == {
            "round": 0, "reason": "completed",
        }


class TestChainRaceWindows:
    """design Decision 2 await 纪律 / 10 ⑪：可挂起 emit sink 竞态。"""

    @pytest.mark.asyncio
    async def test_second_message_while_first_emit_suspends_opens_one_chain(
        self, chain_team
    ):
        store, room, runner, resolver, _ = chain_team
        entered = asyncio.Event()
        gate = asyncio.Event()
        events: list[str] = []

        async def sink(event_type, data):
            events.append(event_type)
            if event_type == "user_message" and data.get("queued") is False:
                entered.set()
                await gate.wait()      # 模拟房间 WS send_json 必然挂起

        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner, on_event=sink
        )
        runner.default = _silent()

        first = asyncio.create_task(orch.submit_user_message(room.id, "第一条"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = await orch.submit_user_message(room.id, "第二条")
        assert second.queued is True
        assert orch.is_round_active(room.id) is True

        gate.set()
        first_result = await first
        assert first_result.queued is False
        assert first_result.discussion_reason == "converged"
        assert events.count("discussion_started") == 1
        assert events.count("round_ended") == 1
        assert events.count("discussion_ended") == 1
        assert len(
            [e for e in store.read_room_log(room.id) if e.kind == "user"]
        ) == 2

    @pytest.mark.asyncio
    async def test_message_during_chain_end_await_starts_new_chain(self, chain_team):
        """Decision 2.3：结束路径先释放认领再 await 事件 ⇒ 收尾期间新消息开新链。"""
        store, room, runner, resolver, _ = chain_team
        entered = asyncio.Event()
        gate = asyncio.Event()
        events: list[tuple[str, dict]] = []

        async def sink(event_type, data):
            events.append((event_type, data))
            if (
                event_type == "round_ended"
                and data.get("chain_continues") is False
                and str(data.get("chain_id", "")).endswith(":1")
            ):
                entered.set()
                await gate.wait()

        orch = RoomOrchestrator(
            store=store, resolver=resolver, runner=runner, on_event=sink
        )
        runner.default = _silent()

        first = asyncio.create_task(orch.submit_user_message(room.id, "第一条"))
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = asyncio.create_task(orch.submit_user_message(room.id, "第二条"))
        for _ in range(200):
            if any(
                event_type == "discussion_started"
                and str(data.get("chain_id", "")).endswith(":2")
                for event_type, data in events
            ):
                break
            await asyncio.sleep(0)
        gate.set()
        first_result = await first
        second_result = await second

        assert first_result.chain_id == f"{room.id}:1"
        assert second_result.chain_id == f"{room.id}:2"
        assert second_result.queued is False
        assert first_result.discussion_reason == "converged"
        assert second_result.discussion_reason == "converged"
        assert orch.is_round_active(room.id) is False


class TestDiscussionSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_round_and_reason_lifecycle(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        gate_runner = GateRunner()
        orch = _evented(store, resolver, runner=gate_runner)
        assert orch.discussion_snapshot(room.id) == {"round": 0, "reason": None}

        gate_runner.push("room-pA", _text("R1"))
        gate_runner.default = _silent()
        block = gate_runner.block("room-pA", 1)
        task = asyncio.create_task(orch.submit_user_message(room.id, "开始讨论"))
        await asyncio.wait_for(block.entered.wait(), timeout=2)
        assert orch.discussion_snapshot(room.id) == {"round": 1, "reason": None}
        block.release.set()
        result = await task

        assert result.discussion_reason == "converged"
        assert orch.discussion_snapshot(room.id) == {
            "round": 0, "reason": "converged",
        }

    @pytest.mark.asyncio
    async def test_single_room_snapshot_stays_zero(self, team):
        store, room, runner, resolver, _ = team
        orch = _evented(store, resolver, runner)
        runner.default = _silent()
        await orch.submit_user_message(room.id, "开始")
        assert orch.discussion_snapshot(room.id) == {"round": 0, "reason": None}


class TestReviewSinkPerRound:
    @pytest.mark.asyncio
    async def test_review_runs_once_per_round_before_round_ended(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        order: list[str] = []

        class RecordingReview:
            async def on_member_turn(self, *, room_id, persona_id, outcome):
                return None

            async def on_round_end(self, *, room_id):
                order.append("review")

        async def sink(event_type, data):
            if event_type == "round_ended":
                order.append("round_ended")

        orch = RoomOrchestrator(
            store=store,
            resolver=resolver,
            runner=runner,
            review_sink=RecordingReview(),
            on_event=sink,
        )
        runner.push("room-pA", _text("R1"))
        runner.default = _silent()
        result = await orch.submit_user_message(room.id, "开始讨论")

        assert result.discussion_reason == "converged"
        assert order == ["review", "round_ended", "review", "round_ended"]

    @pytest.mark.asyncio
    async def test_raising_review_does_not_break_chain(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        calls = 0

        class RaisingReview:
            async def on_member_turn(self, *, room_id, persona_id, outcome):
                return None

            async def on_round_end(self, *, room_id):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("review boom")

        orch = _evented(store, resolver, runner, review_sink=RaisingReview())
        runner.push("room-pA", _text("R1"))
        runner.default = _silent()

        result = await orch.submit_user_message(room.id, "开始讨论")

        assert calls == 2
        assert result.discussion_reason == "converged"
        assert result.rounds == 2


class TestChainAccounting:
    @pytest.mark.asyncio
    async def test_chain_id_is_monotonic_per_room(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        orch = _evented(store, resolver, runner)
        runner.default = _silent()          # 第 1 轮全静默 → 每链 1 轮收敛

        first = await orch.submit_user_message(room.id, "第一条")
        second = await orch.submit_user_message(room.id, "第二条")

        assert first.chain_id == f"{room.id}:1"
        assert second.chain_id == f"{room.id}:2"
        assert [data["chain_id"] for data in orch.by_type("discussion_ended")] == [
            f"{room.id}:1", f"{room.id}:2",
        ]

    @pytest.mark.asyncio
    async def test_elapsed_seconds_uses_injected_clock(self, chain_team):
        store, room, runner, resolver, _ = chain_team
        clock = FakeClock(500.0)
        ticking = TickingRunner(clock, 5.0)
        orch = _evented(store, resolver, ticking, clock=clock)
        ticking.default = _silent()         # 全静默：1 轮 3 个回合后收敛

        result = await orch.submit_user_message(room.id, "开始讨论")

        ended = orch.by_type("discussion_ended")
        assert ended[0]["elapsed_seconds"] == 15.0
        assert ended[0]["turns"] == 3
        assert ended[0]["rounds"] == 1
        assert ended[0]["rounds_started"] == 1
        assert result.rounds == 1


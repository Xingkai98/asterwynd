# tests/agent/team/test_roomlog.py
"""房间日志的 schema、游标与有界切片（tasks 2.2 的日志部分 / 3.5）。

关键断言是 design Decision 6 的「静默回合也推进游标、不重复注入」：注入游标在
**回合开始**推进，而不是「上次发言之后」。
"""
from pathlib import Path

from agent.team.models import Persona, Room
from agent.team.roomlog import (
    ROOM_DELTA_MAX,
    ROOM_EARLIER_MAX,
    ROOM_FIRST_LOOK,
    RoomLog,
)
from agent.team.store import TeamStore


def _setup(tmp_path: Path, members: list[str]) -> tuple[TeamStore, Room, RoomLog]:
    store = TeamStore(tmp_path)
    for mid in members:
        store.upsert_persona(Persona(name=mid, id=mid))
    room = Room(name="r", members=list(members))
    store.save_room(room)
    return store, room, RoomLog(store, room.id, time_source=lambda: "t")


class TestSchema:
    def test_entries_carry_seq_speaker_kind_text_ts(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1", "p2"])
        log.append_user("hello")
        log.append_post("p1", "hi there")
        log.append_system("因达上限结束")

        entries = log.entries()
        assert [e.seq for e in entries] == [1, 2, 3]
        assert entries[0].speaker == "user" and entries[0].kind == "user"
        assert entries[1].speaker == "p1" and entries[1].kind == "post"
        assert entries[2].speaker is None and entries[2].kind == "system"
        assert all(e.ts for e in entries)
        assert all(isinstance(e.text, str) for e in entries)

    def test_seq_is_monotonic_across_reopen(self, tmp_path):
        store, room, log = _setup(tmp_path, ["p1"])
        log.append_user("a")
        reopened = RoomLog(store, room.id, time_source=lambda: "t")
        reopened.append_user("b")
        assert [e.seq for e in reopened.entries()] == [1, 2]
        assert reopened.seq == 2

    def test_unknown_kind_rejected(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1"])
        try:
            log.append(speaker="x", kind="notice", text="t")
        except ValueError:
            return
        raise AssertionError("unknown kind must be rejected")

    def test_full_log_is_retained(self, tmp_path):
        """Decision 17：房间日志 SHALL 保留全部条目（不做 60 条滚动）。"""
        _, _, log = _setup(tmp_path, ["p1"])
        for i in range(200):
            log.append_user(f"m{i}")
        assert len(log.entries()) == 200
        assert log.seq == 200


class TestInjectionSlice:
    def test_first_look_is_capped(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1"])
        for i in range(30):
            log.append_user(f"m{i}")
        view = log.build_injection("p1", round_start=1)
        assert view["first_look"] is True
        assert len(view["current"]) + len(view["earlier"]) == ROOM_FIRST_LOOK

    def test_delta_is_capped_and_excludes_own_posts(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1", "p2"])
        log.advance_seen("p1")            # 建立游标（此刻 seq = 0）
        for i in range(40):
            log.append_user(f"m{i}")
            log.append_post("p1", f"own {i}")
        view = log.build_injection("p1", round_start=1)
        lines = view["earlier"] + view["current"]
        assert len(lines) == ROOM_DELTA_MAX
        assert all(e.speaker != "p1" for e in lines)
        # 取的是最近的一段（往尾部对齐）
        assert lines[-1].text == "m39"

    def test_earlier_and_current_split_by_round_start(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1"])
        log.advance_seen("p1")
        for i in range(20):
            log.append_user(f"old{i}")
        round_start = log.seq + 1
        for i in range(3):
            log.append_user(f"now{i}")
        view = log.build_injection("p1", round_start=round_start)
        assert [e.text for e in view["current"]] == ["now0", "now1", "now2"]
        assert len(view["earlier"]) == ROOM_EARLIER_MAX
        assert view["earlier"][-1].text == "old19"

    def test_spoke_this_round_flag(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1"])
        log.append_user("opening")
        round_start = log.seq         # 开局条目就是本轮的第一条
        # 还没被轮到过：上一次的游标来自更早的回合（首见 → None）。取注入时看到开局条目。
        assert log.build_injection("p1", round_start=round_start)["spoke_this_round"] is False
        log.advance_seen("p1")        # 本轮第一次轮到 → 游标推到开局之后
        view = log.build_injection("p1", round_start=round_start)
        assert view["spoke_this_round"] is True
        assert view["current"] == []  # 自己已经看过的内容不再重复注入


class TestCursorAdvancesOnSilentTurns:
    """Scenario「静默成员的切片游标仍推进」（Decision 6）。"""

    def test_silent_turn_still_advances_and_never_repeats(self, tmp_path):
        _, _, log = _setup(tmp_path, ["p1", "p2"])
        log.append_user("first")

        # 回合 1：p1 被轮到（不管它是否静默），回合开始推进游标。
        view1 = log.build_injection("p1", round_start=1)
        assert [e.text for e in view1["current"]] == ["first"]
        log.advance_seen("p1")

        # 回合 2：没有任何新内容 → 看不到任何东西（不重复注入 "first"）。
        view2 = log.build_injection("p1", round_start=log.seq)
        assert view2["current"] == [] and view2["earlier"] == []

        # 有新增时只看到新增。
        log.append_post("p2", "second")
        view3 = log.build_injection("p1", round_start=log.seq)
        assert [e.text for e in view3["current"]] == ["second"]

    def test_advance_seen_without_room_is_noop(self, tmp_path):
        store = TeamStore(tmp_path)
        log = RoomLog(store, "missing", time_source=lambda: "t")
        log.advance_seen("p1")           # 不抛
        assert log.seen_cursor("p1") is None

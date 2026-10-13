"""房间日志的时序语义：游标推进与有界切片注入（design Decision 6）。

房间日志是群时间线的**唯一权威**（``Message`` 无 timestamp/speaker，合并 N 份
per-session 历史还原不出有序群时间线）。本模块在 ``store`` 的裸读写之上加两件事：

1. **持久化游标 ``seen[member]``**——在**回合开始**推进（含静默/超时回合）。
   若按「上次发言之后」推进，连续静默的成员切片边界永不前进 ⇒ 同一段内容被反复
   重复注入，上下文随静默次数无界增长（与 issue #278「上下文无界」同类风险）。
2. **三层有界切片**：首见 12 / 单次增量 24 / 往轮上下文 8，且把「本轮」与
   「往轮（仅上下文）」分开标注（与参照同形，``ds-bot/src/host/groups.js:21-23``）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from agent.team.models import ENTRY_KINDS, RoomEntry
from agent.team.store import TeamStore

#: 首见（该成员在该群还没有游标）时注入的日志条数上限。
ROOM_FIRST_LOOK = 12
#: 单次增量注入的条数上限。
ROOM_DELTA_MAX = 24
#: 「往轮」上下文（仅供理解，不属于本轮）的条数上限。
ROOM_EARLIER_MAX = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoomLog:
    """一个房间的日志视图：追加、游标、有界切片。"""

    def __init__(
        self,
        store: TeamStore,
        room_id: str,
        *,
        time_source: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self.room_id = room_id
        self._time_source = time_source or _now_iso

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------

    def entries(self) -> list[RoomEntry]:
        return self._store.read_room_log(self.room_id)

    @property
    def seq(self) -> int:
        entries = self.entries()
        return entries[-1].seq if entries else 0

    def append(
        self,
        *,
        speaker: str | None,
        kind: str,
        text: str,
        ts: str | None = None,
    ) -> RoomEntry:
        """追加一条条目。``system`` 条目 SHALL 由调用方给 ``speaker=None``。"""
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown room log kind: {kind!r}")
        return self._store.append_room_log(
            self.room_id,
            speaker=speaker,
            kind=kind,
            text=text,
            ts=ts or self._time_source(),
        )

    def append_user(self, text: str) -> RoomEntry:
        return self.append(speaker="user", kind="user", text=text)

    def append_post(self, persona_id: str, text: str) -> RoomEntry:
        return self.append(speaker=persona_id, kind="post", text=text)

    def append_system(self, text: str) -> RoomEntry:
        return self.append(speaker=None, kind="system", text=text)

    # ------------------------------------------------------------------
    # 游标
    # ------------------------------------------------------------------

    def seen_cursor(self, persona_id: str) -> int | None:
        """该成员当前的注入游标；``None`` 表示「首见」（还没有游标）。"""
        room = self._store.get_room(self.room_id)
        if room is None:
            return None
        value = room.seen.get(persona_id, None)
        return None if value is None else int(value)

    def advance_seen(self, persona_id: str) -> None:
        """把该成员的注入游标推进到当前 seq（**回合开始**调用，含静默/超时回合）。"""
        room = self._store.get_room(self.room_id)
        if room is None:
            return
        room.seen[persona_id] = self.seq
        self._store.save_room(room)

    # ------------------------------------------------------------------
    # 有界切片
    # ------------------------------------------------------------------

    def build_injection(
        self,
        persona_id: str,
        *,
        round_start: int,
    ) -> dict:
        """该成员本轮应看到的切片（**不**推进游标；调用方随后 ``advance_seen``）。

        ``round_start`` 是本轮开局条目的 seq：``seq >= round_start`` 的算「本轮」，
        更早的算「往轮（仅上下文）」。
        """
        seen = self.seen_cursor(persona_id)
        all_entries = self.entries()
        if seen is None:
            lines = all_entries[-ROOM_FIRST_LOOK:]
            first_look = True
        else:
            lines = [
                e for e in all_entries if e.seq > seen and e.speaker != persona_id
            ][-ROOM_DELTA_MAX:]
            first_look = False
        earlier = [e for e in lines if e.seq < round_start][-ROOM_EARLIER_MAX:]
        current = [e for e in lines if e.seq >= round_start]
        return {
            "earlier": earlier,
            "current": current,
            "first_look": first_look,
            # 「本轮已发过言」的判定基准是**回合开始前**的游标：它已经 >= 开局 seq
            # 说明该成员在本轮开局之后被轮到过（参照 ``spokeThisRound``）。
            "spoke_this_round": seen is not None and seen >= round_start,
        }


def render_lines(entries: list[RoomEntry], *, speaker_names: dict[str, str]) -> str:
    """把条目渲染成给模型的转写文本。

    ``post`` 条目带发言者名；``system`` 条目带 ``[系统]`` 前缀（避免读成某个成员
    的发言）；``user`` 条目带 ``User`` 前缀。
    """
    parts: list[str] = []
    for entry in entries:
        if entry.kind == "system":
            parts.append(f"[system] {entry.text}")
        elif entry.kind == "user":
            parts.append(f"User: {entry.text}")
        else:
            name = speaker_names.get(entry.speaker or "", entry.speaker or "")
            parts.append(f"{name}: {entry.text}")
    return "\n".join(parts)

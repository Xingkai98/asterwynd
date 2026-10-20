"""会话式群聊轮次编排器（design Decision 3 / 5 / 10 / 11 / 13 / 16）。

与既有 DAG 调度器（``agent/subagent/scheduler.py``，节点种类封闭四值）**并列**，
不复用 ``SubAgentManager``：本编排器是「长期存在、面向用户、可交互轮次」的形态，
把「轮次 + ``@`` 接力 + 用户中途插话」塞进 DAG 会同时破坏两套语义。

钉死的语义（全部来自 design）：

- **slot 序列**：开局 = 用户消息**行首** ``@Name``（按出现顺序、去重）→ 否则房间
  ``admin`` → 否则 roster 首个 ``mainBot`` → 否则成员顺序。成员发言**句中**的
  ``@Name`` 追加到**当前位次之后**（去重、非本群成员或自己忽略且不报错）。
- **每轮上限** = 开局 slot 数 + 固定额外轮次（有 admin 再加固定额度），并按成员
  分别计数封顶。上限按**开局** slot 数计算，轮次中到达的用户消息 SHALL NOT 改基。
- **静默**：成员回复哨兵文本（``[PASS]``）即不发言，轮次继续。
- **轮次终止三出口**：走完 / 达上限（记 ``system``）/ 全部剩余成员失败或超时。
  首版**不提供**轮次取消出口；系统 SHALL NOT 在用户再次发言前自行开启新一轮。
- **房间级互斥**：同一房间同一时刻至多一轮；轮次进行中到达的用户消息只追加进
  房间日志（其行首 ``@`` 追加为当前位次之后的 slot），SHALL NOT 并行开第二轮。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from agent.team.member_status import MemberStatus, reduce_signal
from agent.team.models import Persona, Room, RoomEntry
from agent.team.roomlog import RoomLog, render_lines
from agent.team.runner import (
    DEFAULT_TURN_TIMEOUT_SECONDS,
    SILENT_MARKER,
    SessionRunner,
    TurnOutcome,
)
from agent.team.sessions import SessionResolver
from agent.team.store import TeamStore

logger = logging.getLogger("asterwynd.team.orchestrator")

#: 每轮固定额外轮次（与参照 ``ROOM_EXTRA_TURNS`` 同值）。
ROOM_EXTRA_TURNS = 4
#: 群有 admin 时再加的固定额度（与参照 ``ROOM_ADMIN_EXTRA_TURNS`` 同值）。
ROOM_ADMIN_EXTRA_TURNS = 4
#: 普通成员每轮发言上限（参照 ``ROOM_TURNS_EACH``）。
ROOM_TURNS_EACH = 2
#: admin 每轮发言上限（参照 ``ROOM_ADMIN_TURNS_EACH``）。
ROOM_ADMIN_TURNS_EACH = 4

#: 轮次终止口径。
TERMINATION_COMPLETED = "completed"
TERMINATION_LIMIT = "limit"
TERMINATION_ALL_FAILED = "all_failed"
TERMINATION_QUEUED = "queued"

#: 达上限时写入房间日志的系统条目文案（spec delta 钉死的可测口径）。
LIMIT_ENTRY_TEXT = "本轮因达上限结束"

#: 成员发言提示（末行，哨兵文本在这里被要求）。
ROOM_REPLY_INSTRUCTION = (
    "Reply with your message for the group: one or two short messages, "
    "no name prefix. Reply [PASS] to stay silent when you have nothing new "
    "to add or the message is for someone else."
)


@dataclass
class RoundResult:
    """一次 ``submit_user_message`` 的结果。"""

    room_id: str
    queued: bool
    termination: str
    posts: list[RoomEntry] = field(default_factory=list)
    systems: list[RoomEntry] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    limit: int = 0


class ReviewSink(Protocol):
    """记忆 review 侧的回调（Decision 17）。实现方 SHALL 非阻塞地排队。"""

    async def on_member_turn(
        self, *, room_id: str, persona_id: str, outcome: TurnOutcome
    ) -> None:
        ...

    async def on_round_end(self, *, room_id: str) -> None:
        ...


def parse_mentions(
    text: str,
    name_index: dict[str, str],
    *,
    leading_only: bool,
) -> list[str]:
    """解析 ``@`` 点名，返回被点者（按出现顺序、去重）的 persona id。

    ``name_index`` 是 ``显示名 → persona id``。长名优先匹配（``@Mx`` 不会被读成
    ``@M``）；``@`` 前一个字符是字母数字/``_.`` 时不算点名；名字后紧跟字母数字/``-_``
    时也不算（``@Kai`` 不是 ``@K``）。

    ``leading_only=True`` 只认**消息开头的点名块**（用户消息口径：``@A @B 正文``）；
    成员发言用 ``False``（句中 ``@`` 也触发接力）。
    """
    if not text:
        return []
    region = _leading_block(text) if leading_only else text
    if not region:
        return []
    by_length = sorted(name_index.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    found: list[str] = []
    at = region.find("@")
    while at != -1:
        prev = region[at - 1] if at > 0 else ""
        if prev and (prev.isalnum() or prev in "_."):
            at = region.find("@", at + 1)
            continue
        rest = region[at + 1:]
        for name, persona_id in by_length:
            if not name or not rest.lower().startswith(name.lower()):
                continue
            after = rest[len(name):]
            if after[:1] and (after[0].isalnum() or after[0] in "_-"):
                continue
            if persona_id not in found:
                found.append(persona_id)
            break
        at = region.find("@", at + 1)
    return found


def _leading_block(text: str) -> str:
    """消息开头的「点名块」：连续的 ``@名字``（分隔符只有空白与常见标点）。"""
    i = 0
    n = len(text)
    while i < n:
        j = i
        while j < n and (text[j].isspace() or text[j] in "，,、;；"):
            j += 1
        if j < n and text[j] == "@":
            k = j + 1
            while k < n and (text[k].isalnum() or text[k] in "_-"):
                k += 1
            if k > j + 1:
                i = k
                continue
        break
    return text[:i]


def opening_slots(
    room: Room, text: str, roster: dict[str, Persona], main_bot_ids: list[str]
) -> list[str]:
    """本轮的初始 slot 序列（design Decision 11，钉死顺序）。

    行首 ``@Name`` 在**两种应答模式下都优先**（Decision 19 只改「无 `@` 时的默认
    应答者」）。无 `@` 时按 ``room.reply_mode`` 分支：

    - ``admin``（缺省）：房间 admin → 无 admin 则 roster 首个 ``mainBot`` → 无
      ``mainBot`` 则成员顺序；
    - ``everyone``：全体成员按序各得一次机会（**admin 先**），各自可静默。
    """
    name_index = _name_index(room, roster)
    mentioned = [
        pid
        for pid in parse_mentions(text, name_index, leading_only=True)
        if pid in room.members
    ]
    if mentioned:
        return mentioned
    if room.reply_mode == "everyone":
        if room.admin and room.admin in room.members:
            return [room.admin] + [m for m in room.members if m != room.admin]
        return list(room.members)
    if room.admin and room.admin in room.members:
        return [room.admin]
    for pid in main_bot_ids:
        if pid in room.members:
            return [pid]
    return list(room.members)


def _name_index(room: Room, roster: dict[str, Persona]) -> dict[str, str]:
    index: dict[str, str] = {}
    for pid in room.members:
        persona = roster.get(pid)
        if persona is None or not persona.name:
            continue
        index.setdefault(persona.name, pid)
    return index


def build_member_prompt(
    *,
    room: Room,
    persona_id: str,
    roster: dict[str, Persona],
    view: dict,
    slot_index: int,
    slot_total: int,
) -> str:
    """构造该成员本轮的 user 消息：成员名单 + 群 notice + 切片 + 发言位次 + 哨兵。"""
    peers = [
        roster[pid].name
        for pid in room.members
        if pid != persona_id and pid in roster and roster[pid].name
    ]
    is_admin = room.admin == persona_id
    lines = [f"Members: the user, {', '.join(peers)} and you{' (admin)' if is_admin else ''}."]

    if room.notice:
        lines.append(
            "Group notice (shared instructions for every member):\n" + room.notice
        )

    names = {pid: p.name for pid, p in roster.items()}
    earlier = render_lines(view["earlier"], speaker_names=names)
    current = render_lines(view["current"], speaker_names=names)
    if earlier:
        lines.append(
            "Earlier in the group, before this round (context only):\n" + earlier
        )
    if current:
        head = (
            "This round so far, since your last message"
            if view["spoke_this_round"]
            else "This round so far, starting with the new message"
        )
        lines.append(f"{head} (oldest first):\n" + current)
    else:
        lines.append("Nothing new in this round since your last message.")

    order = [
        (roster[pid].name if pid in roster and roster[pid].name else pid)
        for pid in room.members
    ]
    lines.append("Speaking order for this round follows the group's member list: " + ", ".join(order))
    before = slot_index
    after = max(0, slot_total - slot_index - 1)
    position = [
        f"You are number {slot_index + 1} of {slot_total}.",
        "Nobody spoke before you" if before == 0 else f"{before} went before you",
    ]
    tail = (
        ", and you are the last." if after == 0
        else f"; {after} after you will see your message."
    )
    lines.append(" ".join(position) + tail)
    lines.append(ROOM_REPLY_INSTRUCTION)
    return "\n\n".join(lines)


@dataclass
class _RoundState:
    room_id: str
    start_seq: int
    slots: list[str]
    index: int = 0
    turns: int = 0
    limit: int = 0
    per_member_turns: dict[str, int] = field(default_factory=dict)
    posts: list[RoomEntry] = field(default_factory=list)
    systems: list[RoomEntry] = field(default_factory=list)
    failures: int = 0


class RoomOrchestrator:
    """房间级轮次编排。**不 import web**——依赖由 web 层注入。"""

    def __init__(
        self,
        *,
        store: TeamStore,
        resolver: SessionResolver,
        runner: SessionRunner,
        turn_timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,
        extra_turns: int = ROOM_EXTRA_TURNS,
        admin_extra_turns: int = ROOM_ADMIN_EXTRA_TURNS,
        turns_each: int = ROOM_TURNS_EACH,
        admin_turns_each: int = ROOM_ADMIN_TURNS_EACH,
        review_sink: ReviewSink | None = None,
        on_event: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._runner = runner
        self._turn_timeout = turn_timeout
        self._extra_turns = extra_turns
        self._admin_extra_turns = admin_extra_turns
        self._turns_each = turns_each
        self._admin_turns_each = admin_turns_each
        self._review_sink = review_sink
        self._on_event = on_event
        self._rounds: dict[str, _RoundState] = {}
        #: 每房间的完整非空闲状态表 / 房间级单调序号 / 待发射标记 / 在途发射任务。
        self._statuses: dict[str, dict[str, MemberStatus]] = {}
        self._status_seq: dict[str, int] = {}
        self._status_dirty: dict[str, set[str]] = {}
        self._status_tasks: dict[str, asyncio.Task] = {}
        #: 取消/异常 teardown 的后台 task 强引用（事件循环不回收在途 task）。
        self._teardown_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def is_round_active(self, room_id: str) -> bool:
        return room_id in self._rounds

    def log_for(self, room_id: str) -> RoomLog:
        return RoomLog(self._store, room_id)

    async def submit_user_message(self, room_id: str, text: str) -> RoundResult:
        """用户消息入口：开一轮，或排队进入正在进行的轮次（房间级互斥）。

        **不用锁**：``_rounds`` 的「查—建」之间没有 ``await`` 点（asyncio 单线程
        事件循环下是原子的），与既有 ``run_session`` 的 ``run_lock.locked()``
        检查同一论证。锁会把整轮圈住，导致轮次中到达的消息在轮后才被处理、
        进而**另开一轮**——正是 Decision 5 要禁止的。
        """
        room = self._store.get_room(room_id)
        if room is None:
            raise KeyError(f"unknown room: {room_id}")
        active = self._rounds.get(room_id)
        if active is not None:
            # 轮次进行中：只追加进房间日志 + 行首 @ 追加为当前位次之后的 slot。
            entry = self.log_for(room_id).append_user(text)
            self._append_called_slots(active, room, text)
            await self._emit("user_message", {
                "room_id": room_id, "text": text, "seq": entry.seq, "queued": True,
            })
            return RoundResult(
                room_id=room_id,
                queued=True,
                termination=TERMINATION_QUEUED,
                slots=list(active.slots),
                limit=active.limit,
            )
        return await self._run_round(room, text)

    # ------------------------------------------------------------------
    # 轮次驱动
    # ------------------------------------------------------------------

    async def _run_round(self, room: Room, opening_text: str) -> RoundResult:
        log = self.log_for(room.id)
        roster = {p.id: p for p in self._store.list_personas()}
        slots = opening_slots(room, opening_text, roster, self._store.main_bot_ids())
        limit = len(slots) + self._extra_turns + (
            self._admin_extra_turns if room.admin else 0
        )
        state = _RoundState(room_id=room.id, start_seq=0, slots=slots, limit=limit)
        # **认领必须发生在任何 await 之前**（I2）：房间级互斥靠的是「查—建之间没有
        # await 点」这条论证，而下面的 `_emit` 在生产路径必然挂起（房间 WS 的
        # `await ws.send_json`）——若把注册放在它之后，同 tick 的第二次提交会看到
        # `_rounds` 仍是空的，于是两轮并存（正是 Decision 5 要禁止的），且第二轮会
        # 覆盖第一轮的 state、让 `is_round_active` 在轮中报 false。
        self._rounds[room.id] = state
        teardown_seq: int | None = None
        try:
            entry = log.append_user(opening_text)      # 同步：不引入 await
            state.start_seq = entry.seq
            await self._emit("user_message", {
                "room_id": room.id, "text": opening_text, "seq": entry.seq,
                "queued": False,
            })
            await self._drive(state)

            # termination 与 limit system 条目在任何 reset/pop/await 之前同步完成：
            # 它们一定排在任何新一轮用户消息之前。
            if state.turns >= state.limit and state.index < len(state.slots):
                state.systems.append(log.append_system(LIMIT_ENTRY_TEXT))
                termination = TERMINATION_LIMIT
            elif not state.posts and state.failures:
                termination = TERMINATION_ALL_FAILED
            else:
                termination = TERMINATION_COMPLETED

            # 先同步重置并释放认领（两者之间无 await），再 flush / review / 终态。
            # 释放后新一轮可以启动；旧终态 seq 更低，客户端会丢弃。
            teardown_seq = self._reset_room_statuses(room.id)
            self._release_round(room.id, state)
            await self._flush_status_emits(room.id)

            if self._review_sink is not None:
                try:
                    await self._review_sink.on_round_end(room_id=room.id)
                except Exception:  # noqa: BLE001 - review 失败 SHALL NOT 中断轮次
                    logger.exception("记忆 review 的落后补齐调度失败（已忽略）")

            await self._emit("round_ended", {
                "room_id": room.id,
                "termination": termination,
                "limit": state.limit,
                "status_seq": teardown_seq,
            })
            return RoundResult(
                room_id=room.id,
                queued=False,
                termination=termination,
                posts=list(state.posts),
                systems=list(state.systems),
                slots=list(state.slots),
                limit=state.limit,
            )
        except asyncio.CancelledError:
            if self._rounds.get(room.id) is state:
                if teardown_seq is None:
                    teardown_seq = self._reset_room_statuses(room.id)
                self._schedule_teardown(
                    room.id, teardown_seq, "cancelled", state.limit
                )
            raise
        except Exception:
            if self._rounds.get(room.id) is state:
                if teardown_seq is None:
                    teardown_seq = self._reset_room_statuses(room.id)
                self._schedule_teardown(room.id, teardown_seq, "error", state.limit)
            logger.exception("群聊轮次异常终止（已尽力通知房间）")
            raise
        finally:
            if teardown_seq is None and self._rounds.get(room.id) is state:
                self._reset_room_statuses(room.id)
            self._release_round(room.id, state)

    async def _drive(self, state: _RoundState) -> None:
        while state.index < len(state.slots):
            if state.turns >= state.limit:
                return
            persona_id = state.slots[state.index]
            await self._run_slot(state, persona_id)
            state.index += 1

    async def _run_slot(self, state: _RoundState, persona_id: str) -> None:
        log = self.log_for(state.room_id)
        # 成员中途变更（被移出房间）→ 跳过该 slot（参照的 ``left`` 出口）。
        room = self._store.get_room(state.room_id)
        if room is None or persona_id not in room.members:
            await self._emit("slot_skipped", {
                "room_id": state.room_id, "persona_id": persona_id, "reason": "left",
            })
            return

        roster = {p.id: p for p in self._store.list_personas()}
        persona = roster.get(persona_id)
        name = persona.name if persona and persona.name else persona_id

        # slot 认领即 running：覆盖 ensure_room_session / prompt 构造的空窗。
        self._set_signal(state.room_id, persona_id, "slot_started", {})
        try:
            try:
                session_id = await self._resolver.ensure_room_session(
                    state.room_id, persona_id
                )
            except Exception as exc:  # noqa: BLE001 - 单个成员建会话失败不挂死整轮
                logger.warning("成员 %s 的群内会话创建失败: %s", persona_id, exc)
                state.failures += 1
                state.systems.append(
                    log.append_system(f"成员 {name} 运行失败：会话不可用")
                )
                await self._finish_member(
                    state.room_id, persona_id, "member_failed",
                    {"status": "failed", "reason": "会话不可用", "name": name},
                )
                return

            # 回合开始：先读切片（用**旧**游标），再推进游标（含静默/超时回合）。
            view = log.build_injection(persona_id, round_start=state.start_seq)
            log.advance_seen(persona_id)

            prompt = build_member_prompt(
                room=room,
                persona_id=persona_id,
                roster=roster,
                view=view,
                slot_index=state.index,
                slot_total=len(state.slots),
            )
            state.turns += 1
            state.per_member_turns[persona_id] = (
                state.per_member_turns.get(persona_id, 0) + 1
            )

            await self._emit("member_speaking", {
                "room_id": state.room_id, "persona_id": persona_id, "name": name,
                "status_seq": self._status_seq.get(state.room_id, 0),
            })

            async def on_progress(kind: str, data: dict) -> None:
                self._set_signal(state.room_id, persona_id, kind, data or {})

            outcome = await self._runner.run(
                session_id, prompt,
                timeout=self._turn_timeout,
                silent_marker=SILENT_MARKER,
                on_progress=on_progress,
            )

            if outcome.status == "silent":
                await self._finish_member(
                    state.room_id, persona_id, "member_silent", {}
                )
            elif outcome.status in ("failed", "timeout"):
                state.failures += 1
                reason = "超时" if outcome.status == "timeout" else (
                    outcome.message or outcome.code or "运行失败"
                )
                state.systems.append(
                    log.append_system(f"成员 {name} 运行失败：{reason}")
                )
                await self._finish_member(
                    state.room_id, persona_id, "member_failed",
                    {
                        "status": outcome.status,
                        "reason": reason,
                        "name": name,
                    },
                )
            else:
                text = outcome.text.strip()
                if text:
                    entry = log.append_post(persona_id, text)
                    state.posts.append(entry)
                    await self._finish_member(
                        state.room_id, persona_id, "member_post",
                        {
                            "speaker": persona_id,
                            "text": text,
                            "seq": entry.seq,
                        },
                    )
                    self._append_called_slots(
                        state, room, text, speaker_id=persona_id
                    )
                else:
                    # 空产出等价于静默（不与 failed 混同：模型确实跑完了）。
                    # 生产 WebSessionRunner 已把空文本归一为 silent；这里是编排器层的
                    # 防御性契约，覆盖自定义 runner。
                    outcome = TurnOutcome(status="silent")
                    await self._finish_member(
                        state.room_id, persona_id, "member_silent", {}
                    )

            # review 排期**排在发言落日志之后**：review 读的是房间日志切片，先入日志
            # 才不会漏掉刚发出的这条（Decision 17：仅实际发言的回合触发）。
            if self._review_sink is not None:
                try:
                    await self._review_sink.on_member_turn(
                        room_id=state.room_id, persona_id=persona_id, outcome=outcome
                    )
                except Exception:  # noqa: BLE001 - review 排期失败 SHALL NOT 中断轮次
                    logger.exception("记忆 review 排期失败（已忽略）")
        finally:
            # 幂等兜底：任何遗漏出口/取消/意外异常都不把成员留在忙。
            self._reset_member(state.room_id, persona_id)

    # ------------------------------------------------------------------
    # 成员运行状态（change web-agent-group-member-status）
    # ------------------------------------------------------------------

    def _status_table(self, room_id: str) -> dict[str, MemberStatus]:
        return self._statuses.setdefault(room_id, {})

    def _set_signal(
        self, room_id: str, persona_id: str, kind: str, data: dict | None = None
    ) -> None:
        """同步归约一个进度信号；有变化才递增房间级 seq 并调度全量表事件。"""
        table = self._status_table(room_id)
        new = reduce_signal(table.get(persona_id), kind, data)
        if new is None:
            return
        if new.is_idle:
            table.pop(persona_id, None)
        else:
            table[persona_id] = new
        self._status_seq[room_id] = self._status_seq.get(room_id, 0) + 1
        self._mark_status_dirty(room_id, persona_id)

    def _mark_status_dirty(self, room_id: str, persona_id: str) -> None:
        self._status_dirty.setdefault(room_id, set()).add(persona_id)
        self._schedule_status_emit(room_id)

    def _schedule_status_emit(self, room_id: str) -> None:
        if self._on_event is None:
            return
        task = self._status_tasks.get(room_id)
        if task is not None and not task.done():
            return
        self._status_tasks[room_id] = asyncio.create_task(
            self._drain_status(room_id)
        )

    async def _drain_status(self, room_id: str) -> None:
        """合并发射：循环直到没有新变化；每次读取**当前完整表 + 当前 seq**。"""
        try:
            while True:
                dirty = self._status_dirty.pop(room_id, None)
                if not dirty:
                    break
                table = self._statuses.get(room_id, {})
                seq = self._status_seq.get(room_id, 0)
                statuses = [
                    status.as_dict(pid)
                    for pid, status in table.items()
                    if not status.is_idle
                ]
                await self._emit("member_status", {
                    "room_id": room_id,
                    "status_seq": seq,
                    "statuses": statuses,
                })
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 发射失败不得打断成员 run
            logger.exception("成员状态发射失败（已忽略）")
        finally:
            current = asyncio.current_task()
            if self._status_tasks.get(room_id) is current:
                self._status_tasks.pop(room_id, None)
            if self._status_dirty.get(room_id):
                self._schedule_status_emit(room_id)

    async def _flush_status_emits(self, room_id: str) -> None:
        """等待当前在途的发射任务完成；测试与终态顺序的确定性抓手。"""
        for _ in range(10):
            task = self._status_tasks.get(room_id)
            if task is not None and not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("等待成员状态发射失败（已忽略）")
                continue
            if self._status_dirty.get(room_id):
                self._schedule_status_emit(room_id)
                task = self._status_tasks.get(room_id)
                if task is not None and not task.done():
                    continue
            break

    def _reset_member(self, room_id: str, persona_id: str) -> int:
        """幂等重置一个成员：表未变时返回当前 seq，不递增、不标脏。"""
        table = self._statuses.get(room_id)
        if table and persona_id in table:
            table.pop(persona_id, None)
            self._status_seq[room_id] = self._status_seq.get(room_id, 0) + 1
            self._mark_status_dirty(room_id, persona_id)
        return self._status_seq.get(room_id, 0)

    def _reset_room_statuses(self, room_id: str) -> int:
        """幂等清空房间状态表：空表时返回当前 seq。"""
        table = self._statuses.get(room_id)
        if table:
            table.clear()
            self._status_seq[room_id] = self._status_seq.get(room_id, 0) + 1
            self._mark_status_dirty(room_id, "__room__")
        return self._status_seq.get(room_id, 0)

    def status_snapshot(self, room_id: str) -> tuple[list[dict], int]:
        """返回 (非空闲状态表副本, 当前房间级 seq)，供 room_state 使用。"""
        table = self._statuses.get(room_id, {})
        statuses = [
            status.as_dict(pid)
            for pid, status in table.items()
            if not status.is_idle
        ]
        return statuses, self._status_seq.get(room_id, 0)

    def _release_round(self, room_id: str, state: _RoundState) -> None:
        """仅当仍持有认领时才释放，避免误删 flush 期间启动的新轮。"""
        if self._rounds.get(room_id) is state:
            del self._rounds[room_id]

    async def _finish_member(
        self,
        room_id: str,
        persona_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """统一终态出口：同步重置 -> seq -> flush -> 用新 seq 发终态。"""
        seq = self._reset_member(room_id, persona_id)
        await self._flush_status_emits(room_id)
        payload = dict(data)
        payload.update({
            "room_id": room_id,
            "persona_id": persona_id,
            "status_seq": seq,
        })
        await self._emit(event_type, payload)

    def _schedule_teardown(
        self, room_id: str, status_seq: int, termination: str, limit: int
    ) -> None:
        """取消/意外异常的 status-only teardown；强引用后台 task + 有界等待。"""
        async def _run() -> None:
            try:
                await asyncio.wait_for(
                    self._flush_status_emits(room_id), timeout=2.0
                )
                await asyncio.wait_for(
                    self._emit("round_ended", {
                        "room_id": room_id,
                        "termination": termination,
                        "limit": limit,
                        "status_seq": status_seq,
                    }),
                    timeout=2.0,
                )
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("群聊轮次 teardown 超时（%s）", room_id)
            except Exception:  # noqa: BLE001 - teardown 尽力而为
                logger.exception("群聊轮次 teardown 失败（已忽略）")

        task = asyncio.create_task(_run())
        self._teardown_tasks.add(task)
        task.add_done_callback(self._teardown_tasks.discard)

    # ------------------------------------------------------------------
    # slot 追加（@ 接力）
    # ------------------------------------------------------------------

    def _append_called_slots(
        self,
        state: _RoundState,
        room: Room,
        text: str,
        *,
        speaker_id: str | None = None,
    ) -> None:
        """把 ``text`` 行首（用户）或句中（成员）点名的成员插到**当前位次之后**。

        用户消息用 ``leading_only=True``（spec 的「用户行首 @」口径），成员发言用
        ``False``（句中接力）。去重；不在本群成员 / 自己忽略且不报错；受每人每轮
        上限约束；SHALL NOT 改变本轮上限基数（``state.limit`` 在开局算定）。
        """
        roster = {p.id: p for p in self._store.list_personas()}
        name_index = _name_index(room, roster)
        mentioned = parse_mentions(
            text, name_index, leading_only=speaker_id is None
        )
        callees = [
            pid for pid in mentioned
            if pid in room.members and pid != speaker_id
        ]
        if not callees:
            return
        # 用户点名与 admin 点名用同一额度（参照的 ``ROOM_ADMIN_TURNS_EACH``）；
        # 普通成员点名的接力额度更紧（``ROOM_TURNS_EACH``），防成员之间互相点火。
        if speaker_id is None or room.admin == speaker_id:
            cap = self._admin_turns_each
        else:
            cap = self._turns_each
        next_pos = state.index + 1
        for pid in callees:
            if state.per_member_turns.get(pid, 0) >= cap:
                continue
            if pid in state.slots[next_pos:]:
                state.slots.pop(state.slots.index(pid, next_pos))
            state.slots.insert(next_pos, pid)
            next_pos += 1

    # ------------------------------------------------------------------

    async def _emit(self, event_type: str, data: dict) -> None:
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, data)
        except Exception:  # noqa: BLE001 - 事件出口尽力而为
            logger.exception("编排器事件推送失败（已忽略）")

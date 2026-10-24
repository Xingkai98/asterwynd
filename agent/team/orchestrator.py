"""会话式群聊轮次与讨论链编排器（design Decision 3 / 5 / 10 / 11 / 13 / 16）。

与既有 DAG 调度器（``agent/subagent/scheduler.py``，节点种类封闭四值）**并列**，
不复用 ``SubAgentManager``：本编排器是「长期存在、面向用户、可交互轮次」的形态，
把「轮次 + ``@`` 接力 + 用户中途插话」塞进 DAG 会同时破坏两套语义。

钉死的语义（全部来自 design）：

- **slot 序列**：开局 = 用户消息**行首** ``@Name``（按出现顺序、去重）→ 否则房间
  ``admin`` → 否则 roster 首个 ``mainBot`` → 否则成员顺序。成员发言**句中**的
  ``@Name`` 追加到**当前位次之后**（去重、非本群成员或自己忽略且不报错）。
- **每轮上限** = 开局 slot 数 + 固定额外轮次（有 admin 再加固定额度），并按成员
  分别计数封顶；``unlimited`` 下再与链剩余回合额度取 min。
- **静默**：成员回复哨兵文本（``[PASS]``）即不发言，轮次继续。
- **轮次终止三出口**：走完 / 达上限（记 ``system``）/ 全部剩余成员失败或超时。
- **讨论链**（change ``group-unlimited-discussion``）：``discussion_mode =
  unlimited`` 时房间认领升级为**整条讨论链**：一轮正常结束且本轮有人发言时自动
  续下一轮；某轮 0 发言 0 失败且无未消费用户消息 = 收敛；用户可请求停止；轮数 /
  回合 / 墙钟三档安全阀。``single``（缺省）保持原三出口与零事件变化。
- **房间级互斥**：同一房间同一时刻至多一条讨论；讨论进行中到达的用户消息只追加进
  房间日志（行首 ``@`` 追加为当前位次之后的 slot / 轮间窗口记入待应用点名），
  SHALL NOT 并行开启第二条讨论。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from agent.team.member_status import MemberStatus, reduce_signal
from agent.team.models import (
    DEFAULT_DISCUSSION_MODE,
    Persona,
    Room,
    RoomEntry,
)
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

#: 讨论模式取值（与 ``agent.team.models.DISCUSSION_MODES`` 同源）。
DISCUSSION_MODE_SINGLE = DEFAULT_DISCUSSION_MODE
DISCUSSION_MODE_UNLIMITED = "unlimited"

#: 讨论链安全阀缺省值（design Decision 6；``agent/config.py`` 的 ``TeamConfig``
#: 缺省值与之同值，由 web 层注入；这里保留构造器缺省以便独立使用编排器）。
DEFAULT_DISCUSSION_MAX_ROUNDS = 200
DEFAULT_DISCUSSION_MAX_TURNS = 600
DEFAULT_DISCUSSION_MAX_SECONDS = 6000.0

#: 轮次终止口径（``single`` 只用前三值；``stopped`` 仅 ``unlimited`` 产生）。
TERMINATION_COMPLETED = "completed"
TERMINATION_LIMIT = "limit"
TERMINATION_ALL_FAILED = "all_failed"
TERMINATION_STOPPED = "stopped"
TERMINATION_CANCELLED = "cancelled"
TERMINATION_ERROR = "error"
TERMINATION_QUEUED = "queued"

#: 讨论链结束原因（``discussion_ended.reason``，design Decision 3 优先级表）。
REASON_CONVERGED = "converged"
REASON_STOPPED = "stopped"
REASON_ALL_FAILED = "all_failed"
REASON_ROUND_LIMIT = "round_limit"
REASON_MAX_ROUNDS = "max_rounds"
REASON_MAX_TURNS = "max_turns"
REASON_MAX_SECONDS = "max_seconds"
REASON_MODE_CHANGED = "mode_changed"
REASON_COMPLETED = "completed"
REASON_CANCELLED = TERMINATION_CANCELLED
REASON_ERROR = TERMINATION_ERROR

#: 达上限时写入房间日志的系统条目文案（spec delta 钉死的可测口径）。
LIMIT_ENTRY_TEXT = "本轮因达上限结束"
#: 续轮系统条目文案（其 ``seq`` 作为该轮的 ``start_seq``）。
CONTINUE_ENTRY_TEXT = "讨论继续（第 {round_index} 轮）"
#: 链结束系统条目文案（design Decision 3 文案表；``completed`` / ``error`` 不写）。
CONVERGED_ENTRY_TEXT = "讨论已收敛（本轮全员静默）"
STOPPED_ENTRY_TEXT = "讨论已由用户停止"
ALL_FAILED_ENTRY_TEXT = "讨论已中止（本轮无人发言，存在失败）"
ROUND_LIMIT_ENTRY_TEXT = "讨论因本轮达上限结束"
MAX_LIMIT_ENTRY_TEXT = "讨论达安全上限结束"
MODE_CHANGED_ENTRY_TEXT = "讨论已结束（模式已变更）"
DISCONNECTED_ENTRY_TEXT = "讨论因页面断开而中止"

#: 链结束原因 → 房间日志 system 文案（``completed`` / ``error`` 明确不写）。
CHAIN_END_SYSTEM_TEXTS = {
    REASON_CONVERGED: CONVERGED_ENTRY_TEXT,
    REASON_STOPPED: STOPPED_ENTRY_TEXT,
    REASON_ALL_FAILED: ALL_FAILED_ENTRY_TEXT,
    REASON_ROUND_LIMIT: ROUND_LIMIT_ENTRY_TEXT,
    REASON_MAX_ROUNDS: MAX_LIMIT_ENTRY_TEXT,
    REASON_MAX_TURNS: MAX_LIMIT_ENTRY_TEXT,
    REASON_MAX_SECONDS: MAX_LIMIT_ENTRY_TEXT,
    REASON_MODE_CHANGED: MODE_CHANGED_ENTRY_TEXT,
    REASON_CANCELLED: DISCONNECTED_ENTRY_TEXT,
}

#: 成员发言提示（末行，哨兵文本在这里被要求）。
ROOM_REPLY_INSTRUCTION = (
    "Reply with your message for the group: one or two short messages, "
    "no name prefix. Reply [PASS] to stay silent when you have nothing new "
    "to add or the message is for someone else."
)

#: ``unlimited`` 第 1 轮的轮次上下文（design Decision 4，在
#: ``ROOM_REPLY_INSTRUCTION`` 之前追加；``single`` 逐字节不变）。
DISCUSSION_ROUND1_CONTEXT = (
    "Round 1 of a continuous discussion; every member speaks at most once "
    "per round."
)
#: ``unlimited`` 第 k>1 轮的轮次上下文。
DISCUSSION_CONTINUING_CONTEXT = (
    "Round {round_index} of a continuing discussion. There is no new user "
    "message this round; the discussion continues because the previous "
    "round produced new content."
)
#: ``unlimited`` 共同句：要求成员收敛即静默、不重复。
DISCUSSION_CONVERGENCE_HINT = (
    "If the discussion has converged or you have nothing new to add, reply "
    "[PASS] — do not repeat points already made; do not speak just to fill "
    "the round."
)


def discussion_prompt_context(round_index: int) -> str:
    """``unlimited`` 成员的轮次上下文（两段：轮次头 + 收敛要求）。"""
    if round_index <= 1:
        head = DISCUSSION_ROUND1_CONTEXT
    else:
        head = DISCUSSION_CONTINUING_CONTEXT.format(round_index=round_index)
    return head + "\n\n" + DISCUSSION_CONVERGENCE_HINT


@dataclass
class RoundResult:
    """一次 ``submit_user_message`` 的结果。

    ``single`` 模式下新增字段保持默认值（design Decision 9 / grill L11）；
    ``unlimited`` 下返回**最后收尾那一轮**的轮级载荷 + 链级统计。
    """

    room_id: str
    queued: bool
    termination: str
    posts: list[RoomEntry] = field(default_factory=list)
    systems: list[RoomEntry] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    limit: int = 0
    #: 讨论模式（``single`` / ``unlimited``）。
    discussion_mode: str = DISCUSSION_MODE_SINGLE
    #: 链结束原因（``single`` / 未开链时为 ``None``）。
    discussion_reason: str | None = None
    #: 讨论链标识（房间内单调 ``"<room_id>:<n>"``；``single`` 为 ``None``）。
    chain_id: str | None = None
    #: 已正常收尾的轮数（被停止打断的当前轮不计入）。
    rounds: int = 0
    #: 已进入的轮数（1-based 的最后轮序号）。
    rounds_started: int = 0


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

    ``unlimited`` 续轮 SHALL 传空 ``text``（grill I7）：否则开局行首 ``@`` 会让
    后续每轮只剩点名者。
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
    discussion_context: str | None = None,
) -> str:
    """构造该成员本轮的 user 消息：成员名单 + 群 notice + 切片 + 发言位次 + 哨兵。

    ``discussion_context`` 只在 ``discussion_mode = unlimited`` 时非空（design
    Decision 4），追加在 ``ROOM_REPLY_INSTRUCTION`` 之前；``single`` 模式不传，
    提示词逐字节与旧实现一致。
    """
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
    if discussion_context:
        lines.append(discussion_context)
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
    #: 本轮收尾同步区已执行（轮间窗口的判定依据）。
    closed: bool = False
    #: 本轮终态事件（``round_ended``）已发出；取消/异常 teardown 用它防重复。
    terminal_sent: bool = False


@dataclass(frozen=True)
class _DiscussionLimits:
    """链启动时从 ``TeamConfig`` 快照的三档安全阀（design Decision 6）。"""

    max_rounds: int
    max_turns: int
    max_seconds: float

    def as_dict(self) -> dict:
        return {
            "max_rounds": self.max_rounds,
            "max_turns": self.max_turns,
            "max_seconds": self.max_seconds,
        }


@dataclass
class _ChainState:
    """一条讨论链（design Decision 2）。房间认领的对象是它，而不是单轮 state。"""

    room_id: str
    chain_id: str
    discussion_mode: str
    started_at: float
    limits: _DiscussionLimits
    #: 认领后到链结束前**恒非 ``None``**：链认领与第 1 轮骨架在同一同步区建立。
    current: _RoundState
    rounds: list[_RoundState] = field(default_factory=list)
    round_index: int = 1
    turns: int = 0
    stop_requested: bool = False
    closing: bool = False
    #: 轮间窗口到达的用户行首 ``@``（被某轮开局 slot 消费后立即清空）。
    pending_mentions: list[str] = field(default_factory=list)
    #: 「尚无任何成员回合切片看到」的用户条目 ``seq``（到达即同步写入）。
    pending_user_seqs: list[int] = field(default_factory=list)


@dataclass
class _ChainEnd:
    """链结束的同步快照（事件 payload 由它 + ``chain`` 共同构造）。"""

    reason: str
    status_seq: int
    system_entry: RoomEntry | None = None
    elapsed_seconds: float = 0.0


@dataclass
class _ClosedRound:
    """一轮同步收尾的结果：``chain_end is None`` 表示续轮。"""

    termination: str
    status_seq: int
    chain_end: _ChainEnd | None


@dataclass
class _StartedRound:
    """续轮同步区建出的下一轮 + 它的「讨论继续（第 k 轮）」system 条目。"""

    state: _RoundState
    system_entry: RoomEntry


class RoomOrchestrator:
    """房间级轮次 / 讨论链编排。**不 import web**——依赖由 web 层注入。"""

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
        discussion_max_rounds: int = DEFAULT_DISCUSSION_MAX_ROUNDS,
        discussion_max_turns: int = DEFAULT_DISCUSSION_MAX_TURNS,
        discussion_max_seconds: float = DEFAULT_DISCUSSION_MAX_SECONDS,
        clock: Callable[[], float] = time.monotonic,
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
        #: 讨论链安全阀（design Decision 6）：构造期注入，链启动时快照。
        self._discussion_max_rounds = discussion_max_rounds
        self._discussion_max_turns = discussion_max_turns
        self._discussion_max_seconds = discussion_max_seconds
        #: 可注入时钟（测试用；缺省 ``time.monotonic``）。
        self._clock = clock
        #: 房间 → 当前讨论链（``single`` 也共用该外壳，统一释放/身份语义）。
        self._rounds: dict[str, _ChainState] = {}
        #: 房间内单调的讨论链序号（``chain_id = "<room_id>:<n>"``）。
        self._chain_seq: dict[str, int] = {}
        #: ``room_state`` 的讨论态快照宿主：``{room_id: {"round": int, "reason": ...}}``。
        self._discussion_state: dict[str, dict] = {}
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
        """该房间是否有进行中的讨论 / 轮次（链认领覆盖整条链）。"""
        return room_id in self._rounds

    def discussion_snapshot(self, room_id: str) -> dict:
        """``room_state`` 的讨论态快照（design Decision 7，grill I8/N2）。

        ``round`` = 当前活动链已进入的轮序号（1-based），无链 / ``single`` 恒 0；
        ``reason`` = 最近一次链结束原因，从未结束过为 ``None``。
        """
        entry = self._discussion_state.get(room_id)
        if entry is None:
            return {"round": 0, "reason": None}
        return {
            "round": int(entry.get("round", 0)),
            "reason": entry.get("reason"),
        }

    def log_for(self, room_id: str) -> RoomLog:
        return RoomLog(self._store, room_id)

    async def request_stop(self, room_id: str) -> bool:
        """请求优雅停止当前讨论链（design Decision 5 / grill L2）。

        - 无活动链 / 链已 ``closing`` / 房间不存在 / ``single`` 房 → ``False``；
        - 首次请求：**同步**置位并 ``await`` 发 ``discussion_stop_requested``；
          重复请求返回 ``True`` 但不重复发事件（CQ11）。

        停止**不打断在跑回合**：``_drive`` 在每个 slot 前后检查，当前回合跑完后
        结束当前轮并跳过剩余 slot。
        """
        chain = self._rounds.get(room_id)
        if chain is None or chain.closing:
            return False
        room = self._store.get_room(room_id)
        if room is None or room.discussion_mode != DISCUSSION_MODE_UNLIMITED:
            return False
        first = not chain.stop_requested
        chain.stop_requested = True
        if first:
            await self._emit("discussion_stop_requested", {
                "room_id": room_id,
                "chain_id": chain.chain_id,
            })
        return True

    async def submit_user_message(self, room_id: str, text: str) -> RoundResult:
        """用户消息入口：开一条讨论链，或排队进入正在进行的讨论。

        **不用锁**：``_rounds`` 的「查—建」之间没有 ``await`` 点（asyncio 单线程
        事件循环下是原子的），与既有 ``run_session`` 的 ``run_lock.locked()``
        检查同一论证。锁会把整条链圈住，导致讨论中到达的消息在链后才被处理、
        进而**另开一条链**——正是 Decision 5 要禁止的。
        """
        room = self._store.get_room(room_id)
        if room is None:
            raise KeyError(f"unknown room: {room_id}")
        active = self._rounds.get(room_id)
        if active is not None:
            # 讨论进行中：只追加进房间日志；行首 @ 进当前位次之后 / 轮间窗口记待应用。
            entry = self.log_for(room_id).append_user(text)
            active.pending_user_seqs.append(entry.seq)
            if active.current.closed:
                # 轮间窗口（本轮已收尾、下一轮尚未建）：点名留待下一轮开局 slot。
                self._record_pending_mentions(active, room, text)
                await self._emit("user_message", {
                    "room_id": room_id, "text": text, "seq": entry.seq,
                    "queued": True,
                })
                return RoundResult(
                    room_id=room_id,
                    queued=True,
                    termination=TERMINATION_QUEUED,
                )
            self._append_called_slots(active.current, room, text)
            await self._emit("user_message", {
                "room_id": room_id, "text": text, "seq": entry.seq,
                "queued": True,
            })
            return RoundResult(
                room_id=room_id,
                queued=True,
                termination=TERMINATION_QUEUED,
                slots=list(active.current.slots),
                limit=active.current.limit,
            )
        return await self._run_discussion(room, text)

    # ------------------------------------------------------------------
    # 讨论链驱动
    # ------------------------------------------------------------------

    async def _run_discussion(self, room: Room, opening_text: str) -> RoundResult:
        log = self.log_for(room.id)
        roster = {p.id: p for p in self._store.list_personas()}

        # Decision 3.1（grill C9/I9）：空成员房间不建链，退化单轮语义。
        if not room.members:
            return await self._run_degenerate_round(room, opening_text)

        unlimited = room.discussion_mode == DISCUSSION_MODE_UNLIMITED

        # ---- 认领 + 第 1 轮骨架：同一无 await 同步区（grill I1）----
        limits = _DiscussionLimits(
            max_rounds=self._discussion_max_rounds,
            max_turns=self._discussion_max_turns,
            max_seconds=self._discussion_max_seconds,
        )
        slots = opening_slots(room, opening_text, roster, self._store.main_bot_ids())
        state = _RoundState(
            room_id=room.id,
            start_seq=0,
            slots=slots,
            limit=self._first_round_limit(room, slots, unlimited, limits),
        )
        chain = _ChainState(
            room_id=room.id,
            chain_id=self._next_chain_id(room.id),
            discussion_mode=room.discussion_mode,
            started_at=self._clock(),
            limits=limits,
            current=state,
        )
        self._rounds[room.id] = chain
        if unlimited:
            self._set_discussion_round(room.id, 1)

        try:
            entry = log.append_user(opening_text)          # 同步：不引入 await
            state.start_seq = entry.seq
            await self._emit("user_message", {
                "room_id": room.id, "text": opening_text, "seq": entry.seq,
                "queued": False,
            })
            if unlimited:
                await self._emit("discussion_started", {
                    "room_id": room.id,
                    "chain_id": chain.chain_id,
                    "discussion_mode": room.discussion_mode,
                    "members": list(room.members),
                    "round_index": 1,
                    "limits": limits.as_dict(),
                })

            last_termination = TERMINATION_COMPLETED
            while True:
                await self._drive(chain, state)
                # ---- 同步收尾区（无 await）：轮终止 → 链判定 → 释放（若结束）----
                closed = self._close_round(chain, state)
                last_termination = closed.termination
                await self._flush_status_emits(room.id)
                await self._notify_round_review(room.id)
                # 在发出本轮 round_ended **之前**置位（取消/异常 teardown 防重复）。
                state.terminal_sent = True
                await self._emit("round_ended", self._round_ended_payload(
                    chain,
                    state,
                    termination=closed.termination,
                    status_seq=closed.status_seq,
                    chain_continues=closed.chain_end is None,
                ))
                if closed.chain_end is not None:
                    return await self._finish_chain(
                        chain, state, closed.termination, closed.chain_end
                    )
                # ---- 续轮：先同步检查轮间停止 / 建下一轮，再 await 事件 ----
                following = self._begin_following_round(chain, roster)
                if isinstance(following, _ChainEnd):
                    return await self._finish_chain(
                        chain, state, last_termination, following
                    )
                state = following.state
                await self._emit("system_entry", self._system_entry_payload(
                    chain, following.system_entry
                ))
        except asyncio.CancelledError:
            # 取消优先于一切快照条件（grill I9）：同步 abort + 后台 teardown。
            self._abort_chain(chain, TERMINATION_CANCELLED)
            raise
        except Exception:
            self._abort_chain(chain, TERMINATION_ERROR)
            logger.exception("群聊讨论链异常终止（已尽力通知房间）")
            raise
        finally:
            if self._rounds.get(room.id) is chain:
                # 兜底释放（照搬单轮实现的 finally 语义）：任何遗漏出口都不把
                # 房间永久锁在「讨论中」，也不依赖正常收尾区。
                self._reset_room_statuses(room.id)
                self._release_round(room.id, chain)

    async def _run_degenerate_round(
        self, room: Room, opening_text: str
    ) -> RoundResult:
        """空成员房间的退化单轮（design Decision 3.1）：不建链、不发链级事件。"""
        log = self.log_for(room.id)
        entry = log.append_user(opening_text)
        await self._emit("user_message", {
            "room_id": room.id, "text": opening_text, "seq": entry.seq,
            "queued": False,
        })
        status_seq = self._reset_room_statuses(room.id)
        await self._flush_status_emits(room.id)
        await self._emit("round_ended", {
            "room_id": room.id,
            "termination": TERMINATION_COMPLETED,
            "limit": self._round_budget(room, []),
            "status_seq": status_seq,
        })
        await self._notify_round_review(room.id)
        return RoundResult(
            room_id=room.id,
            queued=False,
            termination=TERMINATION_COMPLETED,
            limit=self._round_budget(room, []),
            discussion_mode=room.discussion_mode,
        )

    async def _drive(self, chain: _ChainState, state: _RoundState) -> None:
        """走完本轮 slot；每个 slot **前后**检查停止与墙钟（design Decision 5/6）。"""
        unlimited = chain.discussion_mode == DISCUSSION_MODE_UNLIMITED
        while state.index < len(state.slots):
            if state.turns >= state.limit:
                return
            if unlimited:
                if chain.stop_requested:
                    return
                if self._clock() - chain.started_at >= chain.limits.max_seconds:
                    # 不打断在跑回合，仅不再开新回合（Q4）。
                    return
            persona_id = state.slots[state.index]
            await self._run_slot(chain, state, persona_id)
            state.index += 1

    async def _run_slot(
        self, chain: _ChainState, state: _RoundState, persona_id: str
    ) -> None:
        room_id = state.room_id
        log = self.log_for(room_id)
        # 成员中途变更（被移出房间 / 房间被删）→ 跳过该 slot（参照的 ``left`` 出口）。
        room = self._store.get_room(room_id)
        if room is None or persona_id not in room.members:
            await self._emit("slot_skipped", {
                "room_id": room_id, "persona_id": persona_id, "reason": "left",
            })
            return

        roster = {p.id: p for p in self._store.list_personas()}
        persona = roster.get(persona_id)
        name = persona.name if persona and persona.name else persona_id

        discussion_context = None
        if chain.discussion_mode == DISCUSSION_MODE_UNLIMITED:
            discussion_context = discussion_prompt_context(chain.round_index)

        # slot 认领即 running：覆盖 ensure_room_session / prompt 构造的空窗。
        self._set_signal(room_id, persona_id, "slot_started", {})
        try:
            try:
                session_id = await self._resolver.ensure_room_session(
                    room_id, persona_id
                )
            except Exception as exc:  # noqa: BLE001 - 单个成员建会话失败不挂死整轮
                logger.warning("成员 %s 的群内会话创建失败: %s", persona_id, exc)
                state.failures += 1
                system_entry = self._append_room_system(
                    room_id, f"成员 {name} 运行失败：会话不可用"
                )
                if system_entry is not None:
                    state.systems.append(system_entry)
                await self._finish_member(
                    room_id, persona_id, "member_failed",
                    {"status": "failed", "reason": "会话不可用", "name": name},
                )
                return

            # 回合开始：先读切片（用**旧**游标），再推进游标（含静默/超时回合）。
            view = log.build_injection(persona_id, round_start=state.start_seq)
            self._consume_pending_user_seqs(chain, view)
            log.advance_seen(persona_id)

            prompt = build_member_prompt(
                room=room,
                persona_id=persona_id,
                roster=roster,
                view=view,
                slot_index=state.index,
                slot_total=len(state.slots),
                discussion_context=discussion_context,
            )
            state.turns += 1
            state.per_member_turns[persona_id] = (
                state.per_member_turns.get(persona_id, 0) + 1
            )

            await self._emit("member_speaking", {
                "room_id": room_id, "persona_id": persona_id, "name": name,
                "status_seq": self._status_seq.get(room_id, 0),
            })

            async def on_progress(kind: str, data: dict) -> None:
                self._set_signal(room_id, persona_id, kind, data or {})

            outcome = await self._runner.run(
                session_id, prompt,
                timeout=self._turn_timeout,
                silent_marker=SILENT_MARKER,
                on_progress=on_progress,
            )

            # 回合进行中房间被删除：不写任何日志（避免复活已删房间，grill L13）。
            if self._store.get_room(room_id) is None:
                await self._finish_member(room_id, persona_id, "member_silent", {})
                return

            if outcome.status == "silent":
                await self._finish_member(
                    room_id, persona_id, "member_silent", {}
                )
            elif outcome.status in ("failed", "timeout"):
                state.failures += 1
                reason = "超时" if outcome.status == "timeout" else (
                    outcome.message or outcome.code or "运行失败"
                )
                system_entry = self._append_room_system(
                    room_id, f"成员 {name} 运行失败：{reason}"
                )
                if system_entry is not None:
                    state.systems.append(system_entry)
                await self._finish_member(
                    room_id, persona_id, "member_failed",
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
                        room_id, persona_id, "member_post",
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
                        room_id, persona_id, "member_silent", {}
                    )

            # review 排期**排在发言落日志之后**：review 读的是房间日志切片，先入日志
            # 才不会漏掉刚发出的这条（Decision 17：仅实际发言的回合触发）。
            if self._review_sink is not None:
                try:
                    await self._review_sink.on_member_turn(
                        room_id=room_id, persona_id=persona_id, outcome=outcome
                    )
                except Exception:  # noqa: BLE001 - review 排期失败 SHALL NOT 中断轮次
                    logger.exception("记忆 review 排期失败（已忽略）")
        finally:
            # 幂等兜底：任何遗漏出口/取消/意外异常都不把成员留在忙。
            self._reset_member(room_id, persona_id)

    # ------------------------------------------------------------------
    # 一轮收尾与链级判定（全部同步，design Decision 3 d）
    # ------------------------------------------------------------------

    def _close_round(
        self, chain: _ChainState, state: _RoundState
    ) -> _ClosedRound:
        """轮终止判定 + rounds/turns 记账 + 链级判定 + 结束释放（纯同步快照）。"""
        log = self.log_for(chain.room_id)
        room = self._store.get_room(chain.room_id)
        state.closed = True

        # ---- 轮终止判定（优先级：停止 > 达上限 > 全失败 > 走完）----
        if chain.stop_requested:
            termination = TERMINATION_STOPPED
        elif state.turns >= state.limit and state.index < len(state.slots):
            if room is not None:
                state.systems.append(log.append_system(LIMIT_ENTRY_TEXT))
            termination = TERMINATION_LIMIT
        elif not state.posts and state.failures:
            termination = TERMINATION_ALL_FAILED
        else:
            termination = TERMINATION_COMPLETED

        # ---- 链级记账：rounds 只计正常收尾的轮（grill I3）；turns 含被打断轮 ----
        chain.turns += state.turns
        if termination in (
            TERMINATION_COMPLETED, TERMINATION_LIMIT, TERMINATION_ALL_FAILED,
        ):
            chain.rounds.append(state)

        now = self._clock()
        if chain.discussion_mode != DISCUSSION_MODE_UNLIMITED:
            # Decision 3.5：single 共用链外壳，但不做链级判定、不写链级 system、
            # 不发链级事件；一轮结束即链结束（三出口语义逐字段不变）。
            chain.closing = True
            status_seq = self._reset_room_statuses(chain.room_id)
            self._release_round(chain.room_id, chain)
            return _ClosedRound(
                termination=termination,
                status_seq=status_seq,
                chain_end=_ChainEnd(
                    reason=REASON_COMPLETED,
                    status_seq=status_seq,
                    elapsed_seconds=now - chain.started_at,
                ),
            )

        reason = self._chain_end_reason(chain, state, termination, room, now)
        if reason is None:
            # 续轮路径：同步区只到「决定继续 + 置 closed」（不释放认领）。
            return _ClosedRound(
                termination=termination,
                status_seq=self._status_seq.get(chain.room_id, 0),
                chain_end=None,
            )

        chain.closing = True
        end_system = None
        if room is not None:
            text = CHAIN_END_SYSTEM_TEXTS.get(reason)
            if text:
                end_system = log.append_system(text)
        self._set_discussion_ended(chain.room_id, reason)
        status_seq = self._reset_room_statuses(chain.room_id)
        self._release_round(chain.room_id, chain)
        return _ClosedRound(
            termination=termination,
            status_seq=status_seq,
            chain_end=_ChainEnd(
                reason=reason,
                status_seq=status_seq,
                system_entry=end_system,
                elapsed_seconds=now - chain.started_at,
            ),
        )

    def _chain_end_reason(
        self,
        chain: _ChainState,
        state: _RoundState,
        termination: str,
        room: Room | None,
        now: float,
    ) -> str | None:
        """链级结束判定（design Decision 3 优先级表，纯同步快照）。

        取消 / 意外异常不参与本排序（它们在 ``_abort_chain`` 里直接终结）。
        ``None`` 表示续轮。
        """
        limits = chain.limits
        if chain.stop_requested:
            return REASON_STOPPED
        if room is None or not room.members:
            return REASON_COMPLETED
        if (
            room.discussion_mode != DISCUSSION_MODE_UNLIMITED
            or room.reply_mode != "everyone"
        ):
            return REASON_MODE_CHANGED
        if termination == TERMINATION_LIMIT:
            return REASON_ROUND_LIMIT
        if len(chain.rounds) >= limits.max_rounds:
            return REASON_MAX_ROUNDS
        if chain.turns >= limits.max_turns:
            return REASON_MAX_TURNS
        if now - chain.started_at >= limits.max_seconds:
            return REASON_MAX_SECONDS
        if not state.posts and not state.failures and not chain.pending_user_seqs:
            return REASON_CONVERGED
        if not state.posts and state.failures:
            return REASON_ALL_FAILED
        # 有发言 → 续轮；0 发言 0 失败但有未消费用户消息 → 强制再开一轮（Q1）。
        return None

    def _begin_following_round(
        self, chain: _ChainState, roster: dict[str, Persona]
    ) -> _StartedRound | _ChainEnd:
        """续轮同步区：建下一轮，或发现轮间停止 / 房间被删而结束链。"""
        log = self.log_for(chain.room_id)
        now = self._clock()
        room = self._store.get_room(chain.room_id)
        if room is None:
            # 轮间房间被删除：退化 completed，不写日志（不复活已删房间）。
            chain.closing = True
            self._set_discussion_ended(chain.room_id, REASON_COMPLETED)
            status_seq = self._reset_room_statuses(chain.room_id)
            self._release_round(chain.room_id, chain)
            return _ChainEnd(
                reason=REASON_COMPLETED,
                status_seq=status_seq,
                elapsed_seconds=now - chain.started_at,
            )
        if chain.stop_requested:
            # design 4a：不建新轮、不补发 round_ended，直接结束链。
            chain.closing = True
            end_system = log.append_system(STOPPED_ENTRY_TEXT)
            self._set_discussion_ended(chain.room_id, REASON_STOPPED)
            status_seq = self._reset_room_statuses(chain.room_id)
            self._release_round(chain.room_id, chain)
            return _ChainEnd(
                reason=REASON_STOPPED,
                status_seq=status_seq,
                system_entry=end_system,
                elapsed_seconds=now - chain.started_at,
            )

        round_index = chain.round_index + 1
        system_entry = log.append_system(
            CONTINUE_ENTRY_TEXT.format(round_index=round_index)
        )
        # grill I7：续轮 SHALL 传空 opening，避免开局行首 @ 让后续每轮只剩点名者。
        slots = opening_slots(room, "", roster, self._store.main_bot_ids())
        slots = self._apply_pending_mentions(chain, room, slots)
        budget = self._round_budget(room, slots)
        remaining = chain.limits.max_turns - chain.turns
        state = _RoundState(
            room_id=chain.room_id,
            start_seq=system_entry.seq,
            slots=slots,
            limit=max(0, min(budget, remaining)),
        )
        chain.current = state
        chain.round_index = round_index
        self._set_discussion_round(chain.room_id, round_index)
        return _StartedRound(state=state, system_entry=system_entry)

    def _apply_pending_mentions(
        self, chain: _ChainState, room: Room, slots: list[str]
    ) -> list[str]:
        """轮间窗口的待应用点名：按顺序插队首、去重、非本群成员忽略。"""
        if not chain.pending_mentions:
            return slots
        heads: list[str] = []
        for pid in chain.pending_mentions:
            if pid in room.members and pid not in heads:
                heads.append(pid)
        chain.pending_mentions.clear()
        if not heads:
            return slots
        return heads + [pid for pid in slots if pid not in heads]

    async def _finish_chain(
        self,
        chain: _ChainState,
        state: _RoundState,
        termination: str,
        end: _ChainEnd,
    ) -> RoundResult:
        """链结束路径的 await 段：(f) 之后补 system_entry → discussion_ended。"""
        if chain.discussion_mode == DISCUSSION_MODE_UNLIMITED:
            if end.system_entry is not None:
                await self._emit("system_entry", self._system_entry_payload(
                    chain, end.system_entry
                ))
            await self._emit(
                "discussion_ended", self._discussion_ended_payload(chain, end)
            )
        return self._build_round_result(chain, state, termination, end)

    # ------------------------------------------------------------------
    # 取消 / 异常 teardown（design Decision 8）
    # ------------------------------------------------------------------

    def _abort_chain(self, chain: _ChainState, kind: str) -> None:
        """取消/异常 teardown 的**同步**区：置 closing、写 system、reset、release。"""
        if self._rounds.get(chain.room_id) is not chain:
            # 迟到 teardown：认领已释放（正常收尾 / 新链已接管）。
            return
        chain.closing = True
        system_entry: RoomEntry | None = None
        if chain.discussion_mode == DISCUSSION_MODE_UNLIMITED:
            self._set_discussion_ended(chain.room_id, kind)
            if kind == TERMINATION_CANCELLED:
                # Q2：断线取消写 system（让用户知道中止原因）；error 不写。
                room = self._store.get_room(chain.room_id)
                if room is not None:
                    system_entry = self.log_for(chain.room_id).append_system(
                        DISCONNECTED_ENTRY_TEXT
                    )
        status_seq = self._reset_room_statuses(chain.room_id)
        self._release_round(chain.room_id, chain)
        end = _ChainEnd(
            reason=kind,
            status_seq=status_seq,
            system_entry=system_entry,
            elapsed_seconds=self._clock() - chain.started_at,
        )
        self._schedule_chain_teardown(chain, end)

    def _schedule_chain_teardown(
        self, chain: _ChainState, end: _ChainEnd
    ) -> None:
        """后台 teardown：尽力发 round_ended（未发过时）+ discussion_ended。"""
        state = chain.current
        kind = end.reason
        unlimited = chain.discussion_mode == DISCUSSION_MODE_UNLIMITED

        async def _run() -> None:
            async def _flush_and_emit() -> None:
                await self._flush_status_emits(chain.room_id)
                if unlimited and end.system_entry is not None:
                    await self._emit("system_entry", self._system_entry_payload(
                        chain, end.system_entry
                    ))
                if not state.terminal_sent:
                    state.terminal_sent = True
                    await self._emit("round_ended", self._round_ended_payload(
                        chain,
                        state,
                        termination=kind,
                        status_seq=end.status_seq,
                        chain_continues=False,
                    ))
                if unlimited:
                    await self._emit(
                        "discussion_ended",
                        self._discussion_ended_payload(chain, end),
                    )

            try:
                # 整体 2s 上限（不是 flush 2s + emit 2s）。
                await asyncio.wait_for(_flush_and_emit(), timeout=2.0)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("群聊讨论链 teardown 超时（%s）", chain.room_id)
            except Exception:  # noqa: BLE001 - teardown 尽力而为
                logger.exception("群聊讨论链 teardown 失败（已忽略）")

        task = asyncio.create_task(_run())
        self._teardown_tasks.add(task)
        task.add_done_callback(self._teardown_tasks.discard)

    # ------------------------------------------------------------------
    # 事件 payload 构造
    # ------------------------------------------------------------------

    def _round_ended_payload(
        self,
        chain: _ChainState,
        state: _RoundState,
        *,
        termination: str,
        status_seq: int,
        chain_continues: bool,
    ) -> dict:
        payload = {
            "room_id": chain.room_id,
            "termination": termination,
            "limit": state.limit,
            "status_seq": status_seq,
        }
        # single 模式：payload 四键逐字段不变（design Decision 9）。
        if chain.discussion_mode == DISCUSSION_MODE_UNLIMITED:
            payload.update({
                "chain_id": chain.chain_id,
                "round_index": chain.round_index,
                "chain_continues": chain_continues,
            })
        return payload

    def _discussion_ended_payload(
        self, chain: _ChainState, end: _ChainEnd
    ) -> dict:
        return {
            "room_id": chain.room_id,
            "chain_id": chain.chain_id,
            "reason": end.reason,
            "rounds": len(chain.rounds),
            "rounds_started": chain.round_index,
            "turns": chain.turns,
            "elapsed_seconds": end.elapsed_seconds,
            "status_seq": end.status_seq,
        }

    @staticmethod
    def _system_entry_payload(chain: _ChainState, entry: RoomEntry) -> dict:
        return {
            "room_id": chain.room_id,
            "chain_id": chain.chain_id,
            "seq": entry.seq,
            "text": entry.text,
        }

    def _build_round_result(
        self,
        chain: _ChainState,
        state: _RoundState,
        termination: str,
        end: _ChainEnd,
    ) -> RoundResult:
        """``single`` 返回旧字段（新字段默认值）；``unlimited`` 加链级统计。"""
        if chain.discussion_mode != DISCUSSION_MODE_UNLIMITED:
            return RoundResult(
                room_id=chain.room_id,
                queued=False,
                termination=termination,
                posts=list(state.posts),
                systems=list(state.systems),
                slots=list(state.slots),
                limit=state.limit,
            )
        return RoundResult(
            room_id=chain.room_id,
            queued=False,
            termination=termination,
            posts=list(state.posts),
            systems=list(state.systems),
            slots=list(state.slots),
            limit=state.limit,
            discussion_mode=chain.discussion_mode,
            discussion_reason=end.reason,
            chain_id=chain.chain_id,
            rounds=len(chain.rounds),
            rounds_started=chain.round_index,
        )

    # ------------------------------------------------------------------
    # 讨论链辅助
    # ------------------------------------------------------------------

    def _next_chain_id(self, room_id: str) -> str:
        seq = self._chain_seq.get(room_id, 0) + 1
        self._chain_seq[room_id] = seq
        return f"{room_id}:{seq}"

    def _set_discussion_round(self, room_id: str, round_index: int) -> None:
        entry = self._discussion_state.setdefault(
            room_id, {"round": 0, "reason": None}
        )
        entry["round"] = round_index

    def _set_discussion_ended(self, room_id: str, reason: str) -> None:
        entry = self._discussion_state.setdefault(
            room_id, {"round": 0, "reason": None}
        )
        entry["round"] = 0
        entry["reason"] = reason

    def _round_budget(self, room: Room, slots: list[str]) -> int:
        return len(slots) + self._extra_turns + (
            self._admin_extra_turns if room.admin else 0
        )

    def _first_round_limit(
        self,
        room: Room,
        slots: list[str],
        unlimited: bool,
        limits: _DiscussionLimits,
    ) -> int:
        budget = self._round_budget(room, slots)
        if not unlimited:
            return budget
        return max(0, min(budget, limits.max_turns))

    @staticmethod
    def _consume_pending_user_seqs(chain: _ChainState, view: dict) -> None:
        """回合切片构造后，把已被该切片覆盖到的用户条目移出待消费集合。"""
        current = view.get("current") or []
        if not current or not chain.pending_user_seqs:
            return
        # 「覆盖到的最大 seq」= 本次注入看到的房间日志末条 seq（不是窗口首条，
        # 避免窗口截断时把旧消息误记已消费；design Decision 2）。
        max_seq = current[-1].seq
        chain.pending_user_seqs = [
            seq for seq in chain.pending_user_seqs if seq > max_seq
        ]

    def _record_pending_mentions(
        self, chain: _ChainState, room: Room, text: str
    ) -> None:
        """轮间窗口到达的用户行首 ``@``：去重记入待应用点名。"""
        roster = {p.id: p for p in self._store.list_personas()}
        for pid in parse_mentions(text, _name_index(room, roster), leading_only=True):
            if pid in room.members and pid not in chain.pending_mentions:
                chain.pending_mentions.append(pid)

    def _append_room_system(self, room_id: str, text: str) -> RoomEntry | None:
        """写一条房间 system 条目；房间已被删除时不写（避免复活日志）。"""
        if self._store.get_room(room_id) is None:
            return None
        return self.log_for(room_id).append_system(text)

    async def _notify_round_review(self, room_id: str) -> None:
        if self._review_sink is None:
            return
        try:
            await self._review_sink.on_round_end(room_id=room_id)
        except Exception:  # noqa: BLE001 - review 失败 SHALL NOT 中断轮次/链
            logger.exception("记忆 review 的落后补齐调度失败（已忽略）")

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
        # reduce_signal 只产生非 idle 状态；idle 由 _reset_member/_reset_room_statuses 负责。
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
            return
        logger.warning("成员状态 flush 达到迭代上限，仍有待发射变化：%s", room_id)

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
        """返回 (非空闲状态表副本, 当前房间级 seq)，供 room_state 使用。

        只返回当前仍在房间里的成员，避免成员中途被移出后快照里留下幽灵状态。
        """
        table = self._statuses.get(room_id, {})
        room = self._store.get_room(room_id)
        members = set(room.members) if room is not None else set()
        statuses = [
            status.as_dict(pid)
            for pid, status in table.items()
            if not status.is_idle and pid in members
        ]
        return statuses, self._status_seq.get(room_id, 0)

    def _release_round(self, room_id: str, chain: _ChainState) -> None:
        """仅当仍持有认领时才释放，避免误删 await 期间启动的新链（grill I6）。"""
        if self._rounds.get(room_id) is chain:
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

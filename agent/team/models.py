"""群聊板块的数据模型：人设（roster）、房间、房间日志条目。

三者都是**纯数据**：不含 IO、不含会话驱动。持久化在 ``store.py``，
时序语义在 ``roomlog.py`` / ``orchestrator.py``。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from agent import session as _session

#: 房间日志条目的类型枚举（design Decision 6 / spec delta「房间日志」）。
#: ``user``  = 用户消息（``speaker == "user"``）
#: ``post``  = 成员发言（``speaker == persona_id``）
#: ``system``= 系统条目（如「因达上限结束」「成员运行失败」，``speaker is None``）
ENTRY_KINDS = ("user", "post", "system")

#: 人设的运行模式取值（与 ``AgentMode`` 同名，design Decision 18）。
PERSONA_MODES = ("build", "read_only", "plan", "bypass")
#: 人设模式的缺省值：``bypass``（用户 2026-10-13 拍板）。理由：``build`` 下高风险
#: 工具需审批，而群内会话按 Decision 9 审批 fail-closed 立即拒 ⇒ 成员在群里根本
#: 跑不了高风险工具（「被权限卡死」）。
DEFAULT_PERSONA_MODE = "bypass"

#: 房间应答模式取值（design Decision 19）。
REPLY_MODES = ("admin", "everyone")
#: 缺省 ``admin``——``everyone`` 的成本是每条消息 N 次模型调用，故默认关闭。
DEFAULT_REPLY_MODE = "admin"

#: 内部会话的 kind 取值（design Decision 8）。真正定义在 ``agent.session``
#: （``SessionSnapshot.kind`` 的宿主），这里复出以免两处各写一份字符串。
KIND_CHAT = _session.KIND_CHAT
KIND_PERSONA_CHAT = _session.KIND_PERSONA_CHAT
KIND_ROOM_MEMBER = _session.KIND_ROOM_MEMBER


def new_persona_id() -> str:
    """稳定的人设标识。文件系统安全（纯 alnum），用作目录名与 scope 片段。"""
    return "p" + uuid.uuid4().hex[:12]


def new_room_id() -> str:
    return "r" + uuid.uuid4().hex[:12]


@dataclass
class Persona:
    """长期存在的 agent 人设（design Decision 1 / 13）。

    ``id`` 稳定且跨进程持久化；``instructions`` 走既有的会话指令注入面
    （``AgentSession.init_messages`` → ``_user_system_prompt`` → 快照落盘/回灌）。
    """

    name: str
    role: str = ""
    instructions: str = ""
    model: str = ""
    id: str = ""
    #: 运行模式（design Decision 18）：该人设的**单聊与所有群内会话**都以它构造。
    mode: str = DEFAULT_PERSONA_MODE
    #: 该人设单聊会话的底座 id（稳定映射，design Decision 8）。
    chat_session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = new_persona_id()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "instructions": self.instructions,
            "model": self.model,
            "mode": self.mode,
            "chat_session_id": self.chat_session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        return cls(
            name=str(data.get("name", "")),
            role=str(data.get("role", "")),
            instructions=str(data.get("instructions", "")),
            model=str(data.get("model", "")),
            id=str(data.get("id", "")),
            # 本 change 之前写入的 roster 记录没有该字段 → 按缺省 ``bypass`` 读。
            mode=str(data.get("mode") or DEFAULT_PERSONA_MODE),
            chat_session_id=data.get("chat_session_id") or None,
        )


@dataclass
class Room:
    """群聊房间（design Decision 6 / 13 / 16）。

    ``admin`` 是**房间级**主持角色（单个、可为空），决定「用户消息默认由谁应答」；
    roster 级 ``mainBotIds``（可多个）是 Chief。两级并存，各司其职。
    """

    name: str
    members: list[str] = field(default_factory=list)
    admin: str | None = None
    notice: str = ""
    #: 应答模式（design Decision 19）：``admin`` 只让 admin 应答；``everyone`` 让
    #: 全体成员按序各得一次发言机会（admin 先）。
    reply_mode: str = DEFAULT_REPLY_MODE
    id: str = ""
    #: ``persona_id -> 群内会话 id``（稳定映射，Decision 8）。
    sessions: dict[str, str] = field(default_factory=dict)
    #: **注入用**游标：``persona_id -> room seq``，在**回合开始**推进（含静默/超时回合）。
    seen: dict[str, int] = field(default_factory=dict)
    #: 创建者（Chief）——建房间时默认把创建者设为 admin。
    created_by: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = new_room_id()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "members": list(self.members),
            "admin": self.admin,
            "notice": self.notice,
            "reply_mode": self.reply_mode,
            "sessions": dict(self.sessions),
            "seen": dict(self.seen),
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Room":
        return cls(
            name=str(data.get("name", "")),
            members=[str(m) for m in data.get("members", [])],
            admin=data.get("admin") or None,
            notice=str(data.get("notice", "")),
            # 本 change 之前写入的房间记录没有该字段 → 按缺省 ``admin`` 读。
            reply_mode=str(data.get("reply_mode") or DEFAULT_REPLY_MODE),
            id=str(data.get("id", "")),
            sessions={str(k): str(v) for k, v in (data.get("sessions") or {}).items()},
            seen={str(k): int(v) for k, v in (data.get("seen") or {}).items()},
            created_by=data.get("created_by") or None,
        )


@dataclass
class RoomEntry:
    """房间日志的一条有序条目（design Decision 6 的 schema）。"""

    seq: int
    speaker: str | None
    kind: str
    text: str
    ts: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "speaker": self.speaker,
            "kind": self.kind,
            "text": self.text,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoomEntry":
        return cls(
            seq=int(data.get("seq", 0)),
            speaker=data.get("speaker"),
            kind=str(data.get("kind", "system")),
            text=str(data.get("text", "")),
            ts=str(data.get("ts", "")),
        )

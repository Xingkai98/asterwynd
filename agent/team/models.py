"""群聊板块的数据模型：人设（roster）、房间、房间日志条目。

三者都是**纯数据**：不含 IO、不含会话驱动。持久化在 ``store.py``，
时序语义在 ``roomlog.py`` / ``orchestrator.py``。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

#: 房间日志条目的类型枚举（design Decision 6 / spec delta「房间日志」）。
#: ``user``  = 用户消息（``speaker == "user"``）
#: ``post``  = 成员发言（``speaker == persona_id``）
#: ``system``= 系统条目（如「因达上限结束」「成员运行失败」，``speaker is None``）
ENTRY_KINDS = ("user", "post", "system")

#: 内部会话的 kind 取值（design Decision 8）。
KIND_CHAT = "chat"
KIND_PERSONA_CHAT = "persona_chat"
KIND_ROOM_MEMBER = "room_member"
INTERNAL_KINDS = (KIND_PERSONA_CHAT, KIND_ROOM_MEMBER)


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

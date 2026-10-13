"""编排器与「会话底座创建」之间的抽象（design Decision 4 的第二条依赖）。

创建会话需要 llm / config / 会话数上限与排队——全是 web 层的知识。编排器只依赖本
协议的 ``ensure_*`` 返回一个**稳定的会话 id**，web 层负责懒构造与上限（Decision 1/Q4）。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SessionResolver(Protocol):
    """把一个 (persona, room) 或 persona 映射到一个已就绪的会话 id。"""

    async def ensure_room_session(self, room_id: str, persona_id: str) -> str:
        """该人设在该群的群内会话 id（首次调用时创建底座）。"""
        ...

    async def ensure_persona_chat_session(self, persona_id: str) -> str:
        """该人设单聊会话 id（首次调用时创建底座）。"""
        ...

"""长期 agent 人设与群聊编排（change ``web-agent-group-chat``）。

本包的边界刻意收窄：它只依赖 ``SessionRunner`` 抽象（``agent/team/runner.py``）
驱动成员会话，**不 import ``web``**——本仓分层单向 ``web/ → agent/``
（``agent/main.py`` 的 CLI 入口延迟 import 是唯一反向点），编排器若反向驱动
``web.AgentSession`` 会打破这条约束（design Decision 4）。
"""

from agent.team.models import Persona, Room, RoomEntry
from agent.team.roomlog import RoomLog
from agent.team.runner import SessionRunner, TurnOutcome
from agent.team.store import TeamStore

__all__ = [
    "Persona",
    "Room",
    "RoomEntry",
    "RoomLog",
    "SessionRunner",
    "TeamStore",
    "TurnOutcome",
]

"""编排器与「会话驱动」之间的抽象（design Decision 4）。

编排器跑在 ``agent/`` 层，而成员会话是 ``web.AgentSession``、驱动入口是
``web.SessionManager.run_session``。本仓分层单向 ``web/ → agent/``，所以编排器
**不能** import ``web``——它依赖本模块的 ``SessionRunner`` 抽象，由 web 层实现并
注入（依赖倒置）。

契约要点（四条，SHALL NOT 弱化）：

- ``run`` **返回** 四态之一而不是抛异常；调用方不会因一个成员的失败而中断整轮。
- ``text`` SHALL 只来自**本次 run** 的产出，SHALL NOT 退化为「读 session 最后一条
  assistant」。同 session 并发 run 被 ``run_lock`` 拒时既有实现只发
  ``run_in_progress`` 事件并 ``return None``（``web/session.py``），若取「最后一条
  assistant」会把**陈旧内容**当本轮发言写进房间日志。
- 被拒 / 无产出 SHALL 映射为 ``failed``，SHALL NOT 复用旧文本。
- 单轮超时映射为 ``timeout``（缺省 240s，与参照 ``ROOM_REPLY_TIMEOUT_MS`` 同量级）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: 单轮缺省超时（秒）。参照实现 ``ds-bot/src/host/constants.js:25``
#: ``ROOM_REPLY_TIMEOUT_MS = 240_000``。
DEFAULT_TURN_TIMEOUT_SECONDS = 240.0

#: 出口状态四值。
STATUS_TEXT = "text"
STATUS_SILENT = "silent"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"

STATUSES = (STATUS_TEXT, STATUS_SILENT, STATUS_FAILED, STATUS_TIMEOUT)

#: 静默哨兵（design Decision 10）：成员被提示「无新增内容时回复 ``[PASS]``」，
#: 编排器解析最终文本判静默。不新增控制工具（会污染所有既有 agent 工具面）。
SILENT_MARKER = "[PASS]"

#: 哨兵的可接受写法（与参照 ``isPass`` 同形的宽松匹配）。
_SILENT_RE = re.compile(r"^[\[【(（]?\s*pass\s*[\]】)）]?\s*[.。!！]?$", re.IGNORECASE)


@dataclass(frozen=True)
class TurnOutcome:
    """一次成员回合的出口（四态 + 载荷）。"""

    status: str
    text: str = ""
    code: str = ""
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown turn status: {self.status!r}")

    @property
    def spoke(self) -> bool:
        """本回合是否**实际产生了发言**（记忆 review 的主触发条件，Decision 17）。"""
        return self.status == STATUS_TEXT


@runtime_checkable
class SessionRunner(Protocol):
    """「驱动一个会话的一轮并拿回出口」的抽象。由 web 层实现并注入。"""

    async def run(
        self,
        session_id: str,
        message: str,
        *,
        timeout: float | None = None,
        silent_marker: str | None = None,
    ) -> TurnOutcome:
        ...


def is_silent(text: str, marker: str = SILENT_MARKER) -> bool:
    """判定最终文本是否为静默哨兵。

    与参照同形：接受空串、``[PASS]``、``【PASS】``、``（pass）``、裸 ``PASS``
    以及带句末标点的形式，大小写不敏感
    （``ds-bot/src/host/groups.js:48`` 的 ``isPass``）。
    """
    stripped = (text or "").strip()
    if stripped == "":
        return True
    return _SILENT_RE.match(stripped) is not None

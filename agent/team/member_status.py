"""群聊成员运行状态的纯 reducer（change ``web-agent-group-member-status``）。

状态只由真实运行事件驱动，编排器负责房间级状态表与事件发射；本模块只做
``(当前状态, 信号) -> 新状态 | None`` 的纯计算，便于无 provider、无 asyncio 单测。

信号来自 web 层的 ``ProgressObserver``（AgentLoop 钩子 + 流式事件旁路）：

- ``slot_started`` / ``run_started`` / ``iteration_started``
- ``reasoning_delta`` / ``assistant_delta`` / ``stream_complete``
- ``tool_started`` / ``tool_finished``（带 ``tool_id`` / ``tool_name``）
- ``run_completed``

优先级：``tool > typing > thinking > running > idle``。工具按 ``tool_call.id`` 记账，
同名并发工具不会互相抵消；``iteration_started`` 会清空上一批在途工具（覆盖工具异常
跳过 ``after_tool_execute`` 的路径）。
"""
from __future__ import annotations

from dataclasses import dataclass

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_THINKING = "thinking"
PHASE_TYPING = "typing"
PHASE_TOOL = "tool"

PHASES = (PHASE_IDLE, PHASE_RUNNING, PHASE_THINKING, PHASE_TYPING, PHASE_TOOL)

#: 优先级（高 -> 低）；仅用于文档/测试断言，reducer 用显式迁移而不是数值比较。
PHASE_PRIORITY = {
    PHASE_TOOL: 4,
    PHASE_TYPING: 3,
    PHASE_THINKING: 2,
    PHASE_RUNNING: 1,
    PHASE_IDLE: 0,
}

SIGNALS = (
    "slot_started",
    "run_started",
    "iteration_started",
    "reasoning_delta",
    "assistant_delta",
    "stream_complete",
    "tool_started",
    "tool_finished",
    "run_completed",
)


@dataclass(frozen=True)
class MemberStatus:
    """一个成员的当前状态；``tools`` 是 ``(tool_call_id, tool_name)`` 有序元组。"""

    phase: str = PHASE_IDLE
    tools: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(f"unknown member phase: {self.phase!r}")

    @property
    def is_idle(self) -> bool:
        return self.phase == PHASE_IDLE

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def tool_names(self) -> list[str]:
        """去重后的在途工具名（按首次进入顺序）。"""
        seen: list[str] = []
        for _, name in self.tools:
            if name not in seen:
                seen.append(name)
        return seen

    def as_dict(self, persona_id: str) -> dict:
        return {
            "persona_id": persona_id,
            "phase": self.phase,
            "tools": self.tool_names,
            "tool_count": self.tool_count,
        }


def _tool_key(data: dict) -> tuple[str, str]:
    name = str(data.get("tool_name") or "").strip() or "tool"
    tool_id = str(data.get("tool_id") or "").strip() or name
    return tool_id, name


def reduce_signal(
    current: MemberStatus | None,
    kind: str,
    data: dict | None = None,
) -> MemberStatus | None:
    """返回新状态；无变化返回 ``None``。

    ``current is None`` 等价于空闲。未知信号/未知参数返回 ``None``。
    """
    cur = current or MemberStatus()
    payload = data or {}
    has_tools = bool(cur.tools)

    if kind == "slot_started":
        nxt = cur if cur.phase != PHASE_IDLE else MemberStatus(PHASE_RUNNING, cur.tools)
    elif kind == "iteration_started":
        # 新一次 LLM 调用意味着上一批工具已经结束；清空残留，防止异常路径卡在 tool。
        nxt = MemberStatus(PHASE_THINKING)
    elif kind in ("run_started", "reasoning_delta"):
        if has_tools or cur.phase in (PHASE_TYPING, PHASE_THINKING):
            nxt = cur
        else:
            nxt = MemberStatus(PHASE_THINKING, cur.tools)
    elif kind == "assistant_delta":
        if has_tools or cur.phase == PHASE_TYPING:
            nxt = cur
        else:
            nxt = MemberStatus(PHASE_TYPING, cur.tools)
    elif kind == "stream_complete":
        if has_tools:
            nxt = cur
        elif cur.phase in (PHASE_TYPING, PHASE_THINKING):
            nxt = MemberStatus(PHASE_RUNNING, cur.tools)
        else:
            nxt = cur
    elif kind == "tool_started":
        key = _tool_key(payload)
        tools = cur.tools if key in cur.tools else cur.tools + (key,)
        nxt = MemberStatus(PHASE_TOOL, tools)
    elif kind == "tool_finished":
        key = _tool_key(payload)
        tools = cur.tools
        if key in tools:
            tools = tuple(item for item in tools if item != key)
        elif tools:
            # 防御未配对事件：id 不匹配时按 name 移除第一个同名项。
            removed = False
            tool_id, name = key
            for index, (existing_id, existing_name) in enumerate(tools):
                if existing_name == name and (not tool_id or existing_id == tool_id):
                    tools = tools[:index] + tools[index + 1:]
                    removed = True
                    break
            if not removed:
                return None
        else:
            return None
        nxt = MemberStatus(PHASE_TOOL, tools) if tools else MemberStatus(PHASE_RUNNING)
    elif kind == "run_completed":
        nxt = cur if has_tools else MemberStatus(PHASE_RUNNING, cur.tools)
    else:
        return None

    return None if nxt == cur else nxt

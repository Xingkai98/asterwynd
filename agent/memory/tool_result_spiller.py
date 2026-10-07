"""工具结果 spill 生命周期的**单一内聚宿主**（change ``tool-result-spill-module``）。

本模块把此前摊在三处的有界工具结果生命周期收拢为一个深模块：

- **剪枝算法**（原 ``MemoryManager.prune_tool_results`` 的循环体）；
- **迭代消费状态**（原 ``agent/loop.py`` 的 ``_tool_result_iterations`` dict）；
- **判据调用**（``tool_result_policy`` 纯函数）与 ``_tokens`` 失效。

对外仅三个领域动词方法：``mark`` / ``reset`` / ``spill``——调用方（``AgentLoop``）
无需知道判据形态、幂等判据、窗口语义或内部状态存储；``spill`` 只返回 ``PruneStats``，
不持有 ``on_event`` / ``trace_recorder``（可观测是**编排关注点**，由调用方发射）。

**counter 注入（头号正确性风险）**：本模块**不**静态导入 ``manager._count_tokens``
（那会把绑定固化在 import 期，使测试的 ``monkeypatch.setattr(manager, "_count_tokens", ...)``
静默失效）。构造期由 ``MemoryManager`` 注入一个 **call-time 解析** ``manager`` 模块全局的
闭包；故 counter 是模块全局、可替换的单一缝。

**依赖方向**：``manager → tool_result_spiller → tool_result_policy``。本模块**不得**
反向 import ``manager``——迁 ``save`` 前的 flatten 用的是 ``policy.flatten_content``
而非 ``manager._flatten``，否则构成 ``manager ↔ spiller`` 循环 import。
"""
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from agent.message import Message
from agent.memory.tool_result_policy import (
    content_bytes as _content_bytes,
    exceeds_single_threshold as _exceeds_single_threshold,
    flatten_content as _flatten,
    is_spilled_preview as _is_spilled_preview,
    make_preview as _make_preview,
)

#: 复用 ``manager`` 的 logger 名（D8：纯重构，logger 名亦不漂移）。
logger = logging.getLogger("asterwynd.memory")


@dataclass(frozen=True)
class PruneStats:
    """``spill`` 的可观测产出（D9：剪枝不静默）。"""

    messages_spilled: int = 0
    bytes_released: int = 0

    def to_metadata(self) -> dict:
        return {
            "messages_spilled": self.messages_spilled,
            "bytes_released": self.bytes_released,
        }


class ToolResultSpiller:
    """工具结果 spill 的判定 + 剪枝 + 迭代消费状态。

    ``max_tokens`` / ``recent_window`` 是剪枝判据的输入；``counter`` 是 token 计数器
    （由 ``MemoryManager`` 注入的延迟闭包，见模块 docstring）。迭代标记 dict 唯一读者
    是剪枝，故随算法一起内聚于此，不对外暴露。
    """

    def __init__(
        self,
        max_tokens: int,
        recent_window: int,
        counter: Callable[[str], int],
    ) -> None:
        self.max_tokens = max_tokens
        self.recent_window = recent_window
        self._counter = counter
        self._iterations: dict[str, int] = {}

    def mark(self, tool_call_id: str, iteration: int) -> None:
        """记一个工具结果入库时的 iteration（取代 loop 内联写 dict）。"""
        self._iterations[tool_call_id] = iteration

    def reset(self, messages: list[Message]) -> None:
        """清空本 spiller 的标记，并把给定 ``messages`` 中既有 ``role=="tool"`` 消息预置为 ``-1``。

        这些消息在本 run 开始前就已产生、必然已被模型读过 ⇒ 预置 ``-1``（远早于任何
        ``current_iteration``，故 ``added <= current - 1`` 恒真），使 resume 重载 / 调用方
        预置的历史大结果可被剪——否则它们无标记、``spill`` 因 ``added is None`` 跳过 ⇒
        **永不剪、全文常驻**（审阅 M2）。语义须逐字保留今日 ``loop._reset_tool_result_iterations``。
        """
        self._iterations = {
            m.tool_call_id: -1
            for m in messages
            if m.role == "tool" and m.tool_call_id
        }

    def spill(
        self,
        messages: list[Message],
        *,
        current_iteration: int,
        added_iterations: Optional[dict[str, int]] = None,
        save: Optional[Callable[[str], str]] = None,
    ) -> PruneStats:
        """把陈旧的工具结果 ``messages`` 正文换成「有界预览 + ref」。

        剪枝判据 = **已消费一轮** ∩（**滑出近期窗口** ∪ **单条超阈**）：

        - **已消费一轮**：``added <= current_iteration - 1``。结果在 iteration k 入库、
          同轮末尾已发一次、k+1 轮再发一次 ⇒ k+1 末尾即可剪。未标记的结果**不剪**（保守）。
        - **滑出窗口**：消息索引 < ``len(messages) - recent_window``（窗口按**消息条数**，
          非轮数）。
        - **单条超阈**：token 或字节任一超阈（``tool_result_policy``），**不受窗口保护**
          ——超阈结果即使新鲜、仍在窗内也替换（穿透窗口），但受「已消费一轮」保护。

        ``added_iterations`` 是外部标记灌入通道：``None`` 时走 spiller 自身的 ``mark``
        状态；非 ``None`` 时以传入的外部映射为准（**覆盖注入**，供显式指定消费轮次的调用）。

        ``save(text) -> ref`` 由调用方注入（``loop.py`` 在 ``run()`` 期构造 store 与
        scope）；返回 ``None`` 或抛异常时**不谎称可回读**（D8）——仍替换正文使内存有界，
        但标记 ``[truncated]``。本方法**不碰 I/O**，只调注入的回调与判据纯函数。

        任何替换后 MUST 置 ``message._tokens = None``（D10），否则 ``count_tokens``
        返旧值、反复误触发压缩。
        """
        marks = self._iterations if added_iterations is None else added_iterations
        stats_spilled = 0
        stats_bytes = 0
        window_start = len(messages) - self.recent_window
        for index, message in enumerate(messages):
            if message.role != "tool" or not message.tool_call_id:
                continue
            if _is_spilled_preview(message.content):
                continue  # already a preview — idempotent
            added = marks.get(message.tool_call_id)
            if added is None or added > current_iteration - 1:
                continue  # fresh / never-marked ⇒ keep full text
            slid_out = index < window_start
            oversized = _exceeds_single_threshold(
                message.content, max_tokens=self.max_tokens, counter=self._counter,
            )
            if not (slid_out or oversized):
                continue
            before = _content_bytes(message.content)
            ref: str | None = None
            if save is not None:
                try:
                    ref = save(_flatten(message.content))
                except Exception:
                    logger.warning("[Memory] tool result spill failed", exc_info=True)
                    ref = None
            preview = _make_preview(message.content, ref=ref)
            message.content = preview
            message._tokens = None
            stats_spilled += 1
            stats_bytes += max(0, before - _content_bytes(preview))
        if stats_spilled:
            logger.info(
                "[Memory] spilled %d tool result(s), released %d bytes",
                stats_spilled, stats_bytes,
            )
        return PruneStats(messages_spilled=stats_spilled, bytes_released=stats_bytes)

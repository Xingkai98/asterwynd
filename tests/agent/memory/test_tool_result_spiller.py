"""``ToolResultSpiller`` 直接单测（change ``tool-result-spill-module``）。

覆盖内聚后 spiller 的三方法语义：
- ``mark`` 后剪陈旧、未 ``mark`` 不剪（保守）；
- ``reset`` 预置 ``-1``（resume 历史可剪）、并覆盖既有标记；
- ``spill`` 幂等（预览不被二次剪）；
- ``PruneStats`` 数值（``messages_spilled`` / ``bytes_released``）；
- ``added_iterations`` 覆盖注入（``None`` 走自身 mark 状态）；
- **counter 注入（D2 头号正确性风险）**：``monkeypatch`` 替换 ``manager._count_tokens``
  后 spiller 的阈值判定随之变化——且**必须经 ``MemoryManager`` 触发**
  （``manager.tool_result_spiller``），否则测的是测试自建的 counter，是假通过。
"""
import pytest

from agent.artifact_store import extract_result_ref
from agent.memory import manager as _manager_mod
from agent.memory.manager import MemoryManager
from agent.memory.tool_result_policy import TRUNCATED_MARKER
from agent.message import Message, tool_result_message


def _counter(text: str) -> int:
    return len(text) // 4


@pytest.fixture(autouse=True)
def _fast_token_counter(monkeypatch):
    """O(1) 近似计数替换 tiktoken（口径与 ``_count_tokens`` 的 tiktoken-缺失回退一致）。"""
    monkeypatch.setattr(_manager_mod, "_count_tokens", _counter)


def _big(n_chars: int) -> str:
    return "A" * n_chars


class _TC:
    def __init__(self, id, name):
        self.id = id
        self.name = name


def _tool_then_assistant(tool_call_id: str, content):
    assistant = Message(role="assistant", content="", tool_calls=[_TC(tool_call_id, "Read")])
    return [assistant, tool_result_message(tool_call_id, content)]


# ── mark / reset 状态语义 ────────────────────────────────────────────────


def test_mark_then_spill_prunes_stale_result():
    """``mark`` 登记的陈旧结果（越过窗口或超阈）被剪成预览 + ref。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 3)

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[-1].content) == "artifact://agent/s-1/k"


def test_unmarked_result_is_not_pruned_conservative():
    """未 ``mark`` 的结果**不剪**（保守：无标记 ⇒ 当作未消费）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=9, save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 0
    assert messages[-1].content.startswith("AAA")  # still full text


def test_reset_presets_history_consumed():
    """``reset`` 把 messages 中既有工具结果预置 ``-1``（已消费）⇒ 可剪（M2 修复点）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.reset(messages)

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=0, save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 1


def test_reset_overrides_existing_marks():
    """``reset`` 清空本 spiller 标记后再预置 —— 已被 mark 的 id 被覆盖为 ``-1``。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 100)   # would be "fresh" at iteration 100
    manager.tool_result_spiller.reset(messages)   # replaced with -1

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=0, save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 1


# ── spill 幂等 与 PruneStats 数值 ────────────────────────────────────────


def test_spill_is_idempotent():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 3)
    save = lambda text: "artifact://agent/s-1/k"  # noqa: E731

    first = manager.tool_result_spiller.spill(messages, current_iteration=4, save=save)
    second = manager.tool_result_spiller.spill(messages, current_iteration=5, save=save)

    assert first.messages_spilled == 1
    assert second.messages_spilled == 0          # preview is idempotent


def test_spill_stats_report_counts_and_released_bytes():
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 3)

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 1
    assert stats.bytes_released > 0
    assert stats.to_metadata() == {
        "messages_spilled": 1,
        "bytes_released": stats.bytes_released,
    }


def test_spill_without_save_marks_truncated_not_fake_ref():
    """无 ``save`` ⇒ 内存有界但标记如实为 ``[truncated]``，不指向 ref（D8）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 3)

    stats = manager.tool_result_spiller.spill(messages, current_iteration=4, save=None)

    assert stats.messages_spilled == 1
    assert extract_result_ref(messages[-1].content) is None
    assert messages[-1].content.endswith(TRUNCATED_MARKER)


# ── added_iterations 覆盖注入 ────────────────────────────────────────────


def test_added_iterations_override_uses_external_map():
    """非 ``None`` 时以外部映射为准（覆盖 spiller 自身 mark 状态）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 1)   # own state says stale

    # External map says "not yet consumed a round" ⇒ keep full text.
    fresh = manager.tool_result_spiller.spill(
        messages, current_iteration=3, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert fresh.messages_spilled == 0
    assert messages[-1].content.startswith("AAA")

    # External map says consumed ⇒ prune.
    stale = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations={"c1": 3},
        save=lambda text: "artifact://agent/s-1/k",
    )
    assert stale.messages_spilled == 1


def test_added_iterations_none_falls_back_to_mark_state():
    """``added_iterations=None`` 走 spiller 自身 ``mark`` 状态。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=10)
    messages = _tool_then_assistant("c1", _big(400_000))
    manager.tool_result_spiller.mark("c1", 3)

    stats = manager.tool_result_spiller.spill(
        messages, current_iteration=4, added_iterations=None,
        save=lambda text: "artifact://agent/s-1/k",
    )

    assert stats.messages_spilled == 1


# ── counter 注入（D2 头号风险，必须经 MemoryManager 触发）──────────────────


def test_counter_injection_via_manager_controls_threshold(monkeypatch):
    """D2：替换 ``manager._count_tokens`` 后 spiller 阈值判定随之变化。

    **必须经 ``MemoryManager``（``manager.tool_result_spiller``）触发**——若直接
    ``ToolResultSpiller(counter=<自建函数>)`` 构造，测的是测试自己的闭包，不覆盖生产
    注入点（即无法发现「spiller 静态导入 ``_count_tokens`` 导致 monkeypatch 静默失效」）。
    这里内容仅 100 字节，不会因字节维或窗口被剪，唯一决定剪不剪的是 counter。
    """
    manager = MemoryManager(max_tokens=80_000, recent_window=100)
    messages = _tool_then_assistant("c1", "x" * 100)
    manager.tool_result_spiller.mark("c1", 1)
    save = lambda text: "artifact://agent/s-1/k"  # noqa: E731

    # Counter 报出巨大 token 数 ⇒ 单条超阈 ⇒ 剪。
    monkeypatch.setattr(_manager_mod, "_count_tokens", lambda text: 10 ** 9)
    oversized = manager.tool_result_spiller.spill(messages, current_iteration=2, save=save)
    assert oversized.messages_spilled == 1

    # Counter 报出极小 token 数 ⇒ 不超阈、也未滑出窗口 ⇒ 不剪。
    messages2 = _tool_then_assistant("c2", "y" * 100)
    manager.tool_result_spiller.mark("c2", 1)
    monkeypatch.setattr(_manager_mod, "_count_tokens", lambda text: 1)
    small = manager.tool_result_spiller.spill(messages2, current_iteration=2, save=save)
    assert small.messages_spilled == 0


def test_is_oversized_result_shares_same_counter_seam(monkeypatch):
    """R2：``is_oversized_result`` 与 spiller 共用同一 counter 解析点（同受 monkeypatch 影响）。"""
    manager = MemoryManager(max_tokens=80_000, recent_window=100)
    monkeypatch.setattr(_manager_mod, "_count_tokens", lambda text: 10 ** 9)
    assert manager.is_oversized_result("x" * 100) is True
    monkeypatch.setattr(_manager_mod, "_count_tokens", lambda text: 1)
    assert manager.is_oversized_result("x" * 100) is False

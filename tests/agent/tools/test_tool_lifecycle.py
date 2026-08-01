"""Tests for ToolLifecycle — four-state lifecycle state machine.

Covers design.md 第二轮 Q6：low_traffic → deprecation → grace → removed，
显式驱动（不依赖 quality），removed 从 get_all_schemas 排除。

可观测状态模型：mark_deprecated() 直接进入 GRACE（grace 立即开始，notice 可用），
GRACE 到期 → REMOVED。DEPRECATION 是枚举触发态，可观测路径为
LOW_TRAFFIC → GRACE → REMOVED。
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agent.tools.governance.lifecycle import (
    LifecycleState,
    ToolLifecycle,
)


class TestToolLifecycleStates:
    def test_new_tool_defaults_low_traffic(self) -> None:
        lc = ToolLifecycle()
        assert lc.get_state("ReadTool") is LifecycleState.LOW_TRAFFIC

    def test_mark_deprecated_enters_grace(self) -> None:
        """mark_deprecated 触发 deprecation，grace 立即开始（可观测为 GRACE）"""
        lc = ToolLifecycle(grace_period=timedelta(days=7))
        lc.mark_deprecated("ReadTool")
        assert lc.get_state("ReadTool") is LifecycleState.GRACE

    def test_grace_to_removed_after_period(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=7))
        lc.mark_deprecated("ReadTool")
        lc.advance_time(timedelta(days=7))
        assert lc.get_state("ReadTool") is LifecycleState.REMOVED

    def test_grace_not_removed_before_period(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=7))
        lc.mark_deprecated("ReadTool")
        lc.advance_time(timedelta(days=6))
        assert lc.get_state("ReadTool") is LifecycleState.GRACE

    def test_unknown_tool_returns_low_traffic(self) -> None:
        lc = ToolLifecycle()
        assert lc.get_state("UnknownTool") is LifecycleState.LOW_TRAFFIC


class TestToolLifecycleVisibility:
    def test_removed_tool_not_visible(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=1))
        lc.mark_deprecated("ReadTool")
        lc.advance_time(timedelta(days=1))
        assert not lc.is_visible("ReadTool")

    def test_active_tool_visible(self) -> None:
        lc = ToolLifecycle()
        assert lc.is_visible("ReadTool")

    def test_grace_tool_visible(self) -> None:
        """grace 期间仍可见（deprecation notice 提示，不硬性隐藏）"""
        lc = ToolLifecycle(grace_period=timedelta(days=7))
        lc.mark_deprecated("ReadTool")
        assert lc.is_visible("ReadTool")

    def test_deprecation_notice_for_grace(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=7))
        lc.mark_deprecated("ReadTool")
        notice = lc.deprecation_notice("ReadTool")
        assert notice is not None
        assert "ReadTool" in notice

    def test_no_notice_for_active(self) -> None:
        lc = ToolLifecycle()
        assert lc.deprecation_notice("ReadTool") is None

    def test_no_notice_for_removed(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=1))
        lc.mark_deprecated("ReadTool")
        lc.advance_time(timedelta(days=1))
        assert lc.deprecation_notice("ReadTool") is None


class TestToolLifecyclePersistence:
    def test_manual_removal(self) -> None:
        lc = ToolLifecycle()
        lc.mark_removed("ReadTool")
        assert lc.get_state("ReadTool") is LifecycleState.REMOVED

    def test_zero_grace_immediate_removal(self) -> None:
        lc = ToolLifecycle(grace_period=timedelta(days=0))
        lc.mark_deprecated("ReadTool")
        assert lc.get_state("ReadTool") is LifecycleState.REMOVED

"""Tests for CostLedger — session/phase/tool cost attribution + JSONL persistence.

Covers design.md 第二/三轮：CostLedger 按 session/phase/tool 三维记账，
bill() 输出分组账单，flush/load JSONL 持久化支持跨 session 历史统计。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.cost_tracker import CostLedger


class TestCostLedgerRecord:
    def test_record_accumulates_total(self) -> None:
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 500, session_id="s1", phase="building")
        ledger.record("gpt-4o-mini", 2000, 1000, session_id="s1", phase="building")
        # 3000 in * 0.15/1M + 1500 out * 0.60/1M
        assert ledger.total() > 0

    def test_bill_by_session(self) -> None:
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        ledger.record("gpt-4o-mini", 2000, 0, session_id="s2", phase="planning")
        by_session = ledger.bill()["by_session"]
        assert set(by_session.keys()) == {"s1", "s2"}
        assert by_session["s1"]["tokens"] == 1000
        assert by_session["s2"]["tokens"] == 2000

    def test_bill_by_phase(self) -> None:
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        ledger.record("gpt-4o-mini", 2000, 0, session_id="s1", phase="planning")
        by_phase = ledger.bill()["by_phase"]
        assert set(by_phase.keys()) == {"building", "planning"}

    def test_bill_by_tool(self) -> None:
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building", tool_name="Bash")
        ledger.record("gpt-4o-mini", 2000, 0, session_id="s1", phase="building", tool_name="Edit")
        by_tool = ledger.bill()["by_tool"]
        assert set(by_tool.keys()) == {"Bash", "Edit"}

    def test_tool_none_grouped_as_no_tool(self) -> None:
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        by_tool = ledger.bill()["by_tool"]
        assert "no_tool" in by_tool


class TestCostLedgerPersistence:
    def test_flush_and_load_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 500, session_id="s1", phase="building", tool_name="Bash")
        ledger.flush(path)

        loaded = CostLedger()
        loaded.load(path)
        assert loaded.total() == ledger.total()
        assert loaded.bill()["by_session"] == ledger.bill()["by_session"]

    def test_flush_appends_not_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        ledger.flush(path)
        # second flush appends
        ledger.record("gpt-4o-mini", 2000, 0, session_id="s2", phase="planning")
        ledger.flush(path)

        loaded = CostLedger()
        loaded.load(path)
        by_session = loaded.bill()["by_session"]
        assert set(by_session.keys()) == {"s1", "s2"}  # both persisted

    def test_repeated_flush_without_new_records_no_duplicates(self, tmp_path: Path) -> None:
        """回归：同一 ledger 重复 flush（主/子 loop 共享实例场景）不得重复 append。"""
        path = tmp_path / "ledger.jsonl"
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        ledger.flush(path)
        # 共享实例被第二个 loop 再次 flush，无新增记录时不应重复写 s1
        ledger.flush(path)
        ledger.flush(path)

        loaded = CostLedger()
        loaded.load(path)
        assert loaded.bill()["by_session"]["s1"]["tokens"] == 1000
        assert loaded.total() > 0

    def test_load_then_flush_does_not_rewrite_history(self, tmp_path: Path) -> None:
        """回归：load 恢复历史后 flush 新条目，不应重写已加载的历史。"""
        path = tmp_path / "ledger.jsonl"
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 0, session_id="s1", phase="building")
        ledger.flush(path)

        loaded = CostLedger()
        loaded.load(path)
        loaded.record("gpt-4o-mini", 2000, 0, session_id="s2", phase="planning")
        loaded.flush(path)

        final = CostLedger()
        final.load(path)
        by_session = final.bill()["by_session"]
        assert set(by_session.keys()) == {"s1", "s2"}
        assert by_session["s1"]["tokens"] == 1000
        assert by_session["s2"]["tokens"] == 2000

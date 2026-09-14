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


class TestCostLedgerAttributionDimensions:
    """四维归因（change ``workflow-budget-attribution``，task 2.1；D3/Q12/Q16）。

    - ``record`` 增可选归因键 ``workflow_id``/``node_id``/``depth``/``edge``
      及 cache 两档（``cache_read_tokens``/``cache_write_tokens``）；
    - ``bill()`` 增 ``by_workflow``/``by_node``/``by_depth``/``by_edge``；
    - **兼容铁律**：不带归因键的记录，三维账单（by_session/by_phase/by_tool）
      必须逐字节不变（既有断言 + JSONL 历史记录都依赖它）。
    """

    def test_record_without_attribution_keys_keeps_three_dim_bill_unchanged(self) -> None:
        """兼容铁律：无归因键的记录，三维账单的键集合与值语义逐项不变。"""
        ledger = CostLedger()
        ledger.record("gpt-4o-mini", 1000, 500, session_id="s1", phase="building")
        # 与「record 改造前」的期望值同源：3000 in * 0.15/1M + 1500 out * 0.60/1M
        expected_cost = (1000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.60
        assert ledger.bill()["by_session"] == {
            "s1": {"tokens": 1500, "cost": expected_cost}
        }
        assert set(ledger.bill()["by_phase"].keys()) == {"building"}
        assert set(ledger.bill()["by_tool"].keys()) == {"no_tool"}
        # 四维分桶存在但为空（无归因键的记录不进桶）
        bill = ledger.bill()
        assert bill["by_workflow"] == {}
        assert bill["by_node"] == {}
        assert bill["by_depth"] == {}
        assert bill["by_edge"] == {}

    def test_record_accepts_cache_tokens_and_prices_four_tiers(self) -> None:
        """Q12：``record`` 扩 cache 参数，**四维分桶**走 ``compute_cost_cached`` 四档。

        对齐 ``compute_cost_cached``：cache read = 0.1x fresh input，
        cache write = 1.25x fresh input（Anthropic prompt-caching 经济学）。

        legacy 三维账单（by_session/by_phase/by_tool）与 ``total()`` 保持二档口径
        不变——Q12 只要求 by_node/by_edge 与 workflow 账本对得上，而既有断言
        （``test_cost_ledger_unknown_model_records_tokens_without_cost`` 等）锁定
        了三维账单的 None-跳过语义。
        """
        ledger = CostLedger()
        ledger.record(
            "claude-opus-4",
            1_000_000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            node_id="n1",
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        )
        # 四维：1M fresh * 15 + 1M read * 1.50 + 1M write * 18.75 = 35.25
        assert ledger.bill()["by_node"]["n1"]["cost"] == pytest.approx(35.25)
        # legacy 三维：只算 fresh input（1M * 15）——口径与改造前一致
        assert ledger.total() == pytest.approx(15.0)

    def test_by_workflow_buckets(self) -> None:
        ledger = CostLedger()
        ledger.record(
            "gpt-4o-mini", 1000, 0, session_id="s1", phase="building", workflow_id="wf1"
        )
        ledger.record(
            "gpt-4o-mini", 2000, 0, session_id="s1", phase="building", workflow_id="wf2"
        )
        by_workflow = ledger.bill()["by_workflow"]
        assert set(by_workflow.keys()) == {"wf1", "wf2"}
        assert by_workflow["wf1"]["tokens"] == 1000
        assert by_workflow["wf2"]["tokens"] == 2000

    def test_by_node_buckets_and_identifies_priciest(self) -> None:
        ledger = CostLedger()
        ledger.record(
            "gpt-4o",
            1_000_000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            node_id="cheap",
        )
        ledger.record(
            "gpt-4o",
            2_000_000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            node_id="pricey",
        )
        by_node = ledger.bill()["by_node"]
        assert set(by_node.keys()) == {"cheap", "pricey"}
        assert by_node["pricey"]["tokens"] == 2_000_000
        priciest = max(by_node, key=lambda key: by_node[key]["cost"])
        assert priciest == "pricey"

    def test_by_depth_buckets_use_graph_distance(self) -> None:
        """Q7/Q13：``by_depth`` 的键是 workflow 图距（0=leaf/1=shard/2=domain/3+=root）。"""
        ledger = CostLedger()
        for depth, tokens in ((0, 100), (1, 200), (2, 300), (3, 400), (5, 500)):
            ledger.record(
                "gpt-4o-mini",
                tokens,
                0,
                session_id="s1",
                phase="building",
                workflow_id="wf1",
                depth=depth,
            )
        by_depth = ledger.bill()["by_depth"]
        # 3+ 折进同一桶（与 ``budget_for_distance`` 的 3+=root 同口径）
        assert set(by_depth.keys()) == {"0", "1", "2", "3+"}
        assert by_depth["0"]["tokens"] == 100
        assert by_depth["1"]["tokens"] == 200
        assert by_depth["2"]["tokens"] == 300
        assert by_depth["3+"]["tokens"] == 900

    def test_by_edge_buckets(self) -> None:
        ledger = CostLedger()
        ledger.record(
            "gpt-4o-mini",
            1000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            edge="a|b->join",
        )
        ledger.record(
            "gpt-4o-mini",
            2000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            edge="planner->fan",
        )
        by_edge = ledger.bill()["by_edge"]
        assert set(by_edge.keys()) == {"a|b->join", "planner->fan"}
        assert by_edge["a|b->join"]["tokens"] == 1000

    def test_unknown_model_marks_bucket_estimated(self) -> None:
        """Q16：未知模型（``CostEstimate.known=False``）的桶标 ``estimated: true``，
        不静默混入已知模型桶。"""
        ledger = CostLedger()
        ledger.record(
            "totally-unknown-model",
            1000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            node_id="n1",
            edge="a->n1",
            depth=0,
        )
        bill = ledger.bill()
        assert bill["by_workflow"]["wf1"]["estimated"] is True
        assert bill["by_node"]["n1"]["estimated"] is True
        assert bill["by_edge"]["a->n1"]["estimated"] is True
        # tokens 口径 = input + output（不含 cache），单位 USD
        assert bill["by_node"]["n1"]["tokens"] == 1000

    def test_known_model_bucket_is_not_marked_estimated(self) -> None:
        ledger = CostLedger()
        ledger.record(
            "gpt-4o-mini",
            1000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
        )
        assert ledger.bill()["by_workflow"]["wf1"]["estimated"] is False

    def test_bucket_values_round_to_nine_places(self) -> None:
        """Q16：分桶 cost 与 envelope ``total_cost`` 对齐为 9 位。"""
        ledger = CostLedger()
        ledger.record(
            "gpt-4o-mini",
            1,
            1,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
        )
        cost = ledger.bill()["by_workflow"]["wf1"]["cost"]
        assert cost == round(cost, 9)

    def test_tokens_exclude_cache(self) -> None:
        """Q16：tokens 口径 = input + output（不含 cache read/write）。"""
        ledger = CostLedger()
        ledger.record(
            "claude-opus-4",
            100,
            50,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            cache_read_tokens=10_000,
            cache_write_tokens=20_000,
        )
        assert ledger.bill()["by_workflow"]["wf1"]["tokens"] == 150

    def test_ledger_flush_load_roundtrips_attribution(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = CostLedger()
        ledger.record(
            "gpt-4o-mini",
            1000,
            0,
            session_id="s1",
            phase="building",
            workflow_id="wf1",
            node_id="n1",
            depth=1,
            edge="a->n1",
        )
        ledger.flush(path)

        loaded = CostLedger()
        loaded.load(path)
        assert loaded.bill()["by_workflow"] == ledger.bill()["by_workflow"]
        assert loaded.bill()["by_depth"] == ledger.bill()["by_depth"]
        assert loaded.bill()["by_edge"] == ledger.bill()["by_edge"]


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

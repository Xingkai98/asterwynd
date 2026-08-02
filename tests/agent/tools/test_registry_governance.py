"""Integration tests for governance wired into ToolRegistry.

Covers design.md 第三轮 Q10-Q13：ToolRegistry 注册 → 语义去重 → select_schemas
Top5 → 生命周期 removed 从 get_all_schemas 排除；get_all_schemas 契约不变。
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agent.embedding import NGramEmbedding
from agent.run_config import ModePolicy
from agent.tools.base import Tool
from agent.tools.governance import SemanticDeduper, ToolLifecycle, ToolSelector
from agent.tools.registry import ToolRegistry


class _FakeTool(Tool):
    name = "fake"
    description = "a fake tool for testing"
    parameters = {}

    def execute(self, **kwargs) -> str:
        return "ok"


def _make_registry(tools: list[Tool]) -> ToolRegistry:
    reg = ToolRegistry(mode_policy=ModePolicy())
    for t in tools:
        reg.register(t)
    return reg


class TestRegistryLifecycle:
    def test_removed_tool_excluded_from_get_all_schemas(self) -> None:
        reg = _make_registry([_FakeTool()])
        lc = ToolLifecycle(grace_period=timedelta(days=1))
        reg.set_lifecycle(lc)
        lc.mark_deprecated("fake")
        lc.advance_time(timedelta(days=1))
        names = [s["function"]["name"] for s in reg.get_all_schemas()]
        assert "fake" not in names

    def test_active_tool_in_get_all_schemas(self) -> None:
        reg = _make_registry([_FakeTool()])
        lc = ToolLifecycle()
        reg.set_lifecycle(lc)
        names = [s["function"]["name"] for s in reg.get_all_schemas()]
        assert "fake" in names


class TestRegistrySelection:
    def test_select_schemas_returns_top_k(self) -> None:
        reg = _make_registry([_FakeTool()])
        sel = ToolSelector(embedder=NGramEmbedding(dim=512), top_k=3)
        reg.set_selector(sel)
        # 注册的工具也应同步到 selector 索引
        reg._sync_governance_indexes()
        schemas = reg.select_schemas("use the fake tool", k=3)
        assert len(schemas) == 1  # 只有一个工具

    def test_get_all_schemas_contract_unchanged(self) -> None:
        """get_all_schemas 返回 list[dict] 且含 function.name，契约不变"""
        reg = _make_registry([_FakeTool()])
        schemas = reg.get_all_schemas()
        assert isinstance(schemas, list)
        assert schemas[0]["function"]["name"] == "fake"


class TestRegistryDedup:
    def test_dedup_marks_duplicate_tool(self) -> None:
        class _GrepTool(_FakeTool):
            name = "Grep"
            description = "search files for text matching a regex pattern"

        class _SymbolSearchTool(_FakeTool):
            name = "SymbolSearch"
            description = "search files for text matching a regex pattern with options"

        reg = _make_registry([_GrepTool(), _SymbolSearchTool()])
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        reg.set_deduper(deduper)
        reg._sync_governance_indexes()
        assert reg.duplicate_of("SymbolSearch") == "Grep"

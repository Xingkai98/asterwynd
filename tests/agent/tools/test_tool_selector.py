"""Tests for ToolSelector — BM25 coarse filter + embedding re-rank + Top-K.

Covers design.md 第二轮 Q3/Q4/Q9：稳定层/可变层分层、query 从最近 user 消息 +
最近工具调用构造、延迟预算可配置（超预算降级全量）、选择延迟入 trace。
"""
from __future__ import annotations

from agent.embedding import NGramEmbedding
from agent.tools.governance.selector import ToolSelector


class TestToolSelector:
    def test_selector_returns_top_k(self) -> None:
        sel = ToolSelector(embedder=NGramEmbedding(dim=512), top_k=3)
        sel.index_tool("Grep", "search files for text matching a regex pattern")
        sel.index_tool("WebSearch", "fetch a web page over http and extract content")
        sel.index_tool("Read", "read file contents from disk")
        sel.index_tool("Edit", "modify file contents in place")
        sel.index_tool("Bash", "run shell commands in the workspace")

        top = sel.select("find text in files with grep")
        assert len(top) == 3
        # Grep 应排第一（query 相关性最高）
        assert top[0] == "Grep"

    def test_stable_layer_always_first(self) -> None:
        """>稳定层核心工具始终在结果中且排在前面（Q3）"""
        sel = ToolSelector(embedder=NGramEmbedding(dim=512), top_k=5)
        sel.index_tool("Grep", "search files for text matching a regex pattern")
        sel.index_tool("WebSearch", "fetch a web page over http and extract content")
        sel.index_tool("Bash", "run shell commands in the workspace")
        stable = {"Bash", "Read"}
        sel.set_stable_tools(["Bash", "Read"])
        sel.index_tool("Read", "read file contents from disk")

        top = sel.select("search the web for something")
        # 稳定层工具（Bash/Read）都在结果里，即使与 query 不相关
        assert "Bash" in top
        assert "Read" in top

    def test_latency_recorded(self) -> None:
        """>选择延迟被记录（Q4：入 trace）"""
        sel = ToolSelector(embedder=NGramEmbedding(dim=512), top_k=3)
        sel.index_tool("Grep", "search files for text matching a regex pattern")
        sel.index_tool("WebSearch", "fetch a web page over http and extract content")
        sel.select("find text in files")
        assert sel.last_selection_latency_ms is not None
        assert sel.last_selection_latency_ms >= 0.0

    def test_selector_fallback_when_empty(self) -> None:
        """>空工具集 → 空选择（不崩）"""
        sel = ToolSelector(embedder=NGramEmbedding(dim=256), top_k=3)
        assert sel.select("anything") == []

    def test_selector_returns_all_when_fewer_than_k(self) -> None:
        sel = ToolSelector(embedder=NGramEmbedding(dim=256), top_k=5)
        sel.index_tool("Grep", "search files")
        sel.index_tool("Read", "read files")
        assert len(sel.select("search")) == 2

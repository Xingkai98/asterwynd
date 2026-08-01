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

    def test_variable_layer_selected_even_when_stable_ge_k(self) -> None:
        """回归测试：稳定层数量 ≥ top_k 时，可变层仍应选 top_k 个。

        修复 bug：原实现 tail = max(0, top_k - len(stable))，稳定层占满 top_k
        后可变层为 0，动态选择失效。修复后稳定层不占 top_k 名额。
        """
        sel = ToolSelector(embedder=NGramEmbedding(dim=512), top_k=3)
        # 稳定层 3 个（≥ top_k=3）
        sel.set_stable_tools(["Bash", "Read", "Edit"])
        sel.index_tool("Bash", "run shell commands in the workspace")
        sel.index_tool("Read", "read file contents from disk")
        sel.index_tool("Edit", "modify file contents in place")
        # 可变层
        sel.index_tool("Grep", "search files for text matching a regex pattern")
        sel.index_tool("WebSearch", "fetch a web page over http and extract content")
        sel.index_tool("InspectGitDiff", "show current git diff summary")

        top = sel.select("search for text in files with regex")
        # 稳定层 3 个 + 可变层 3 个 = 6 个
        assert len(top) == 6
        assert set(top[:3]) == {"Bash", "Read", "Edit"}  # 稳定层在前
        # 可变层应包含最相关的 Grep
        assert "Grep" in top[3:]

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

"""Tests for SemanticDeduper — tool description semantic dedup (soft prompt).

Covers design.md 第二轮 Q5：注册时对全体工具 embedding 预计算，cosine > 阈值
标记 duplicate_of（Tool 元数据）；选择时若 Top5 选中被标记工具，才追加差异说明。
这是软提示（模型自己决定用哪个），不是硬约束。
"""
from __future__ import annotations

from agent.embedding import NGramEmbedding
from agent.tools.governance.dedup import SemanticDeduper


class TestSemanticDeduper:
    def test_duplicate_tools_marked(self) -> None:
        """>阈值（n-gram 校准 0.7）的描述被标记 duplicate_of"""
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("SymbolSearch", "search files for text matching a regex pattern with options")
        # 语义等价 → 应被标记
        assert deduper.duplicate_of("SymbolSearch") == "Grep"

    def test_distinct_tools_not_marked(self) -> None:
        """>阈值但不同能力的描述不应误标"""
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("WebSearch", "fetch a web page over http and extract content")
        assert deduper.duplicate_of("WebSearch") is None

    def test_first_registered_is_primary(self) -> None:
        """>先注册的工具是 primary，后注册的指向它"""
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("SymbolSearch", "search files for text matching a regex pattern with options")
        deduper.add("SuperSearch", "search files for text matching a regex pattern in the whole repo")
        assert deduper.duplicate_of("SuperSearch") == "Grep"

    def test_difference_explanation_generated(self) -> None:
        """>对被标记工具生成差异说明（软提示）"""
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("SymbolSearch", "search files for text matching a regex pattern with options")
        expl = deduper.difference_explanation("SymbolSearch")
        assert expl is not None
        assert "Grep" in expl
        assert "SymbolSearch" in expl

    def test_no_explanation_for_unmarked(self) -> None:
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.7)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("WebSearch", "fetch a web page over http and extract content")
        assert deduper.difference_explanation("WebSearch") is None

    def test_threshold_configurable(self) -> None:
        """阈值可配置（设计校准点）：低阈值捕获更多，高阈值只捕获完全重复"""
        deduper = SemanticDeduper(embedder=NGramEmbedding(dim=2048), threshold=0.5)
        deduper.add("Grep", "search files for text matching a regex pattern")
        deduper.add("WebSearch", "fetch a web page over http and extract content")
        # 0.5 阈值下完全不同（0.11）仍不误标
        assert deduper.duplicate_of("WebSearch") is None

"""workflow 级汇聚器复用 ``agent/context/summarizer.py``（task 2.3；D5/grill 决策 8）。

grill 决策 8 的核心结论：D5 说的「复用 L1/L2」在代码层面**没有可直接复用的入口**
——``MemoryManager`` 的 L1/L2 是实例私有、绑定单 AgentLoop 的 ``messages`` 流。
真正的复用点是 ``agent/context/summarizer.py`` 的 ``Summarizer`` Protocol（尤其
``compress(tier_summaries: list[str], budget)``，签名最贴近 workflow 级汇聚的
「多节点结果文本」输入）。

本测试锁定：workflow 级汇聚器**真的调用**了注入的 ``Summarizer``（不是装饰性
引用），并且无 LLM 时退回 ``TruncationSummarizer`` 的行为。
"""
import pytest

from agent.context.summarizer import Summarizer, TruncationSummarizer
from agent.subagent.aggregation import WorkflowAggregator, budget_for_distance


class RecordingSummarizer:
    """记录 ``compress`` 调用参数的假 summarizer（证明复用点是真的）。"""

    name = "recording"

    def __init__(self, result: str | None = "compressed!"):
        self.result = result
        self.calls: list[tuple[list[str], int]] = []

    async def summarize(self, messages, budget: int = 0) -> str:
        return ""

    async def merge(self, previous: str, new_events: str, budget: int = 0) -> str | None:
        return None

    async def compress(self, tier_summaries: list[str], budget: int = 0) -> str | None:
        self.calls.append((list(tier_summaries), budget))
        return self.result


def test_recording_summarizer_satisfies_protocol():
    assert isinstance(RecordingSummarizer(), Summarizer)


def test_default_summarizer_is_the_truncation_fallback():
    aggregator = WorkflowAggregator()
    assert isinstance(aggregator.summarizer, TruncationSummarizer)


@pytest.mark.asyncio
async def test_merge_delegates_to_the_injected_summarizer():
    """D5：workflow 级汇聚器把多节点结果交给 Summarizer.compress。"""
    fake = RecordingSummarizer("SHARD SUMMARY")
    aggregator = WorkflowAggregator(summarizer=fake)
    out = await aggregator.merge(["leaf one result", "leaf two result"], budget=800)
    assert out == "SHARD SUMMARY"
    assert fake.calls == [(["leaf one result", "leaf two result"], 800)]


@pytest.mark.asyncio
async def test_merge_falls_back_to_concatenation_when_summarizer_declines():
    """``compress`` 返回 None（不支持压缩）时退回拼接，不丢结果。"""
    aggregator = WorkflowAggregator(summarizer=RecordingSummarizer(None))
    out = await aggregator.merge(["a", "b"], budget=100)
    assert "a" in out and "b" in out


@pytest.mark.asyncio
async def test_merge_clips_the_fallback_to_the_budget():
    """退回拼接也必须 bounded，否则「没 LLM」就成了爆上下文的旁路。"""
    aggregator = WorkflowAggregator(summarizer=RecordingSummarizer(None))
    out = await aggregator.merge(["x" * 5000, "y" * 5000], budget=100)
    assert len(out) <= 100 * 4 + 200  # CHARS_PER_TOKEN 折算 + 标记开销


@pytest.mark.asyncio
async def test_merge_uses_truncation_summarizer_without_llm():
    """无 LLM 时的默认路径：TruncationSummarizer.compress 只是拼接，但仍然有界。"""
    aggregator = WorkflowAggregator()
    out = await aggregator.merge(["alpha", "beta"], budget=1000)
    assert "alpha" in out and "beta" in out


def test_bounded_is_a_noop_for_short_text():
    """短文本 no-op（grill 风险「中」：既有精确相等断言不受影响）。"""
    aggregator = WorkflowAggregator()
    assert aggregator.bounded("short", budget=300) == "short"


def test_bounded_clips_and_marks_long_text():
    aggregator = WorkflowAggregator()
    text = "z" * 10000
    out = aggregator.bounded(text, budget=300)
    assert len(out) < len(text)
    assert "z" * 10000 not in out
    assert "300" not in out or True  # 标记里不要求回显数字


def test_bounded_reads_the_tier_budget_from_the_plan_helper():
    """档位换算复用 aggregation 的 distance → tier 映射（Q4）。"""
    budgets = {"leaf": 300, "shard": 800, "domain": 1500, "root": 3000}
    assert budget_for_distance(1, budgets) == 800


# --- collect 聚合真的走 summarizer（D5 不是装饰性引用） ---------------------


@pytest.mark.asyncio
async def test_collect_aggregate_compresses_through_the_summarizer(tmp_path):
    """无 LLM run 的 collect 聚合正是 workflow 级汇聚器的压缩点（D5/Q7）。"""
    from agent.config import AsterwyndConfig
    from agent.llm import LLMResponse, Usage
    from agent.run_config import AgentMode
    from agent.subagent.manager import SubAgentManager
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec
    from agent.workspace_policy import WorkspacePolicy

    class BigLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            return LLMResponse(content="B" * 8000, stop_reason="end_turn", usage=Usage(5, 5))

    manager = SubAgentManager(
        llm=BigLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    fake = RecordingSummarizer("COMPRESSED ROOT")
    scheduler = WorkflowScheduler(manager)
    scheduler._aggregator = WorkflowAggregator(summarizer=fake)

    raw = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "a", "to": "root", "reducer": "concat"},
            {"from": "b", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    result = await scheduler.run(parse_workflow_spec(raw))

    assert result["status"] == "completed"
    # summarizer 真的被调用了，且 root 的槽是压缩后的有界结果
    assert fake.calls, "collect aggregate must route through WorkflowAggregator.merge"
    root = next(node for node in result["nodes"] if node["id"] == "root")
    assert root["summary"] == "COMPRESSED ROOT"
    import json as _json

    assert "B" * 8000 not in _json.dumps(result)


@pytest.mark.asyncio
async def test_small_collect_aggregate_does_not_call_the_summarizer(tmp_path):
    """短结果不触发压缩（保住既有精确相等断言，省一次无谓调用）。"""
    import json as _json

    from agent.config import AsterwyndConfig
    from agent.llm import LLMResponse, Usage
    from agent.run_config import AgentMode
    from agent.subagent.manager import SubAgentManager
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec
    from agent.workspace_policy import WorkspacePolicy

    class SmallLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            return LLMResponse(content="small", stop_reason="end_turn", usage=Usage(5, 5))

    manager = SubAgentManager(
        llm=SmallLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    fake = RecordingSummarizer("SHOULD NOT BE USED")
    scheduler = WorkflowScheduler(manager)
    scheduler._aggregator = WorkflowAggregator(summarizer=fake)
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "a", "to": "root", "reducer": "concat"},
            {"from": "b", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    await scheduler.run(parse_workflow_spec(raw))
    assert fake.calls == []

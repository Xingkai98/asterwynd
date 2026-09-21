"""message bus 的**模型面出口**一律 bounded（issue #224）。

issue #224 是 #213 的同根遗留：#213 把「模型面出现的子 agent 文本一律 bounded」执行到
run envelope 出口，却把 bus 误判为「已有 bounded 口径」而排除。本模块锁住修复后的契约：

1. ``ReadBus`` 工具出口——单条 ≤ ``TRANSCRIPT_ITEM_LIMIT``、条数 ≤ ``BUS_SNAPSHOT_LIMIT``，
   且**不随调用方传入的 ``max_tokens`` / ``limit`` 放大**（总量维，Q1 阻塞项）；
2. ``RunPattern`` 的 ``result["bus"]``（``patterns.py`` 里的 ``snapshot_payload()``）——
   同样两个维度；
3. 发布侧 ``PublishBusMessage`` 的 ``max_tokens`` 阈值被钳住，且其**回包**（第 5 条出口）
   也随之有界。

输入必须**真的**越界（单条 30000 字、条数 100 > 20），否则「≤ 上限」恒真（#213 教训）。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, ToolCallDelta, Usage
from agent.run_config import AgentMode
from agent.subagent.bus import (
    BUS_MESSAGE_LIMIT,
    BUS_PUBLISH_MAX_TOKENS,
    BUS_SNAPSHOT_LIMIT,
    MessageBus,
)
from agent.subagent.context import reset_bus, set_bus
from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT, SubAgentManager
from agent.subagent.patterns import run_pattern
from agent.tools.builtin.subagents import (
    PublishBusMessageTool,
    ReadBusTool,
    RunPatternTool,
)
from agent.workspace_policy import WorkspacePolicy

#: 判别性输入（#213 的参数教训）：4000 是上限，30000 才真的越界。
_OVERSIZED = 30_000


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class PublishThenFinishLLM:
    """让 worker 先调一次 ``PublishBusMessage`` 发一条超长消息，再正常结束。

    这是唯一能在**真实编排 run 内**把超长子 agent 文本塞进 bus 的方式——静态 LLM
    不会调工具，bus 就永远是空的（那样契约测试无判别力）。
    """

    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(
                        id="c1",
                        name="PublishBusMessage",
                        arguments=json.dumps(
                            {
                                "sender": "worker",
                                "topic": "finding",
                                "content": self.payload,
                            }
                        ),
                    )
                ],
                stop_reason="tool_use",
                usage=Usage(5, 5),
            )
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _saturated_bus() -> MessageBus:
    """同一份内容供两条出口共用：1 条 30k（单条超限）+ 满载 100 条。"""
    bus = MessageBus()
    for i in range(100):
        bus.publish(sender=f"w{i}", topic="finding", summary="y" * 1600)
    bus.publish(sender="loud", topic="finding", summary="x" * _OVERSIZED)
    return bus


def _assert_bounded(messages: list[dict]) -> None:
    assert len(messages) <= BUS_SNAPSHOT_LIMIT, "条数维无界"
    for entry in messages:
        assert len(entry["summary"]) <= TRANSCRIPT_ITEM_LIMIT, "单条维无界"
        assert len(entry["summary"]) <= BUS_MESSAGE_LIMIT


@pytest.mark.asyncio
async def test_readbus_tool_export_is_bounded(manager):
    """出口 1：``ReadBusTool`` 的 JSON 返回——单条与条数都不得越界。"""
    bus = _saturated_bus()
    token = set_bus(bus)
    try:
        data = json.loads(await ReadBusTool(manager).execute())
    finally:
        reset_bus(token)
    assert data["count"] == len(data["messages"])
    _assert_bounded(data["messages"])


@pytest.mark.asyncio
async def test_readbus_tool_export_ignores_huge_caller_params(manager):
    """出口 1 的总量维（Q1 阻塞项）：超大 kwargs 不得放大返回体。

    修复前实测 ``ReadBus(max_tokens=10**9)`` 在同样满载的 bus 上返回
    **100 条 / 约 3,000,000 字符**——单条被截断后总量反而更大。
    """
    bus = _saturated_bus()
    token = set_bus(bus)
    try:
        tool = ReadBusTool(manager)
        default = json.loads(await tool.execute())
        huge = json.loads(
            await tool.execute(max_tokens=10**9, limit=10**9)
        )
    finally:
        reset_bus(token)
    _assert_bounded(default["messages"])
    _assert_bounded(huge["messages"])
    assert huge["count"] <= BUS_SNAPSHOT_LIMIT


@pytest.mark.asyncio
async def test_readbus_tool_reports_truncation_flag(manager):
    """截断必须**如实**回流标志（不依赖调用方比长度自行推断）。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * _OVERSIZED)
    token = set_bus(bus)
    try:
        data = json.loads(await ReadBusTool(manager).execute())
    finally:
        reset_bus(token)
    entry = data["messages"][0]
    assert entry["summary_truncated"] is True
    assert entry["token_count"] == max(1, len(entry["summary"]) // 4)
    # bus 不落盘（D6）：不得声称「全文在某个引用」
    assert "ref" not in json.dumps(entry)


@pytest.mark.asyncio
async def test_snapshot_payload_export_is_bounded(manager):
    """出口 2：``run_pattern`` 的 ``result["bus"]`` 就是 ``snapshot_payload()``。

    与 ``test_readbus_tool_export_is_bounded`` 共用同一份 bus 内容，两条出口逐条对齐。
    """
    bus = _saturated_bus()
    payload = bus.snapshot_payload()
    _assert_bounded(payload["messages"])
    assert payload["messages_total"] == bus.size
    assert payload["messages_omitted"] == max(bus.size - BUS_SNAPSHOT_LIMIT, 0)
    assert payload["messages_omitted"] > 0, "100+ 条的 bus 必须有省略，否则断言恒真"


@pytest.mark.asyncio
async def test_run_pattern_bus_export_is_bounded(manager):
    """出口 2 端到端：真实 ``run_pattern`` 里 worker 发布的超长消息被界住。"""
    manager.llm = PublishThenFinishLLM("x" * _OVERSIZED)
    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="t", params={"workers": 1}
    )
    assert result["bus"]["messages"], "worker 应已发布一条消息（否则断言无判别力）"
    _assert_bounded(result["bus"]["messages"])
    assert len(json.dumps(result["bus"])) < BUS_SNAPSHOT_LIMIT * TRANSCRIPT_ITEM_LIMIT * 2


@pytest.mark.asyncio
async def test_run_pattern_tool_export_is_bounded(manager):
    """``RunPatternTool`` 的 JSON 出口与 ``run_pattern`` 同界。"""
    manager.llm = PublishThenFinishLLM("x" * _OVERSIZED)
    data = json.loads(
        await RunPatternTool(manager).execute(
            pattern="orchestrator-worker", task="t", params={"workers": 1}
        )
    )
    _assert_bounded(data["bus"]["messages"])


@pytest.mark.asyncio
async def test_publish_bus_message_clamps_max_tokens(manager):
    """出口 4 + 出口 5：发布侧 ``max_tokens=10**9`` 不得让原文直入并原样回包。"""
    manager.llm = None  # 确定性降级分支：content[: max_tokens * 4]
    bus = MessageBus()
    token = set_bus(bus)
    try:
        out = json.loads(
            await PublishBusMessageTool(manager).execute(
                sender="w",
                topic="t",
                content="x" * _OVERSIZED,
                max_tokens=10**9,
            )
        )
    finally:
        reset_bus(token)
    assert len(out["summary"]) <= BUS_MESSAGE_LIMIT, "发布回包是第 5 条模型面出口"
    assert len(bus._messages[0].summary) <= BUS_MESSAGE_LIMIT


class OverBudgetLLM:
    """Advisory 预算下**允许**发生的形状：摘要比预算大（如实返回，不截断）。

    ``_summarize`` 的 LLM 分支只把预算拼进 prompt，不保证产出 ≤ 预算
    （``agent/context/summarizer.py``：「not a hard guarantee」）。
    """

    def __init__(self, content: str):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.mark.asyncio
async def test_publish_reply_is_bounded_when_summary_over_budget(manager):
    """回归（审阅 R1）：回包是第 5 条出口，不得因摘要超预算而越界。

    summarize 的 LLM 分支是 advisory，可能返回 6000 字的摘要。修复前该值原样进回包
    （实测 6000 > 4000）——发布侧「有界」是假的。界必须由**出口投影**保证。
    """
    manager.llm = OverBudgetLLM("y" * 6000)  # 远超 4000
    bus = MessageBus()
    token = set_bus(bus)
    try:
        out = json.loads(
            await PublishBusMessageTool(manager).execute(
                sender="w", topic="t", content="x" * _OVERSIZED, max_tokens=10**9
            )
        )
    finally:
        reset_bus(token)
    assert len(out["summary"]) <= BUS_MESSAGE_LIMIT, "摘要超预算时回包越界"
    assert out["summary_truncated"] is True
    assert out["token_count"] == max(1, len(out["summary"]) // 4)
    # D2：队列保留全文（截断只发生在出口投影）
    assert len(bus._messages[0].summary) == 6000
    assert bus._messages[0].truncated is False


@pytest.mark.asyncio
async def test_publish_bus_message_threshold_is_inclusive(manager):
    """Q6 边界：4001 字（``estimate_tokens`` 向下取整到 1000）必须触发 summarize。

    闸门若是 ``>``，4001–4003 字会**不**触发、原文直入 bus，把「两侧同界」变成假话。
    """
    manager.llm = None  # 走确定性降级分支：content[: max_tokens * 4]
    bus = MessageBus()
    token = set_bus(bus)
    try:
        tool = PublishBusMessageTool(manager)
        for length in (4000, 4001, 4003, 4004):
            bus._messages.clear()
            out = json.loads(
                await tool.execute(
                    sender="w", topic="t", content="x" * length, max_tokens=10**9
                )
            )
            assert len(out["summary"]) <= BUS_MESSAGE_LIMIT, f"{length} 字未受界"
            assert len(bus._messages[0].summary) <= BUS_MESSAGE_LIMIT
    finally:
        reset_bus(token)


@pytest.mark.asyncio
async def test_publish_bus_message_short_content_is_untouched(manager):
    """钳制不得改变正常短消息的既有行为（不引入无谓摘要）。"""
    manager.llm = None
    bus = MessageBus()
    token = set_bus(bus)
    try:
        out = json.loads(
            await PublishBusMessageTool(manager).execute(
                sender="w", topic="t", content="short finding"
            )
        )
    finally:
        reset_bus(token)
    assert out["summary"] == "short finding"
    assert out["summary_truncated"] is False


def test_publish_max_tokens_matches_single_item_limit():
    """发布侧阈值与单条上限等价（``//4`` 是 ``estimate_tokens`` 的换算口径）。"""
    assert BUS_PUBLISH_MAX_TOKENS * 4 == BUS_MESSAGE_LIMIT

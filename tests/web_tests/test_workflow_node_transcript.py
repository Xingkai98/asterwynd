"""节点 transcript 只读路由（change ``enhance-workflow-graph-ux``，M3.3–M3.6）。

三态 union（对应「界面效果 §0」的节点↔subagent 三类）：

- ``single``     — subagent / aggregate(llm) / 自动插层聚合（1 个对应 subagent）
- ``candidates`` — foreach 容器（N 个展开项）
- ``none``       — route / aggregate(collect) / 从未派发的节点（不产生 run）

口径（grill 决策 7/8/9）逐条落测：
- 候选集**索引源是 ``item_states``**（index 空间），``subagent_ids`` 只做真实性校验；
- ``reason`` **全文**出口（G17：scheduler 侧 reason 从不出现在 transcript 里）；
- session 校验是**内存口径**（进程重启后同名 session 一律 404，与
  ``/api/sessions/{id}/timeline`` 同口径）；
- 只读：不调 LLM、不写盘、不改执行状态。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy
from web.session import (
    FAILURE_EVIDENCE_STATES,
    TRANSCRIPT_CONTENT_LIMIT,
    _FAILURE_EVIDENCE_MESSAGES,
    _foreach_candidates,
    build_node_transcript_payload,
)


class _LLM:
    def __init__(self, content="worker result"):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class _BoomLLM(_LLM):
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise RuntimeError("model exploded: " + "x" * 2000)


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=_LLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _scheduler(manager, raw: dict) -> WorkflowScheduler:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(raw)
    return scheduler


def _single_spec() -> dict:
    return {
        "goal": "chain",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "c", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "a", "to": "c"}],
        "terminal": ["c"],
    }


def _foreach_spec(count: int = 3) -> dict:
    return {
        "goal": "fan",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "item {item}",
             "items": [f"item-{i}" for i in range(count)]},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }


def _route_spec() -> dict:
    return {
        "goal": "route",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {"id": "gate", "kind": "route",
             "cases": [{"when": "APPROVED", "to": "yes"}], "default": "no"},
            {"id": "yes", "kind": "subagent", "task": "yes branch"},
            {"id": "no", "kind": "subagent", "task": "no branch"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "yes"},
            {"from": "gate", "to": "no"},
        ],
        "terminal": ["yes", "no"],
    }


# --- single 形态 ------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_node_returns_its_own_transcript(manager):
    """spec Scenario「读取单 subagent 节点的 transcript」。"""
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["kind"] == "single"
    assert payload["node_id"] == "a"
    assert payload["subagent_id"] == scheduler._states["a"].subagent_id
    assert isinstance(payload["messages"], list)
    assert payload["truncated"] is False
    assert payload["included_tool_results"] is False


@pytest.mark.asyncio
async def test_single_transcript_is_bounded_with_per_message_clip(manager):
    """bounded 是硬要求：条数上限 + **单条内容截断**（``inspect_transcript`` 不做后者的）。"""
    manager.llm = _LLM(content="y" * 5000)
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a", limit=2)
    assert len(payload["messages"]) <= 2
    for message in payload["messages"]:
        assert len(message["content"]) <= payload["content_limit"]
    assert payload["limit"] == 2


@pytest.mark.asyncio
async def test_single_node_reports_reason_in_full(manager):
    """G17：scheduler 侧 reason 从不出现在 transcript 里——必须由本路由单独给全文。"""
    manager.llm = _BoomLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["reason_full"], "失败节点必须给得出 reason 全文"
    assert len(payload["reason_full"]) > 400, (
        "快照里的 reason 被截断到 400，这里必须是**全文**（G17）"
    )
    assert payload["reason_length"] == len(payload["reason_full"])
    assert payload["reason_truncated"] is False


@pytest.mark.asyncio
async def test_reason_truncated_flag_is_a_flag_not_a_length_comparison(manager):
    """审阅员 B：恰好等于上限的 reason 不能被「比长度」误判成已截断。"""
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    state = scheduler._states["a"]
    state.reason = "z" * 400

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["reason_length"] == 400
    assert payload["reason_truncated"] is False


# --- none 形态 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_node_returns_none_with_typed_info(manager):
    """route 不产生 run：``none`` + 该类型**自有信息**（命中标签 + 选中出口），
    而不是一句「无对话」了事（D4 的边界口径）。"""
    manager.llm = _LLM(content="APPROVED: go")
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "gate")
    assert payload["kind"] == "none"
    assert payload["node_kind"] == "route"
    assert payload["targets"], "route 必须给命中出口"
    assert payload["verdict"] == "APPROVED"
    assert "raw" in payload


@pytest.mark.asyncio
async def test_collect_aggregate_returns_none_with_summary(manager):
    """collect 聚合不产生 run：给**合并产出**，不是「无对话」。"""
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "c")
    assert payload["kind"] == "none"
    assert payload["node_kind"] == "aggregate"
    assert payload["summary"], "collect 节点要给合并产出"


@pytest.mark.asyncio
async def test_never_dispatched_node_returns_none(manager):
    """未派发的节点（blocked/pending）优雅降级：说明「未执行」，不编造 transcript。"""
    scheduler = _scheduler(manager, _route_spec())
    # 不 run：全部节点停在 pending。
    payload = build_node_transcript_payload(manager, scheduler, "yes")
    assert payload["kind"] == "none"
    assert payload["reason_full"] or payload["message"]


@pytest.mark.asyncio
async def test_unknown_node_id_returns_none(manager):
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    payload = build_node_transcript_payload(manager, scheduler, "nope")
    assert payload["kind"] == "none"
    assert payload["node_id"] == "nope"


# --- candidates 形态（foreach 容器） ----------------------------------------


@pytest.mark.asyncio
async def test_foreach_container_returns_candidates_indexed_by_item_space(manager):
    """spec Scenario「foreach 容器返回候选集」+ G10：每条含 index/task/reason。"""
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "fan")
    assert payload["kind"] == "candidates"
    assert payload["total"] == 3
    assert [c["index"] for c in payload["candidates"]] == [0, 1, 2]
    for candidate in payload["candidates"]:
        assert candidate["task"], "候选必须带渲染后的具体任务（「哪个文件」的答案）"
        assert "reason" in candidate
        assert candidate["subagent_id"]


@pytest.mark.asyncio
async def test_candidates_index_source_survives_tasks_without_envelope(manager):
    """审阅员 B 的反例：``subagent_ids`` 是**稀疏数组**（异常项走 continue 被跳过）。

    用 ``item_states`` 当索引源时，失败/被取消的项**仍在列表里**——而「还有哪几项
    没跑」正是用户最想知道的（12 项里 4 个被取消时点开只有 8 行 = 谎报）。
    """
    scheduler = _scheduler(manager, _foreach_spec(4))
    state = scheduler._states["fan"]
    state.items = 4
    state.item_states = ["completed", "failed", "cancelled", "completed"]
    state.item_runs = [None] * 4
    # 故意让 subagent_ids 只有 3 条（模拟异常项被 continue 跳过）。
    state.subagent_ids = ["s0", "s1", "s3"]

    payload = build_node_transcript_payload(manager, scheduler, "fan")
    assert payload["kind"] == "candidates"
    assert payload["total"] == 4, "稀疏的 subagent_ids 不得让候选集缩水"
    assert len(payload["candidates"]) == 4
    assert payload["candidates"][2]["index"] == 2
    assert payload["candidates"][2]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_candidates_are_bounded_and_paginated(manager):
    """候选集必须 bounded：默认 limit 50、硬上限 200，带 total/has_more/offset。"""
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "fan",
                                            limit=2, offset=0)
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert len(payload["candidates"]) == 2
    assert payload["has_more"] is True

    second = build_node_transcript_payload(manager, scheduler, "fan", limit=2, offset=2)
    assert len(second["candidates"]) == 1
    assert second["has_more"] is False

    huge = build_node_transcript_payload(manager, scheduler, "fan", limit=10_000)
    assert huge["limit"] <= 200, "候选集硬上限 200"


@pytest.mark.asyncio
async def test_single_item_foreach_is_single_not_candidates(manager):
    """审阅员 B：N=1 的 foreach 归 ``single``，不设特例分支。"""
    scheduler = _scheduler(manager, _foreach_spec(1))
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "fan")
    assert payload["kind"] == "single"


# --- 只读与信任级 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_transcript_read_does_not_change_execution_state(manager):
    """只读：不调 LLM、不改执行状态（与 Chat 视图同信任级，不新增写路径）。"""
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    manager.llm.calls = 0
    # 只比**执行状态**：快照的 ``timestamp``/``budget.wall_time_s`` 本来就随时间变，
    # 把它们比进去等于测试时钟。
    before = json.dumps(scheduler.workflow_graph_snapshot()["nodes"], sort_keys=True)

    build_node_transcript_payload(manager, scheduler, "fan")
    build_node_transcript_payload(manager, scheduler, "root")

    assert manager.llm.calls == 0, "transcript 路由不得触发任何 LLM 调用"
    after = json.dumps(scheduler.workflow_graph_snapshot()["nodes"], sort_keys=True)
    assert before == after, "transcript 路由不得改变任何执行状态"


@pytest.mark.asyncio
async def test_payload_is_json_serialisable(manager):
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    for node_id in ("fan", "root"):
        encoded = json.dumps(build_node_transcript_payload(manager, scheduler, node_id))
        assert node_id in encoded


# --- 候选项下钻：取**某一项**自己的 transcript ------------------------------


@pytest.mark.asyncio
async def test_item_drilldown_returns_that_items_own_transcript(manager):
    """spec Scenario：点候选项后 SHALL 能按该项的 subagent_id 取到**它自己**的
    transcript，SHALL NOT 混入同容器其它项的 messages。

    没有这条取数路径，「点进单项」就是空操作——候选列表点了没反应（审阅发现的
    功能缺口）。
    """
    manager.llm = _LLM(content="item-specific output")
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)

    container = build_node_transcript_payload(manager, scheduler, "fan")
    assert container["kind"] == "candidates"
    target = container["candidates"][1]
    assert target["subagent_id"], "前置：候选项必须带 subagent_id"

    item = build_node_transcript_payload(
        manager, scheduler, "fan",
        subagent_id=target["subagent_id"],
        run_id=target["run_id"],
    )
    assert item["kind"] == "single", f"应下钻为单项，实际 {item['kind']!r}"
    assert item["subagent_id"] == target["subagent_id"]
    assert item["index"] == 1
    assert item["messages"], "单项 transcript 必须真的取到 messages"
    # 不能把容器形态（候选列表）当结果返回——那正是「点了没反应」的成因。
    assert "candidates" not in item


@pytest.mark.asyncio
async def test_item_drilldown_does_not_mix_other_items(manager):
    """每项的 **messages** 是各自 session 的，不得串台。

    断言必须落在 **messages 内容**上，不能只看回显的 ``subagent_id``：一个「永远
    去取第 0 项、但如实回显调用方给的 id」的实现会骗过只看回显的断言（审阅员在
    变异验证里点出了这一点）。所以让每项的产出**带自己的身份标记**，再逐项核对
    取回来的 messages 里只有属于它自己的那个标记。
    """

    class _ItemTaggedLLM(_LLM):
        """每次调用返回**本 session 独有**的标记：同一 session 的多次调用标记相同。

        标记按「这是本 session 第几次调用」生成——不同 session 各自从 1 开始，
        所以三个 session 的标记集互不相同，足以识破串台。
        """

        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            return LLMResponse(content=f"MSG-FROM-{id(self):x}", stop_reason="end_turn",
                               usage=Usage(5, 5))

    # 每个展开项建自己的 session → 各有一个 LLM 实例？不——manager 共用一个 llm。
    # 所以改用「按 task 文本打标」：render_item_task 会把 item 值渲染进 task，
    # 而 task 是**本项独有**的。
    class _TaskEchoLLM(_LLM):
        async def chat(self, messages, tools=None, model="gpt-4"):
            blob = " ".join(str(getattr(m, "content", "")) for m in messages)
            marker = next((f"item-{i}" for i in range(3) if f"item-{i}" in blob), "?")
            return LLMResponse(content=f"OWNED-BY-{marker}", stop_reason="end_turn",
                               usage=Usage(5, 5))

    manager.llm = _TaskEchoLLM()
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)

    container = build_node_transcript_payload(manager, scheduler, "fan")
    candidates = container["candidates"]
    assert len({c["subagent_id"] for c in candidates}) == 3, "三项各有独立 subagent"
    # 每项的 task 是自己的那个 item（这是 render_item_task 的产物）。
    owned = {}
    for candidate in candidates:
        marker = next(f"item-{i}" for i in range(3) if f"item-{i}" in candidate["task"])
        owned[candidate["index"]] = marker

    for candidate in candidates:
        item = build_node_transcript_payload(
            manager, scheduler, "fan",
            subagent_id=candidate["subagent_id"], run_id=candidate["run_id"])
        text = " ".join(m["content"] for m in item["messages"])
        expected = owned[candidate["index"]]
        assert f"OWNED-BY-{expected}" in text, (
            f"第 {candidate['index']} 项取到的不是自己的 messages：{text!r}"
        )
        # 而且**不能**混入别项的标记。
        for other_index, other in owned.items():
            if other_index == candidate["index"]:
                continue
            assert f"OWNED-BY-{other}" not in text, (
                f"第 {candidate['index']} 项混入了第 {other_index} 项的内容：{text!r}"
            )


@pytest.mark.asyncio
async def test_item_drilldown_of_unknown_subagent_degrades(manager):
    """未知 subagent_id（记录已淘汰）优雅降级，不 500。"""
    scheduler = _scheduler(manager, _foreach_spec(2))
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(
        manager, scheduler, "fan", subagent_id="never-existed")
    assert payload["kind"] == "none"
    assert payload["subagent_id"] == "never-existed"


@pytest.mark.asyncio
async def test_item_drilldown_is_bounded_and_read_only(manager):
    manager.llm = _LLM(content="z" * 9000)
    scheduler = _scheduler(manager, _foreach_spec(2))
    await scheduler.run(scheduler.spec)

    container = build_node_transcript_payload(manager, scheduler, "fan")
    target = container["candidates"][0]
    manager.llm.calls = 0
    item = build_node_transcript_payload(
        manager, scheduler, "fan",
        subagent_id=target["subagent_id"], run_id=target["run_id"],
        limit=1, content_limit=100,
    )
    assert len(item["messages"]) <= 1
    for message in item["messages"]:
        assert len(message["content"]) <= 100
    assert manager.llm.calls == 0


@pytest.mark.asyncio
async def test_unknown_subagent_degrades_instead_of_raising(manager):
    """``inspect_transcript`` 对未知 subagent 抛 ``KeyError``——路由要转结构化响应。

    这覆盖「候选列表里的 subagent 已被淘汰」这类真实情形（前端点了一项，
    但 manager 侧记录没了），路由层不能 500。
    """
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    # 模拟 manager 侧记录消失（进程重启 / 会话被淘汰）。
    manager._sessions.clear()

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["kind"] in ("single", "none")
    assert payload.get("messages", []) == []


# --- 工具调用消息（本轮修复：assistant 的 tool_calls 曾被投影丢弃）-------------


class _ToolCallingLLM:
    """第一轮只发起工具调用（**content 为空**），第二轮才给文字结论。

    这是 AgentLoop 的真实形态：模型大多数轮次不输出文字、只发工具调用
    （``agent/loop.py:750`` 构造 ``Message(role="assistant", content="", tool_calls=[...])``）。
    原桩 LLM（``_LLM``）永远返回带文字的 ``end_turn``，所以从未产生过这种消息，
    投影丢字段的问题在测试里永远踩不到。
    """

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        from agent.llm import ToolCallDelta

        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(id="c1", name="Read",
                                  arguments=json.dumps({"path": "AGENTS.md"})),
                    ToolCallDelta(id="c2", name="Grep",
                                  arguments=json.dumps({"pattern": "workflow", "path": "."})),
                ],
                stop_reason="tool_calls",
                usage=Usage(5, 5),
            )
        return LLMResponse(content="结论：都读完了。", stop_reason="end_turn",
                           usage=Usage(5, 5))


@pytest.mark.asyncio
async def test_transcript_keeps_assistant_tool_calls(manager):
    """带 tool_calls 的 assistant 消息 SHALL NOT 变成空行。

    真实场景（用户实测发现）：一个只发起工具调用、不输出文字的 assistant 轮次，
    投影后 ``content`` 为空且 ``tool_calls`` 被丢——对话 tab 里显示成一串
    「ASSISTANT」空行，用户以为「对话不全」。
    """
    manager.llm = _ToolCallingLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["kind"] == "single"

    tool_call_messages = [m for m in payload["messages"] if m.get("tool_calls")]
    assert tool_call_messages, (
        "带 tool_calls 的 assistant 消息全部丢失——对话会显示成空行："
        f"{[m['role'] for m in payload['messages']]}"
    )
    calls = tool_call_messages[0]["tool_calls"]
    assert [c["name"] for c in calls] == ["Read", "Grep"]
    # arguments 是 JSON 字符串（与主 chat 的 ``tool_call`` 事件口径一致）。
    assert json.loads(calls[0]["arguments"]) == {"path": "AGENTS.md"}


class _HugeArgsLLM(_ToolCallingLLM):
    """工具调用的 arguments 极大——模拟「写一个大文件」这类调用。"""

    async def chat(self, messages, tools=None, model="gpt-4"):
        from agent.llm import ToolCallDelta

        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(id="c1", name="Write",
                                  arguments=json.dumps({"path": "big.py", "content": "x" * 5000})),
                ],
                stop_reason="tool_calls",
                usage=Usage(5, 5),
            )
        return LLMResponse(content="写完了。", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.mark.asyncio
async def test_tool_call_arguments_bounded_even_without_route_limit(manager):
    """**生产者侧**的兜底截断：不经 web 路由的调用方（模型面 ``InspectSubagentTranscript``
    工具）也拿不到无界 ``arguments``。

    审阅发现（issue #212 修复 R1）：``InspectSubagentTranscript`` 的 ``limit`` 只有
    ``minimum`` 没有 ``maximum``，且直接 ``json.dumps`` 结果进模型上下文——不给
    ``manager`` 加兜底的话，3 轮 20KB 的 ``Write`` 调用会输出约 60K 字符（~15K tokens），
    比修复前放大两个数量级。
    """
    from agent.subagent.manager import TOOL_CALL_ARGUMENT_LIMIT

    manager.llm = _HugeArgsLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    subagent_id = scheduler._states["a"].subagent_id
    raw = manager.inspect_transcript(
        subagent_id=subagent_id, scope="recent_messages", limit=50)
    calls = [c for m in raw["messages"] for c in (m.get("tool_calls") or [])]
    assert calls, "带 tool_calls 的消息丢了"
    assert len(calls[0]["arguments"]) <= TOOL_CALL_ARGUMENT_LIMIT
    assert calls[0]["arguments_truncated"] is True


@pytest.mark.asyncio
async def test_transcript_tool_call_arguments_are_bounded(manager):
    """arguments 必须走单条内容截断——否则一个写大文件的工具调用就能撑爆响应。

    ``content_limit`` 是**路由层**的单条截断口径（``_bounded_messages``）；
    工具调用的 ``arguments`` 与消息 ``content`` 同属「单条内容」，
    不能绕开它——否则 bounded 是空话。
    """
    manager.llm = _HugeArgsLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a", content_limit=40)
    calls = [c for m in payload["messages"] for c in (m.get("tool_calls") or [])]
    assert calls, "带 tool_calls 的消息丢了"
    assert len(calls[0]["arguments"]) <= 40
    assert calls[0]["arguments_truncated"] is True


@pytest.mark.asyncio
async def test_transcript_tool_results_still_excluded_by_default(manager):
    """默认仍排除 ``role="tool"`` 的结果（spec：「SHALL 默认排除工具结果」）。

    补 ``tool_calls`` 是**增量**（assistant 自己的调用记录），不改变这个默认。
    """
    manager.llm = _ToolCallingLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "a")
    assert payload["included_tool_results"] is False
    assert all(m["role"] != "tool" for m in payload["messages"])
    # 但工具调用的**存在**必须可见。
    assert any(m.get("tool_calls") for m in payload["messages"])


@pytest.mark.asyncio
async def test_inspect_tool_clamps_limit_and_arguments(manager):
    """模型面工具的 bounded：``limit`` 夹到与 web 路由同值 + ``arguments`` 有上限。

    审阅 Issue #1（中）：``InspectSubagentTranscript`` 的 ``limit`` 无上限、输出
    直接进模型上下文——3 轮 20KB 的 ``Write`` 调用会放大到约 60K 字符。
    """
    from agent.tools.builtin.subagents import InspectSubagentTranscriptTool
    from agent.subagent.manager import TOOL_CALL_ARGUMENT_LIMIT, TRANSCRIPT_ITEM_LIMIT
    from web.session import TRANSCRIPT_MAX_LIMIT

    # 契约数字必须同值（一处改了另一处忘改 = 路径口径漂移）：
    # 条数两处 + 单条内容**三处**（新名 / 旧别名 / web 常量）。
    # 审阅 R1 Issue 7 指出此前只断言了两处（别名传递等价），故显式把新名也钉上——
    # 否则「alias 被拆开」或「新名与 web 常量漂移」都不会变红。
    from web.session import TRANSCRIPT_CONTENT_LIMIT
    assert InspectSubagentTranscriptTool.MAX_TRANSCRIPT_LIMIT == TRANSCRIPT_MAX_LIMIT
    assert TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_ITEM_LIMIT, (
        "旧别名必须仍指向新名——否则是半改半不改"
    )
    assert TRANSCRIPT_ITEM_LIMIT == TRANSCRIPT_CONTENT_LIMIT, (
        "生产者的单条上限与路由的单条上限是两个数——不锁死必然漂移"
    )

    manager.llm = _HugeArgsLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id

    # **必须真的超过上限**：跑出来的消息只有个位数时，「返回 ≤200 条」的断言
    # 恒真——变异验证证明它抓不到「去掉夹取」（那个变异会返回 301 条）。
    session = manager._sessions[subagent_id]
    from agent.message import Message
    for index in range(TRANSCRIPT_MAX_LIMIT + 100):
        session.messages.append(Message(role="user", content=f"pad-{index}"))

    tool = InspectSubagentTranscriptTool(manager)
    out = await tool.execute(subagent_id=subagent_id, scope="recent_messages", limit=100000)
    payload = json.loads(out)
    # 夹到上限：不可能因为要 10 万条而拿到 10 万条。
    assert len(payload["messages"]) == TRANSCRIPT_MAX_LIMIT, (
        f"limit 未被夹取：拿到 {len(payload['messages'])} 条"
    )
    # 单条工具调用参数有上限（生产者的兜底截断）。
    for message in payload["messages"]:
        for call in message.get("tool_calls") or []:
            assert len(call["arguments"]) <= TOOL_CALL_ARGUMENT_LIMIT


@pytest.mark.asyncio
async def test_truncation_flag_composes_across_producer_and_route(manager):
    """两层截断标志必须**取或**，不能只看本层长度。

    生产者（``manager``）按 ``TOOL_CALL_ARGUMENT_LIMIT`` 先截到 4000；路由层若拿到
    更宽的 ``content_limit``（``build_node_transcript_payload`` 的公开参数），只看
    本层长度会得出「没截断」——而实际上上游已经截过，前端据此会**谎报完整**。
    """
    from agent.subagent.manager import TOOL_CALL_ARGUMENT_LIMIT

    manager.llm = _HugeArgsLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    # 路由预算**大于**生产者上限：上游截过，本层长度检查不会触发。
    payload = build_node_transcript_payload(
        manager, scheduler, "a", content_limit=TOOL_CALL_ARGUMENT_LIMIT * 2)
    calls = [c for m in payload["messages"] for c in (m.get("tool_calls") or [])]
    assert calls, "带 tool_calls 的消息丢了"
    assert len(calls[0]["arguments"]) <= TOOL_CALL_ARGUMENT_LIMIT
    assert calls[0]["arguments_truncated"] is True, (
        "上游已截断但本层预算更宽——只看本层长度会谎报「未截断」"
    )


# ─── issue #213：模型面出现的子 agent 文本一律 bounded ───────────────────────

#: 真·超长文本。**必须远超上限**——既有测试写过这条教训（见 test_inspect_tool_clamps
#: 的注释）：输入只有几千字时「返回 ≤4000」恒真，抓不到任何变异。
HUGE = "超长内容" * 7500  # 30000 字符


class _HugeOutputLLM:
    """子 agent 产出 30000 字最终回复——模拟「跑了一大段分析然后总结」这类 run。"""

    def __init__(self, content: str = HUGE):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        if self.calls == 1:
            from agent.llm import ToolCallDelta
            return LLMResponse(
                content="",
                tool_calls=[ToolCallDelta(id="c1", name="Read",
                                          arguments=json.dumps({"path": "x.py"}))],
                stop_reason="tool_calls",
                usage=Usage(5, 5),
            )
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.mark.asyncio
async def test_run_summary_is_bounded_at_fixed_limit(manager):
    """出口 2：``GetSubagentRun`` 的 ``summary`` 不得超过**固定**单条上限。

    issue #213：``to_result_dict()["summary"]`` 是 ``run.summary`` 全文（30000 字
    原样进父 agent 上下文）。这里锁死「模型面看到的是 bounded 版」。
    """
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id
    run_id = scheduler._states["a"].run_id

    payload = await manager.get_subagent_run(subagent_id=subagent_id, run_id=run_id)
    assert len(payload["summary"]) <= TRANSCRIPT_ITEM_LIMIT, (
        f"GetSubagentRun 的 summary 无界：{len(payload['summary'])} 字符"
    )
    # 全文仍可取：记录层没被截，ref 指向全文。
    run = manager.find_run(subagent_id, run_id)
    assert run.summary == HUGE, "记录层必须保留全文（下游聚合依赖它）"
    assert run.result_ref is not None
    store = manager.workflow_store(scheduler.workflow_id)
    assert store.load(run.result_ref) == HUGE


@pytest.mark.asyncio
async def test_run_summary_limit_does_not_scale_with_max_tokens(manager):
    """出口 2 的界**不可被被检视对象放大**：``max_tokens`` 拉到很大，上限不变。

    grill 实测：初版方案复用 ``_bounded_summary(text, max_tokens)``（预算
    ``max(2000, max_tokens*4)``），而 ``max_tokens`` 由发起调用的模型自己写、无上界
    校验——``max_tokens=500000`` 时 30000 字**完全不截**，issue #213 静默不修。
    """
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id
    run_id = scheduler._states["a"].run_id

    # 把 run 预算调到足以「容纳全文」的量级（模拟模型自设大 max_tokens）。
    run = manager.find_run(subagent_id, run_id)
    run.max_tokens = 500000

    payload = await manager.get_subagent_run(subagent_id=subagent_id, run_id=run_id)
    assert len(payload["summary"]) <= TRANSCRIPT_ITEM_LIMIT, (
        f"上限随 max_tokens 放大到 {len(payload['summary'])} 字符 —— "
        "界必须独立于 run 预算，否则子 agent 能自己决定父 agent 收到多少"
    )
    # **整包断言**（审阅 R1 的 blocker）：只断言某一个键会漏掉同一 payload 里的别的
    # 键——``bounded_summary`` 当初就是这么漏的（它也随 max_tokens 放大，max_tokens
    # 够大时就是全文）。这里对**序列化后的整个返回体**断言，任何键再犯都会变红。
    assert HUGE not in json.dumps(payload, ensure_ascii=False), (
        "工具返回体里仍含子 agent 全文——换了个键继续泄漏"
    )


@pytest.mark.asyncio
async def test_inspect_summary_scope_is_bounded(manager):
    """出口 1 的 summary scope（工具的**默认** scope）：同样有上限 + 标志。"""
    from agent.tools.builtin.subagents import InspectSubagentTranscriptTool
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id

    tool = InspectSubagentTranscriptTool(manager)
    payload = json.loads(await tool.execute(subagent_id=subagent_id, scope="summary"))
    assert len(payload["summary"]) <= TRANSCRIPT_ITEM_LIMIT, (
        f"summary scope 无界：{len(payload['summary'])} 字符"
    )
    assert payload["summary_truncated"] is True, "截断了却不说 = 让模型以为这就是全部"


@pytest.mark.asyncio
async def test_inspect_message_content_is_bounded(manager):
    """出口 1 的 recent_messages scope：单条 ``content`` 有上限 + 标志。"""
    from agent.tools.builtin.subagents import InspectSubagentTranscriptTool
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id

    tool = InspectSubagentTranscriptTool(manager)
    payload = json.loads(await tool.execute(
        subagent_id=subagent_id, scope="recent_messages", limit=50))
    huge = [m for m in payload["messages"] if len(m["content"]) > 100]
    assert huge, f"没找到长消息，构造无效：{[len(m['content']) for m in payload['messages']]}"
    for message in payload["messages"]:
        assert len(message["content"]) <= TRANSCRIPT_ITEM_LIMIT, (
            f"content 无界：{len(message['content'])} 字符"
        )
    assert any(m.get("content_truncated") is True for m in huge), "截断了却不说"


@pytest.mark.asyncio
async def test_inspect_tool_result_message_content_is_bounded(manager):
    """``include_tool_results=True`` 时 tool 角色消息的 content 同口径。

    这是 30000 字最可能的真实来源（一次 Read/Bash 的整份输出），既有测试恰好把
    tool 消息过滤掉了，所以必须单独覆盖。
    """
    from agent.tools.builtin.subagents import InspectSubagentTranscriptTool
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT
    from agent.message import tool_result_message

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    subagent_id = scheduler._states["a"].subagent_id

    manager._sessions[subagent_id].messages.append(
        tool_result_message("c1", HUGE))
    tool = InspectSubagentTranscriptTool(manager)
    payload = json.loads(await tool.execute(
        subagent_id=subagent_id, scope="recent_messages",
        limit=50, include_tool_results=True))
    tools = [m for m in payload["messages"] if m["role"] == "tool"]
    assert tools, "tool 消息没返回"
    for message in tools:
        assert len(message["content"]) <= TRANSCRIPT_ITEM_LIMIT
    assert tools[-1].get("content_truncated") is True


@pytest.mark.asyncio
async def test_route_content_truncated_ors_producer_flag(manager):
    """HTTP 层的 ``content_truncated`` 必须与生产者标志**取或**。

    生产者开始截 ``content`` 后，路由层若只看本层长度，会在「生产者截了、本层预算
    更宽」时报「没截断」——与 #212 在 ``arguments`` 上修过的是同一个 bug 的第二例。
    """
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    manager.llm = _HugeOutputLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(
        manager, scheduler, "a", content_limit=TRANSCRIPT_ITEM_LIMIT * 2)
    long_messages = [m for m in payload["messages"] if len(m["content"]) > 100]
    assert long_messages, "没找到长消息，构造无效"
    assert long_messages[0]["content_truncated"] is True, (
        "上游已截断但本层预算更宽——只看本层长度会谎报「未截断」"
    )


@pytest.mark.asyncio
async def test_truncation_marker_does_not_promise_missing_ref(manager, tmp_path):
    """截断标记不得声称全文在某个**不存在**的引用里。

    无 workflow 身份的 run（普通 ``RunSubagent``）不落盘，``result_ref`` 为 ``None``；
    而 ``_bounded_summary`` 无条件追加「…[truncated; full result in result_ref]」
    ——实测同一条记录里两者自相矛盾，是一句**假话**。
    """
    from agent.subagent.manager import _bounded_summary

    text = "x" * 10000
    rendered = _bounded_summary(text, None, has_ref=False)
    assert "result_ref" not in rendered, (
        "没有落盘引用却声称「full result in result_ref」——这是假话"
    )
    assert "truncated" in rendered, "仍须如实表达已截断"

    # 有 ref 时保留导航信息（不能因噎废食）。
    with_ref = _bounded_summary(text, None, has_ref=True)
    assert "result_ref" in with_ref


@pytest.mark.asyncio
async def test_worker_entry_summary_is_bounded_and_navigable(manager):
    """出口 4：``RunPattern`` 的 worker 条目（经真实 ``run_pattern`` 路径）。

    (a) summary 有上限（N 个 worker × 全文 = 一次调用放大 N 倍）；
    (b) 条目**无条件带 result_ref**——模型的认知是「被裁过就能按 ref 取全文」，
        若条目没带该字段，模型按图索骥会扑空，等于在出口 4 复制本 change 正要消灭的假话。

    经由 ``run_pattern`` 而非直调 ``_worker_entry``：后者会绕过
    ``_legacy_result`` 的拼接路径，中途任何一环改写都测不到（审阅 R1 Issue 6）。
    """
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT
    from agent.subagent.patterns import run_pattern

    manager.llm = _HugeOutputLLM()
    result = await run_pattern(manager, pattern="orchestrator-worker", task="t")
    workers = result.get("workers") or []
    assert workers, f"没拿到 worker 条目：{list(result)}"

    truncated_entries = []
    for entry in workers:
        assert len(entry["summary"]) <= TRANSCRIPT_ITEM_LIMIT, (
            f"worker summary 无界：{len(entry['summary'])} 字符"
        )
        if entry["summary_truncated"]:
            truncated_entries.append(entry)
    # **无条件**断言被裁过的条目确实存在——否则下面的循环可以是空转，
    # 而「去掉 summary_truncated 标志」这种变异就抓不到（审阅 R2 Issue 2）。
    assert truncated_entries, (
        f"构造无效：没有一条 worker summary 被裁（原文 {len(HUGE)} 字，"
        f"上限 {TRANSCRIPT_ITEM_LIMIT}）；条目状态={[e.get('summary_truncated') for e in workers]}"
    )
    for entry in truncated_entries:
        # 被裁过就必须能导航到全文——模型的认知是「被裁就能按 ref 取全文」，
        # 没带该字段就成了空头承诺。
        assert "result_ref" in entry, (
            "条目被截断却没带 result_ref——模型拿不到全文，成了空头承诺"
        )
    assert HUGE not in json.dumps(result, ensure_ascii=False), (
        "RunPattern 返回体里仍含 worker 全文"
    )


@pytest.mark.asyncio
async def test_worker_entry_without_workflow_identity_does_not_lie(manager):
    """无 workflow 身份的 run（全文未落盘）：条目不得声称「全文在 X」。

    与上一条互补——上一条锁「有 ref 时必须给」，这条锁「没有 ref 时不说谎」。
    """
    from agent.subagent.patterns import _worker_entry
    from agent.subagent.manager import SubagentRunRecord

    run = SubagentRunRecord(run_id="r", task="t", status="completed", summary=HUGE)
    entry = _worker_entry("s", run)

    assert entry.get("result_ref") is None, "构造前提：该 run 没有落盘引用"
    assert "result_ref" not in json.dumps(entry, ensure_ascii=False), (
        "没有落盘引用却提 result_ref——模型按图索骥会扑空，是一句假话"
    )


# --- 失败证据投影（change fix-issue-215-node-failure-evidence） ----------------
#
# 数据源是 ``run.trace.steps`` 里**已经存在**的失败信号（``status != "ok"`` 的
# ``tool_result`` + 全部 ``llm_error``）——本 change 只加读取侧投影，不新增采集。
# 状态枚举七值逐个落测；「无数据」与「无失败」不得折叠成同一个取值。


def _tool_result(step: int, name: str, status: str, observation="out",
                 error_type=None) -> dict:
    return {"step": step, "type": "tool_result",
            "data": {"tool_name": name, "status": status, "duration_ms": 1.0,
                     "observation": observation, "error_type": error_type}}


def _llm_error(step: int, error_type: str, message: str = "boom") -> dict:
    return {"step": step, "type": "llm_error",
            "data": {"error_type": error_type, "message": message}}


def _llm_iteration(step: int) -> dict:
    return {"step": step, "type": "llm_iteration", "data": {"iteration": step}}


def _trace(steps: list[dict]) -> dict:
    return {"steps": steps, "schema_version": "1.1"}


async def _completed_node(manager, node_id: str = "a"):
    """跑一个单节点 spec，返回 (scheduler, state, run)。"""
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    state = scheduler._states[node_id]
    run = manager.find_run(state.subagent_id, state.run_id)
    return scheduler, state, run


@pytest.mark.asyncio
async def test_failure_evidence_present_on_completed_run_with_tool_failure(manager):
    """spec Scenario「run 完成但中途有工具失败」：绿节点也要能读出失败证据。

    这是 issue #215 的主场景——run 终态 ``completed``、``reason`` 为空，但 trace 里
    躺着两条失败（工具错误 + LLM 错误）。
    """
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([
        {"step": 1, "type": "tool_call",
         "data": {"tool_name": "Bash", "arguments": {"command": "uv run pytest -q"}}},
        _tool_result(2, "Bash", "error", "3 failed, 12 passed", "tool_error"),
        _llm_iteration(3),
        _llm_error(4, "network_timeout", "upstream timed out"),
    ])

    assert run.status == "completed", "前置：run 是终态 completed（绿节点）"
    assert run.reason is None, "前置：整体 run 没失败，所以 reason 是空的"

    payload = build_node_transcript_payload(manager, scheduler, "a")
    evidence = payload["failure_evidence"]
    assert evidence["state"] == "present"
    assert evidence["total"] == 2
    assert evidence["truncated"] is False
    # message 必须与 state **配对**：这里是回归——present 分支一度漏设 message，
    # 于是带着初始的 unavailable 文案返回，成了「状态说有失败、文案说取不到」。
    assert evidence["message"] == _FAILURE_EVIDENCE_MESSAGES["present"]
    assert evidence["message"] != _FAILURE_EVIDENCE_MESSAGES["unavailable"]

    tool_item, llm_item = evidence["items"]
    assert tool_item["type"] == "tool_result"
    assert tool_item["tool_name"] == "Bash"
    assert tool_item["step"] == 2
    assert tool_item["status"] == "error"
    assert tool_item["error_type"] == "tool_error"
    assert "3 failed" in tool_item["observation"]
    assert tool_item["text_truncated"] is False

    assert llm_item["type"] == "llm_error"
    assert llm_item["error_type"] == "network_timeout"
    assert llm_item["tool_name"] is None
    assert "upstream timed out" in llm_item["message"]


@pytest.mark.asyncio
async def test_llm_error_item_status_is_synthesised(manager):
    """``llm_error`` 的 trace step **没有** ``status`` 键（``trace_recorder.py:226``
    只写 ``error_type``/``message``）——条目仍须带 ``status``，由投影固定为 ``error``。

    变异点：把合成那一行删掉（直接透传 ``data.get("status")``）→ 本条必须变红。
    """
    scheduler, _state, run = await _completed_node(manager)
    raw_step = _llm_error(1, "rate_limited")
    assert "status" not in raw_step["data"], "前置：生产者确实不写 status"
    run.trace = _trace([raw_step])

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["items"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_failure_evidence_clean_is_a_positive_statement(manager):
    """spec Scenario「trace 存在且没有任何失败步骤」：``clean`` 是**正向声明**。

    变异点：把 ``clean`` 当 ``no_trace`` → 本条必须变红（用户在前者可以放心，
    在后者不能——这正是 change 要区分开的东西）。
    """
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([_llm_iteration(1), _tool_result(2, "Read", "ok", "file body")])

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "clean", "走完 trace 且零失败 = 已检查、干净"
    assert evidence["items"] == []
    assert evidence["total"] == 0
    assert evidence["truncated"] is False
    assert "检查" in evidence["message"] or "无失败" in evidence["message"], (
        "clean 必须带「已检查过」的文案，否则用户分不清「没失败」与「没看过」"
    )


@pytest.mark.asyncio
async def test_failure_evidence_running_is_not_no_trace(manager):
    """spec Scenario「run 仍在运行」：``running`` 时 trace 还没写（按设计），
    但**不得**报成 ``no_trace``（两者成因不同，用户的下一步也不同）。
    """
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    state = scheduler._states["a"]
    run = manager.find_run(state.subagent_id, state.run_id)
    run.status = "running"
    run.trace = None

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "running"
    assert evidence["items"] == []


@pytest.mark.asyncio
async def test_failure_evidence_no_trace_when_terminal_without_trace(manager):
    """spec Scenario「run 到终态但从未记录 trace」：``no_trace`` ≠ ``clean``。

    变异点：把 ``no_trace`` 折进 ``clean`` → 本条必须变红。
    """
    scheduler, _state, run = await _completed_node(manager)
    run.trace = None

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "no_trace"
    assert evidence["total"] == 0
    assert "未记录" in evidence["message"] or "没有采集" in evidence["message"]


@pytest.mark.asyncio
async def test_failure_evidence_empty_trace_is_not_no_trace(manager):
    """spec Scenario「trace 存在但该 run 没有执行过任何步骤」：``empty_trace``
    必须与 ``no_trace``（以及 ``clean``）都是不同取值。

    成因是排队取消路径 ``manager.py:1086``（以及 ``:1100`` 的兜底）新建的**空**
    TraceRecorder——它 ``to_dict()`` 出 ``steps == []``，与「压根没 trace」不同。
    """
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([])

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "empty_trace"
    assert evidence["state"] not in ("no_trace", "clean")
    assert "未执行任何步骤" in evidence["message"]


@pytest.mark.asyncio
async def test_failure_evidence_unavailable_when_run_record_is_gone(manager):
    """spec Scenario「解析不到该节点的 run 记录」：``unavailable`` ≠ ``clean``。

    半合成用例：workflow 内的 ``queue_full`` 因准入背压**预期恒为 0 次**
    （``scheduler.py`` 的 ``_dispatch_capacity = max_active + max_queued_runs``），
    所以这里直接构造「run 记录已不在 session.runs 里」的形状，而不是跑一个真实
    workflow 去撞它——真实路径为 0 次是本 change 的既定事实，不是测试缺陷。
    """
    scheduler, state, _run = await _completed_node(manager)
    session = manager._sessions[state.subagent_id]
    assert session.runs, "前置：确实有一条 run 记录"
    session.runs.pop()

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "unavailable"
    assert evidence["items"] == []
    assert "无法解析" in evidence["message"]


@pytest.mark.asyncio
async def test_failure_evidence_not_applicable_for_route_and_collect(manager):
    """spec Scenario「结构上不可能产生 run 的节点」：route / collect 报
    ``not_applicable``，**不得**报 ``unavailable``。

    变异点：把 ``not_applicable`` 当 ``unavailable`` → 本条必须变红。
    """
    manager.llm = _LLM(content="APPROVED: go")
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)

    route_evidence = build_node_transcript_payload(
        manager, scheduler, "gate")["failure_evidence"]
    assert route_evidence["state"] == "not_applicable"
    assert route_evidence["items"] == []

    scheduler2 = _scheduler(manager, _single_spec())
    await scheduler2.run(scheduler2.spec)
    agg_evidence = build_node_transcript_payload(
        manager, scheduler2, "c")["failure_evidence"]
    assert agg_evidence["state"] == "not_applicable", "collect 聚合不产生 run"


@pytest.mark.asyncio
async def test_failure_evidence_unavailable_for_never_dispatched_node(manager):
    """未派发的节点：``unavailable`` + 「尚未派发」文案（与 route/collect 区分开，
    也与「run 记录被弹出」区分开——三者的下一步动作不同）。
    """
    scheduler = _scheduler(manager, _route_spec())
    # 不 run：全部节点停在 pending。

    evidence = build_node_transcript_payload(
        manager, scheduler, "yes")["failure_evidence"]
    assert evidence["state"] == "unavailable"
    assert "派发" in evidence["message"] or "未执行" in evidence["message"]


@pytest.mark.asyncio
async def test_failure_evidence_returns_most_recent_n_in_time_order(manager):
    """bounded：只回**最近** N 条（按 trace 步骤序号），显示顺序为时间正序，
    ``total`` 是**真实**失败总数。

    变异点一：改成取**最早** N 条 → 本条必须变红。
    变异点二：``total`` 改成返回条数 → 本条必须变红。
    """
    from web.session import FAILURE_EVIDENCE_LIMIT

    scheduler, _state, run = await _completed_node(manager)
    steps = [_llm_iteration(1)]
    for index in range(1, 10):  # 9 条失败
        steps.append(_tool_result(index + 1, f"Tool{index}", "error", f"fail-{index}"))
    run.trace = _trace(steps)

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["total"] == 9, "total 必须是真实失败总数，不是返回条数"
    assert evidence["truncated"] is True
    assert len(evidence["items"]) == FAILURE_EVIDENCE_LIMIT

    observed = [item["observation"] for item in evidence["items"]]
    assert observed == [f"fail-{i}" for i in range(5, 10)], (
        f"必须取最近 {FAILURE_EVIDENCE_LIMIT} 条且按时间正序，实际 {observed}"
    )
    step_numbers = [item["step"] for item in evidence["items"]]
    assert step_numbers == sorted(step_numbers), "条目必须按 trace 步骤序号正序"


@pytest.mark.asyncio
async def test_failure_evidence_truncates_long_text(manager):
    """单条文本截断：输入**必须真的超过上限**（30000 字），否则「不超上限」是恒真断言。

    变异点：去掉截断（或去掉 ``text_truncated`` 标志）→ 本条必须变红。
    """
    from web.session import TRANSCRIPT_CONTENT_LIMIT

    huge = "e" * 30000
    assert len(huge) > TRANSCRIPT_CONTENT_LIMIT, "构造前提：输入必须真的超上限"

    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([_tool_result(1, "Bash", "error", huge, "tool_error"),
                        _llm_error(2, "timeout", huge)])

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    tool_item, llm_item = evidence["items"]
    assert len(tool_item["observation"]) <= TRANSCRIPT_CONTENT_LIMIT
    assert tool_item["text_truncated"] is True
    assert len(llm_item["message"]) <= TRANSCRIPT_CONTENT_LIMIT
    assert llm_item["text_truncated"] is True, (
        "llm_error 被截断的是 message——标志必须对它同样成立"
    )


@pytest.mark.asyncio
async def test_failure_evidence_response_is_bounded_under_huge_trace(manager):
    """体积有界（grill 指定的断言形状）。

    ``run.trace`` **从不进入响应**，所以「响应体积有界」不是一句「整包长度小于某个
    宽松常数」就能验的（没有失败时本来就小）。改用可杀变异的最小断言集：
    条数上限、单条文本总量上限、真实总数、截断标志——「不截断」「不设上限」
    「total 报成返回条数」三条变异都必红。
    """
    from web.session import FAILURE_EVIDENCE_LIMIT, TRANSCRIPT_CONTENT_LIMIT

    huge = "z" * 30000
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([
        _tool_result(index + 1, f"Tool{index}", "error", huge, "tool_error")
        for index in range(300)
    ])

    payload = build_node_transcript_payload(manager, scheduler, "a")
    evidence = payload["failure_evidence"]
    assert len(evidence["items"]) <= FAILURE_EVIDENCE_LIMIT
    total_text = sum(
        len(item.get("observation") or "") + len(item.get("message") or "")
        for item in evidence["items"]
    )
    assert total_text <= FAILURE_EVIDENCE_LIMIT * TRANSCRIPT_CONTENT_LIMIT, (
        f"失败证据文本总量无界：{total_text}"
    )
    assert evidence["total"] == 300, "total 必须是真实失败总数（300），不是返回条数"
    assert evidence["truncated"] is True
    # 全量 observation 不得原样出现在响应里。
    assert huge not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_failure_evidence_tolerates_missing_and_empty_fields(manager):
    """空 / 缺字段不得抛异常，且要给出可读降级（生产者可能写空字符串）。"""
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([
        {"step": 1, "type": "tool_result", "data": {"tool_name": "Bash",
                                                    "status": "error"}},
        {"step": 2, "type": "tool_result", "data": {"status": "error",
                                                    "observation": None}},
        {"step": 3, "type": "llm_error", "data": {}},
        {"step": 4, "type": "tool_result", "data": {"status": "error",
                                                    "observation": ["block", "list"]}},
    ])

    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "present"
    assert evidence["total"] == 4
    for item in evidence["items"]:
        assert isinstance(item["observation"], (str, type(None)))
        assert isinstance(item["message"], (str, type(None)))
        assert isinstance(item["text_truncated"], bool)
    json.dumps(evidence, ensure_ascii=False)


@pytest.mark.asyncio
async def test_failure_evidence_projection_is_read_only(manager):
    """只读：投影不得改写 trace，也不得改变执行状态。"""
    scheduler, state, run = await _completed_node(manager)
    run.trace = _trace([_tool_result(1, "Bash", "error", "3 failed", "tool_error")])
    before = json.dumps(run.trace, sort_keys=True)
    snapshot_before = json.dumps(
        scheduler.workflow_graph_snapshot()["nodes"], sort_keys=True)

    build_node_transcript_payload(manager, scheduler, "a")

    assert json.dumps(run.trace, sort_keys=True) == before, "投影不得改写 trace"
    assert json.dumps(scheduler.workflow_graph_snapshot()["nodes"],
                      sort_keys=True) == snapshot_before


# --- 三态挂载：candidates 轻量 / 下钻完整 -----------------------------------


@pytest.mark.asyncio
async def test_candidates_carry_lightweight_failure_evidence(manager):
    """Q5：容器一次渲染 N 项，所以每候选只带**轻量**证据（≤1 条 × ≤400 字符）。

    变异点：把 candidates 改成完整形态（5 条 × 4000）→ 本条必须变红。
    """
    from web.session import FAILURE_EVIDENCE_PREVIEW_LIMIT

    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    state = scheduler._states["fan"]
    for index, slot in enumerate(state.item_runs):
        run = manager.find_run(slot.subagent_id, slot.run_id)
        if run is None:
            continue
        run.trace = _trace([
            _tool_result(step, f"Tool{step}", "error", "x" * 30000, "tool_error")
            for step in range(1, 8)
        ])

    payload = build_node_transcript_payload(manager, scheduler, "fan")
    assert payload["kind"] == "candidates"
    checked = 0
    for candidate in payload["candidates"]:
        evidence = candidate["failure_evidence"]
        assert evidence["state"] == "present"
        assert evidence["total"] == 7, "轻量形态仍须报真实总数"
        assert evidence["truncated"] is True
        assert len(evidence["items"]) <= 1, "轻量形态至多 1 条"
        for item in evidence["items"]:
            text = item.get("observation") or item.get("message") or ""
            assert len(text) <= FAILURE_EVIDENCE_PREVIEW_LIMIT, (
                f"轻量条目文本应 ≤{FAILURE_EVIDENCE_PREVIEW_LIMIT}，实际 {len(text)}"
            )
        checked += 1
    assert checked == 3, "三个展开项都要挂上证据"


@pytest.mark.asyncio
async def test_item_drilldown_carries_full_failure_evidence(manager):
    """Q5 的另一半：下钻到某一项时给**完整**证据（最近 5 条 × 单条 4000）。

    容器轻量、下钻完整——两者必须真的不同，否则「点进去看细节」没有意义。
    """
    from web.session import FAILURE_EVIDENCE_LIMIT

    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    container = build_node_transcript_payload(manager, scheduler, "fan")
    target = container["candidates"][0]
    slot_run = manager.find_run(target["subagent_id"], target["run_id"])
    slot_run.trace = _trace([
        _tool_result(step, f"Tool{step}", "error", "y" * 30000, "tool_error")
        for step in range(1, 8)
    ])

    item = build_node_transcript_payload(
        manager, scheduler, "fan",
        subagent_id=target["subagent_id"], run_id=target["run_id"],
    )
    evidence = item["failure_evidence"]
    assert evidence["state"] == "present"
    assert len(evidence["items"]) == FAILURE_EVIDENCE_LIMIT, "下钻给完整形态（5 条）"
    assert all(item_["text_truncated"] is True for item_ in evidence["items"])

    # 下钻挂载点也要认 ``content_limit``——R3 实证：三处里只有两处被锁，
    # 删掉下钻那处 `content_limit=content_limit` 时原先全绿。
    tightened = build_node_transcript_payload(
        manager, scheduler, "fan",
        subagent_id=target["subagent_id"], run_id=target["run_id"],
        content_limit=100,
    )
    for item_ in tightened["failure_evidence"]["items"]:
        assert len(item_.get("observation") or "") <= 100
        assert len(item_.get("message") or "") <= 100


@pytest.mark.asyncio
async def test_drilldown_without_run_id_still_resolves_the_run(manager):
    """下钻时调用方可以不带 ``run_id``（前端只在 truthy 时才带）。

    ``SubAgentManager.find_run`` 在 ``run_id is None`` 时**恒返回 None**（逐条比较
    id），直译实现会把这条最常见的路径谎报成 ``unavailable``——必须回落到该
    session 的最近一次 run（与 ``inspect_transcript`` 对 None 的既有语义一致）。
    """
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    container = build_node_transcript_payload(manager, scheduler, "fan")
    target = container["candidates"][0]
    slot_run = manager.find_run(target["subagent_id"], target["run_id"])
    slot_run.trace = _trace([_tool_result(1, "Bash", "error", "3 failed", "tool_error")])

    item = build_node_transcript_payload(
        manager, scheduler, "fan", subagent_id=target["subagent_id"], run_id=None,
    )
    assert item["failure_evidence"]["state"] == "present", (
        "不带 run_id 的常见路径被谎报成 unavailable"
    )
    assert item["failure_evidence"]["items"][0]["tool_name"] == "Bash"


@pytest.mark.asyncio
async def test_failure_evidence_key_is_additive_for_all_shapes(manager):
    """三种形态都带 ``failure_evidence`` 键——加性契约，既有键语义不变。"""
    manager.llm = _LLM(content="APPROVED: go")
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)
    for node_id in ("a", "gate", "yes"):
        payload = build_node_transcript_payload(manager, scheduler, node_id)
        assert "failure_evidence" in payload, f"{node_id} 缺 failure_evidence"

    scheduler2 = _scheduler(manager, _foreach_spec(3))
    await scheduler2.run(scheduler2.spec)
    container = build_node_transcript_payload(manager, scheduler2, "fan")
    assert container["kind"] == "candidates"
    assert container["candidates"], "前置：容器确实展开了候选"
    assert all("failure_evidence" in candidate for candidate in container["candidates"]), (
        "容器形态的证据挂在**每个候选**上（用户点进哪一项就问哪一项）"
    )


@pytest.mark.parametrize("state", sorted(FAILURE_EVIDENCE_STATES))
def test_every_failure_evidence_state_has_a_distinct_readable_message(state):
    """七态**每一态**都配有非空、且**与其他态不同**的文案。

    这条防的是「以后再加一个 state 忘了配 message」：文案表缺键时
    ``_FAILURE_EVIDENCE_MESSAGES[state]`` 直接 KeyError；而文案互相串台
    （如 present 用着 unavailable 的话）会让用户读到与自己处境相反的结论——
    本 change 要消灭的就是这类「说假话」。
    """
    assert _FAILURE_EVIDENCE_MESSAGES[state].strip(), f"{state} 缺文案"
    texts = [_FAILURE_EVIDENCE_MESSAGES[s] for s in FAILURE_EVIDENCE_STATES]
    assert len(set(texts)) == len(FAILURE_EVIDENCE_STATES), "七态文案不得重复"


@pytest.mark.asyncio
async def test_failure_evidence_message_always_matches_state(manager):
    """端到端一致性：不管走哪条分支，``message`` 都必须是**该 state 自己**的文案。

    这条覆盖主路径（present）与各负向态——把 message 与 state 分开写的实现
    会在其中某条路径上露馅。
    """
    scheduler, _state, run = await _completed_node(manager)

    cases = [
        (_trace([_tool_result(1, "Bash", "error", "3 failed", "tool_error")]), "present"),
        (_trace([_llm_iteration(1)]), "clean"),
        (_trace([]), "empty_trace"),
        (None, "no_trace"),
    ]
    for trace, expected in cases:
        run.trace = trace
        evidence = build_node_transcript_payload(
            manager, scheduler, "a")["failure_evidence"]
        assert evidence["state"] == expected
        assert evidence["message"] == _FAILURE_EVIDENCE_MESSAGES[expected], (
            f"{expected} 的 message 串台成了别的状态的文案"
        )

    # running：run 未到终态。
    run.trace = None
    run.status = "running"
    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "running"
    assert evidence["message"] == _FAILURE_EVIDENCE_MESSAGES["running"]
    run.status = "completed"

    # unavailable：run 记录被弹出。
    manager._sessions[scheduler._states["a"].subagent_id].runs.pop()
    evidence = build_node_transcript_payload(
        manager, scheduler, "a")["failure_evidence"]
    assert evidence["state"] == "unavailable"
    assert evidence["message"] == _FAILURE_EVIDENCE_MESSAGES["unavailable"]


# --- 快照失败计数（Q6 方案 D：「任务」tab 的零请求线索） ----------------------
#
# 计数在 run 终态那一刻算一次并存进 ``NodeState``/``_ItemRunSlot``，所以这些用例
# 必须让 trace **在跑的过程中**就带上失败步骤（一个会炸的 LLM 会经
# ``record_llm_error`` 写进 trace），而不是跑完再去改 ``run.trace``——后者测的是
# 「改内存能不能反映到快照」，不是本 change 的埋点。


class _SelectiveBoomLLM(_LLM):
    """只对含指定标记的 task 抛异常，其余正常返回。

    foreach 展开项共用同一个 llm 实例，所以要靠 task 文本区分「哪一项该失败」。
    """

    def __init__(self, markers):
        super().__init__()
        self.markers = tuple(markers)

    async def chat(self, messages, tools=None, model="gpt-4"):
        blob = " ".join(str(getattr(m, "content", "")) for m in messages)
        if any(marker in blob for marker in self.markers):
            raise RuntimeError("model exploded: " + "x" * 200)
        return await super().chat(messages, tools=tools, model=model)


def _node_by_id(snapshot: dict, node_id: str) -> dict:
    return next(node for node in snapshot["nodes"] if node["id"] == node_id)


@pytest.mark.asyncio
async def test_snapshot_carries_failure_count_for_terminal_run(manager):
    """终态 run 的 trace 里有 N 条失败 → 快照节点带 ``N``。

    走真实路径：``_BoomLLM`` 抛异常 → ``record_llm_error`` 把 ``llm_error`` 写进该
    run 的 trace → 终态那一刻被计数。变异点：把 ``_launch_run`` 的计数埋点删掉 →
    快照字段恒为 ``None``，本条必须变红。
    """
    manager.llm = _BoomLLM()
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    node = _node_by_id(scheduler.workflow_graph_snapshot(), "a")
    assert node["failure_count"] == 1


@pytest.mark.asyncio
async def test_snapshot_failure_count_is_zero_when_checked_and_clean(manager):
    """零失败 → ``0``（**不是** ``None``）：``0`` 是正向声明「检查过、没事」，
    ``None`` 是「没数据」——两者在「任务」tab 上的显示行为不同（Q6 粒度确认）。
    """
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    node = _node_by_id(scheduler.workflow_graph_snapshot(), "a")
    assert node["failure_count"] == 0


@pytest.mark.asyncio
async def test_snapshot_failure_count_is_none_without_usable_trace(manager):
    """没有可用 trace 的节点 → ``None``，**不得**报成 ``0``。

    注意范围：本条只证明「未派发 → 快照字段是 None」这一条**结果**，它**不能**证明
    ``count_failures`` 自己区分了「无数据」与「零失败」（未派发节点根本没走到那个
    函数）。该函数的判定由 ``test_count_failures_distinguishes_no_data_from_zero``
    直接锁定——实测把空 trace 改成返回 0 时，**只有**那条直接单测会红。
    """
    scheduler = _scheduler(manager, _route_spec())
    # 不 run：全部节点停在 pending，从未派发 → 没有 trace。
    node = _node_by_id(scheduler.workflow_graph_snapshot(), "yes")
    assert node["failure_count"] is None


@pytest.mark.asyncio
async def test_snapshot_failure_count_covers_foreach_items(manager):
    """展开项的计数走**同一处**埋点（``_launch_run`` 的 ``reuse_state`` 身份槽）。

    这条是「一处埋点覆盖两种身份」的证据：若只在普通节点路径埋点，展开项会恒为
    ``None``（容器快照上「这一项里面有失败」就永远是空白）。
    """
    manager.llm = _SelectiveBoomLLM(["item-1"])
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    state = scheduler._states["fan"]

    counts = [slot.failure_count for slot in state.item_runs]
    assert counts[1] == 1, f"失败那一项必须带计数，实际 {counts}"
    assert counts[0] == 0 and counts[2] == 0, f"正常项应为 0，实际 {counts}"


@pytest.mark.asyncio
async def test_snapshot_failure_count_field_is_bounded(manager):
    """快照加法字段是**有界整数**，不是证据列表（Q6：快照按事件推送，不能塞证据）。

    变异点：把整份证据塞进节点投影 → 字段类型不再是 int，本条变红；单测层面再用
    一条 300 步 × 4000 字的 trace 证明计数本身与文本长度无关。
    """
    from agent.trace_recorder import count_failures

    huge_trace = _trace([
        _tool_result(index, "Bash", "error", "x" * 4000, "tool_error")
        for index in range(1, 301)
    ])
    assert count_failures(huge_trace) == 300, "计数不得随文本长度失真"

    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)
    node = _node_by_id(scheduler.workflow_graph_snapshot(), "a")
    assert isinstance(node["failure_count"], int)
    assert set(node) >= {"failure_count"}
    assert "items" not in node and "evidence" not in node, "快照只给计数，不给证据"


# --- count_failures / iter_failure_steps 的直接单测 ---------------------------
#
# 快照那几条用例走的是**真实执行路径**（计数在 run 终态时算一次），所以它们证明的是
# 「埋点接上了」，**不能**证明 ``count_failures`` 自己对各种 trace 形状的判定。
# 实测教训：把 ``count_failures`` 的「空 trace 返回 None」改成返回 ``0``，
# 快照那组用例**全绿**——因为「未派发节点」的计数根本没被算过（保持在 dataclass
# 默认 ``None``），根本没经过这个函数。所以这两个助手必须有**直接**单测。


def test_count_failures_distinguishes_no_data_from_zero():
    """``None``（没有可用 trace）与 ``0``（采集到了、零失败）不得折叠。

    这是 OTel ``Unset`` 重载那个坑的机械防线：折叠后「没数据」会在 UI 上显示成
    「已检查、无失败」——后者是**正向声明**，不能白给。
    """
    from agent.trace_recorder import count_failures

    assert count_failures(None) is None, "没有 trace → None（不是 0）"
    assert count_failures({"steps": []}) is None, "空 trace → None（不是 0，也不是「没事」）"
    assert count_failures({"steps": [{"step": 1, "type": "llm_iteration", "data": {}}]}) == 0, (
        "有步骤、零失败 → 0（这才是「已检查、没事」）"
    )
    assert count_failures({}) is None, "缺 steps 键 → 按没有可用 trace 处理"
    assert count_failures("not a dict") is None, "非 dict → 不抛异常"
    assert count_failures({"steps": [_llm_error(1, "timeout")]}) == 1


def test_iter_failure_steps_only_yields_failures():
    """失败判据：``status != "ok"`` 的 ``tool_result`` + 全部 ``llm_error``。

    变异点：把判据写成 ``status == "error"``（只认显式 error）→ 会把
    ``status`` 为其它非 ok 值（如 ``cancelled``）的失败漏掉；把 ``llm_error``
    去掉 → 本条变红。
    """
    from agent.trace_recorder import iter_failure_steps

    steps = [
        _llm_iteration(1),
        _tool_result(2, "Read", "ok", "fine"),
        _tool_result(3, "Bash", "error", "3 failed", "tool_error"),
        _llm_error(4, "network_timeout"),
        _tool_result(5, "Edit", "cancelled", "interrupted"),
    ]
    kinds = [(s["type"], s["data"].get("status")) for s in iter_failure_steps(steps)]
    assert kinds == [("tool_result", "error"), ("llm_error", None),
                     ("tool_result", "cancelled")], (
        "只应产出失败步骤：非 ok 的 tool_result（不只是 error）+ 全部 llm_error"
    )


def test_iter_failure_steps_tolerates_malformed_steps():
    """残缺 step 不得把整段投影带崩（非 dict / 缺 data / data 不是 dict）。"""
    from agent.trace_recorder import iter_failure_steps

    steps = [
        "not a dict",
        {"step": 1, "type": "tool_result"},
        {"step": 2, "type": "tool_result", "data": "not a dict"},
        {"step": 3, "type": "llm_error", "data": {"error_type": "x"}},
        None,
    ]
    assert [s["step"] for s in iter_failure_steps(steps)] == [3]
    assert list(iter_failure_steps(None)) == []


# --- `state is None` 分支（节点不在当前执行计划里） --------------------------
#
# 用户确认的判据（Q4）：``state is None`` → ``unavailable``（**不是**
# ``not_applicable``——「不在计划里」不是「结构上不可能产生 run」，后者是
# route/collect 的语义）。这条分支此前**零测试覆盖**（grep「不在当前执行计划」在
# tests/ 下零命中），是个实现-测试缺口。


@pytest.mark.asyncio
async def test_unknown_node_is_unavailable_not_not_applicable(manager):
    """节点不在调度器的 ``_states`` 里 → ``unavailable`` + 说明文案。

    与 route/collect 的 ``not_applicable`` **必须不同**：后者是「这个节点类型天然
    没有 run」，本条是「这个节点现在拿不到证据」（例如前端拿着过期 node_id 来查、
    或图已重置）。两者对用户的行动指引不同，折叠会误导。
    """
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    payload = build_node_transcript_payload(manager, scheduler, "nope")
    assert payload["kind"] == "none"
    evidence = payload["failure_evidence"]
    assert evidence["state"] == "unavailable", (
        "用户确认的映射是 state is None → unavailable，不是 not_applicable"
    )
    assert evidence["state"] != "not_applicable"
    assert evidence["message"] == _FAILURE_EVIDENCE_MESSAGES["unavailable"] or (
        "不在当前执行计划" in evidence["message"]
    )
    assert evidence["items"] == []


@pytest.mark.asyncio
async def test_unknown_node_message_matches_its_state(manager):
    """自定义文案也必须与 state 配对（不能只改文案不改 state，或反之）。"""
    scheduler = _scheduler(manager, _single_spec())
    await scheduler.run(scheduler.spec)

    evidence = build_node_transcript_payload(
        manager, scheduler, "nope")["failure_evidence"]
    assert isinstance(evidence["message"], str) and evidence["message"].strip()
    assert "不产生 run" not in evidence["message"], (
        "unavailable 的文案不得说成「该节点类型不产生 run」——那是 not_applicable 的话"
    )


class _FakeRun:
    """投影只读 ``status`` 与 ``trace``——用最小替身把「可断言 state」语义钉死。"""

    def __init__(self, status, trace):
        self.status = status
        self.trace = trace

def test_failure_evidence_rejects_unknown_explicit_state(manager):
    """显式传入的 ``state=`` 必须是枚举取值——不认识就报错，不静默按 trace 继续走。

    放过去会让调用方以为「我指定了 unavailable」，实际却按 trace 内容走成
    clean/present。静默用错取值比直接报错难查得多（本项目的历史病根就是
    「文档承诺了、实现漂了」）。
    """
    from web.session import _failure_evidence

    for bogus in ("clena", "PRESENT", "", "unavailable "):
        with pytest.raises(ValueError):
            _failure_evidence(None, state=bogus)
    # 从 trace 推出的取值**也不能**由调用方断言——静默忽略会让人以为「我指定了」，
    # 照做则会谎报（例如调用方说 present 而 trace 里其实干净）。fail-fast。
    trace_with_failure = _trace([_tool_result(1, "Bash", "error", "3 failed", "tool_error")])
    for derived in ("present", "clean", "empty_trace", "no_trace"):
        with pytest.raises(ValueError):
            _failure_evidence(_FakeRun("completed", trace_with_failure), state=derived)
    # 三个可断言的取值必须被**尊重**（不是被忽略后按 trace 重算）。
    assert _failure_evidence(None, state="unavailable")["state"] == "unavailable"
    assert _failure_evidence(_FakeRun("completed", trace_with_failure),
                             state="not_applicable")["state"] == "not_applicable"
    assert _failure_evidence(_FakeRun("running", None), state="running")["state"] == "running"


@pytest.mark.asyncio
async def test_real_callers_only_pass_declared_states(manager):
    """所有真实调用点传的 state 都在枚举内（上面那条守卫不会误伤自家调用）。"""
    manager.llm = _LLM(content="APPROVED: go")
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)
    for node_id in ("a", "gate", "yes", "no", "nope"):
        payload = build_node_transcript_payload(manager, scheduler, node_id)
        assert payload["failure_evidence"]["state"] in FAILURE_EVIDENCE_STATES


@pytest.mark.asyncio
async def test_failure_evidence_honours_content_limit(manager):
    """``content_limit`` 必须透传到失败证据的条目截断（review R2 Issue 3）。

    此前三个挂载点都没往下传，于是载荷声明 ``content_limit=100`` 而条目文本仍是
    4000——契约漂移。变异点：把任一处 ``content_limit=content_limit`` 去掉 → 本条变红。
    """
    scheduler, _state, run = await _completed_node(manager)
    run.trace = _trace([_tool_result(1, "Bash", "error", "z" * 30000, "tool_error")])

    payload = build_node_transcript_payload(manager, scheduler, "a", content_limit=100)
    assert payload["content_limit"] == 100
    item = payload["failure_evidence"]["items"][0]
    assert len(item["observation"]) <= 100, (
        f"载荷声明单条上限 100，条目却给了 {len(item['observation'])} 字符"
    )
    assert item["text_truncated"] is True


@pytest.mark.asyncio
async def test_failure_evidence_content_limit_applies_to_candidates(manager):
    """容器形态同样要认 ``content_limit``（轻量上限与它取交集）。"""
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    for slot in scheduler._states["fan"].item_runs:
        slot_run = manager.find_run(slot.subagent_id, slot.run_id)
        if slot_run is not None:
            slot_run.trace = _trace([_tool_result(1, "Bash", "error", "z" * 30000)])

    payload = build_node_transcript_payload(manager, scheduler, "fan", content_limit=50)
    for candidate in payload["candidates"]:
        for item in candidate["failure_evidence"]["items"]:
            assert len(item["observation"]) <= 50


@pytest.mark.asyncio
async def test_queue_full_run_is_not_reported_as_queued_for_candidates(manager):
    """``queue_full`` 属终态：候选投影**不得**把它改写成 ``queued``（D7 的行为断言）。

    R3 实证：原来的守卫只是「源码里不得出现某个字符串」，把集合少写一个
    ``queue_full`` 的等价漂移能存活——而那正是 D7 要防的「取值集合漂移」。
    这里改成**行为断言**：真造一个 ``queue_full`` 的 run，看候选怎么报。
    """
    scheduler = _scheduler(manager, _foreach_spec(3))
    await scheduler.run(scheduler.spec)
    state = scheduler._states["fan"]
    target = state.item_runs[0]
    run = manager.find_run(target.subagent_id, target.run_id)
    run.status = "queue_full"

    candidates = _foreach_candidates(manager, scheduler, state, TRANSCRIPT_CONTENT_LIMIT)
    reported = [c["status"] for c in candidates
                if c["subagent_id"] == target.subagent_id]
    # 候选状态取**项级记录**（`item_states`）的真相；只有当 run 处于**非终态**时
    # 才会被改写成 running/queued。``queue_full`` 属终态 ⇒ 如实保留记录值。
    # 变异（把 queue_full 从终态清单里删掉）→ 会被改写成 "queued" → 本条变红。
    assert "queued" not in reported, (
        f"queue_full 是终态，被改写成 queued 了——终态清单漂移（D7 要防的正是这个）：{reported}"
    )
    assert reported == ["completed"], f"候选状态应保留项级记录值：{reported}"


def test_terminal_run_statuses_has_a_single_source():
    """终态清单在 web 层只有一处定义（D7：不新造第四份）。

    ``_foreach_candidates`` 曾经内联着同一份字面量，改常量不会波及它——实测把
    模块常量的 ``queue_full`` 删掉，全量 web 测试**全绿**（漂移无人发现）。本条把
    「两处必须一致」钉死：候选判据现在直接引用模块常量。
    """
    import inspect

    import web.session as session_module

    source = inspect.getsource(session_module)
    # 「内联字面量」的特征是**括号里成串**出现（常量自身的定义会长成 frozenset({\n   ...})，
    # 形状不同）；这里查的是 `not in ("completed", "failed", ...)` 那种调用点写法。
    for inline in ('("completed", "failed", "cancelled"',
                   '("completed",\n',
                   '"completed", "failed", "cancelled", "budget_exceeded", "queue_full")'):
        assert inline not in source, (
            f"web/session.py 里仍有内联的终态字面量 {inline!r}——应引用 _TERMINAL_RUN_STATUSES"
        )
    assert session_module._TERMINAL_RUN_STATUSES == frozenset(
        {"completed", "failed", "cancelled", "budget_exceeded", "queue_full"}
    ), "终态取值不得悄悄增减（与 manager/scheduler 的既有口径对齐）"

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
from web.session import build_node_transcript_payload


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
    from agent.subagent.manager import TOOL_CALL_ARGUMENT_LIMIT
    from web.session import TRANSCRIPT_MAX_LIMIT

    # 两个契约数字必须同值（一处改了另一处忘改 = 两条路径口径漂移）。
    assert InspectSubagentTranscriptTool.MAX_TRANSCRIPT_LIMIT == TRANSCRIPT_MAX_LIMIT

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

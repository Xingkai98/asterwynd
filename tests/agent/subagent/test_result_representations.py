"""三种结果表示（D7/Q6）：artifact / scheduler internal / parent bounded。

grill 决策 8 + Q6 拍板：**不能只做 ``to_result_dict`` 出口裁剪**——裁剪若经
``_format_run_envelope`` → ``_execute_subagent`` → ``state.summary`` →
``_node_task_text`` 一路传导，下游也会拿到裁剪版。所以三种表示必须分开：

1. **artifact**：完整结果，落盘（``result_ref`` 指向的文件）；
2. **scheduler internal**：下游调度消费的文本（``_node_task_text`` /
   ``_aggregate_task_text`` 产出）——按预算裁剪，不 concat 全文；
3. **parent/public envelope**：bounded summary + refs。

同时锁定：``run.summary`` 保留**全文**（Q6），bounded 只发生在出口投影与落盘件。

issue #213 更正了 ③ 的口径：envelope 的 ``summary`` 在**模型面出口**按固定单条上限
（``TRANSCRIPT_ITEM_LIMIT``）裁剪，不再等于 ``run.summary`` 全文——记录层不受影响，
内部消费可显式传 ``full_summary=True`` 取全量。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

LONG = "FULL-RESULT-" * 800  # 9600 chars，远超 leaf 档预算


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=LONG, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "produce"},
        {"id": "b", "kind": "subagent", "task": "consume"},
        {"id": "root", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "root", "reducer": "concat"},
    ],
    "terminal": ["root"],
}


@pytest.mark.asyncio
async def test_three_representations_are_distinct(manager):
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(SPEC))
    store = manager.workflow_store(scheduler.workflow_id)

    # ① artifact：完整正文落盘
    run_a = manager.find_run(scheduler._states["a"].subagent_id, scheduler._states["a"].run_id)
    assert store.load(run_a.result_ref) == LONG

    # ② scheduler internal：下游 b 的任务文本按预算裁剪，不含完整正文
    b_task = scheduler._node_task_text(scheduler._states["b"].node)
    assert LONG not in b_task
    assert len(b_task) < len(LONG)

    # ③ parent envelope：节点摘要 bounded（_SUMMARY_LIMIT=400），但带 ref
    node_a = next(node for node in result["nodes"] if node["id"] == "a")
    assert len(node_a["summary"]) <= 400
    assert LONG not in json.dumps(result)

    # ③' run 级 parent envelope：**出口**按模型面单条上限裁剪（issue #213），
    # 但 ``run.summary`` 记录层仍是全文（见下一条测试）——两者不再是同一份文本。
    from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

    run_envelope = manager._format_run_envelope(
        scheduler._states["a"].subagent_id, run_a
    )
    assert len(run_envelope["summary"]) <= TRANSCRIPT_ITEM_LIMIT, (
        "模型面出口的 summary 必须 bounded（issue #213）"
    )
    assert LONG not in json.dumps(run_envelope)
    assert run_envelope["summary_truncated"] is True
    assert run_envelope["summary_full_chars"] == len(LONG), (
        "被裁掉多少要如实给出，模型才知道值不值得翻页"
    )
    # 全量仍可显式取得——调度器等内部消费走这条（否则聚合会静默跳过压缩）。
    full_envelope = manager._format_run_envelope(
        scheduler._states["a"].subagent_id, run_a, full_summary=True
    )
    assert full_envelope["summary"] == LONG
    assert len(run_envelope["bounded_summary"]) < len(LONG)
    assert run_envelope["result_ref"] == run_a.result_ref


@pytest.mark.asyncio
async def test_run_summary_keeps_full_text(manager):
    """Q6：``run.summary`` 是全文，裁剪只发生在出口/落盘件。"""
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(SPEC))
    run_a = manager.find_run(scheduler._states["a"].subagent_id, scheduler._states["a"].run_id)
    assert run_a.summary == LONG
    assert run_a.summary_ref is not None
    store = manager.workflow_store(scheduler.workflow_id)
    assert len(store.load(run_a.summary_ref)) < len(LONG)


@pytest.mark.asyncio
async def test_downstream_receives_ref_not_truncated_blob(manager):
    """层级中间节点消费 bounded summary（Q7）：被裁剪时下游必须拿到取全文的 ref。"""
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(SPEC))
    run_a = manager.find_run(scheduler._states["a"].subagent_id, scheduler._states["a"].run_id)
    b_task = scheduler._node_task_text(scheduler._states["b"].node)
    # b 拿到的是 a 的 bounded 产出 + a 的 result_ref（不是被裁的残缺正文）
    assert run_a.result_ref in b_task
    assert "bounded" in b_task
    assert LONG not in b_task

"""资产可发现面：注入范围（只 root）+ 可裁剪（cacheable=False）+ 跨会话可用性。

覆盖 tasks 2.9b（注入范围与 cacheable）、2.5（跨会话集成）、2.6b（键集锁）、
2.10（GetWorkflowAsset 手动重放绕过钳制的表征测试）。
"""
from __future__ import annotations

import json

import pytest

from agent.config import AsterwyndConfig, SubagentsConfig, WorkflowLimitsConfig
from agent.context.builder import ContextBuilder
from agent.context.protocol import BuildContext
from agent.context.workflow_asset_source import WorkflowAssetIndexSource
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent import workflow_assets as wa
from agent.subagent.manager import SubAgentManager
from agent.subagent.workflow_assets import WorkflowAsset, WorkflowAssetStore
from agent.tools.builtin.subagents import (
    GetWorkflowAssetTool,
    RunWorkflowTool,
    SaveWorkflowAssetTool,
)
from agent.workspace_policy import WorkspacePolicy

FANOUT_SPEC = {
    "goal": "research",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "task a"},
        {"id": "b", "kind": "subagent", "task": "task b"},
        {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"},
    ],
    "edges": [
        {"from": "a", "to": "join", "reducer": "concat"},
        {"from": "b", "to": "join", "reducer": "concat"},
    ],
}


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture()
def asset_base(tmp_path, monkeypatch):
    base = tmp_path / "home" / ".asterwynd" / "projects"
    monkeypatch.setattr(wa, "ASSET_DIR_BASE", base)
    return base


def _manager(tmp_path, **limits) -> SubAgentManager:
    config = AsterwyndConfig(
        subagents=SubagentsConfig(workflow=WorkflowLimitsConfig(**limits))
    )
    return SubAgentManager(
        llm=StaticLLM(),
        config=config,
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


async def _render(source, tmp_path) -> str:
    ctx = BuildContext(
        cwd=str(tmp_path), mode=AgentMode.BUILD, context_window=100_000, total_budget=20_000
    )
    return await source.render(ctx)


# --- 注入源本体（task 2.9b） ------------------------------------------------


@pytest.mark.asyncio
async def test_asset_index_source_renders_names(asset_base, tmp_path):
    store = WorkflowAssetStore.for_workspace(tmp_path)
    store.save(
        WorkflowAsset(
            name="release-audit",
            description="五路并行审计",
            source="dsl",
            goal="g",
            spec=FANOUT_SPEC,
            spec_hash="h",
            node_count=2,
        )
    )
    source = WorkflowAssetIndexSource(manager=_manager(tmp_path))
    text = await _render(source, tmp_path)
    assert "release-audit" in text
    assert "数据" in text and "指令" in text


@pytest.mark.asyncio
async def test_asset_index_source_empty_when_no_assets(asset_base, tmp_path):
    source = WorkflowAssetIndexSource(manager=_manager(tmp_path))
    assert await _render(source, tmp_path) == ""


def test_asset_index_source_is_not_cacheable():
    """cacheable=False：必须能被预算裁剪（与 MemoryIndexSource 相反）。"""
    assert WorkflowAssetIndexSource.cacheable is False
    assert WorkflowAssetIndexSource.critical is False


@pytest.mark.asyncio
async def test_asset_index_source_is_trimmable(asset_base, tmp_path):
    store = WorkflowAssetStore.for_workspace(tmp_path)
    store.save(
        WorkflowAsset(
            name="release-audit", description="d", source="dsl", goal="g",
            spec=FANOUT_SPEC, spec_hash="h", node_count=2,
        )
    )
    builder = ContextBuilder(total_budget=1)
    builder.register(WorkflowAssetIndexSource(manager=_manager(tmp_path)))
    blocks = await builder.build_blocks(
        BuildContext(cwd=str(tmp_path), mode=AgentMode.BUILD, context_window=100_000, total_budget=1)
    )
    # 预算压到 1 token：可裁剪源应当被裁掉（若 cacheable=True 则仍在）
    assert blocks == []


def test_root_loop_includes_asset_index_subagent_loop_does_not(tmp_path):
    """构造期事实：root loop 注册该源，子 loop 不注册（Q9）。

    ``_build_subagent_loop`` 是**子 loop** 构造器（生产调用点只有
    ``manager.py`` 的 run 路径），它一律传 False；root 走 ``AgentLoop`` 的默认
    ``include_workflow_asset_index=True``。
    """
    from agent.loop import AgentLoop
    from agent.tools.registry import ToolRegistry

    manager = _manager(tmp_path)
    child = manager._build_subagent_loop(AgentMode.BUILD, depth=1)
    assert child.include_workflow_asset_index is False
    assert not any(
        isinstance(s, WorkflowAssetIndexSource) for s in child.context_builder._sources
    )

    root = AgentLoop(
        llm=StaticLLM(),
        tool_registry=ToolRegistry(),
        subagent_manager=manager,
    )
    assert root.include_workflow_asset_index is True
    assert any(
        isinstance(s, WorkflowAssetIndexSource) for s in root.context_builder._sources
    )


# --- 跨会话可用性（task 2.5） ----------------------------------------------


@pytest.mark.asyncio
async def test_asset_is_usable_from_a_fresh_manager(asset_base, tmp_path):
    """新会话（新 manager + 新 store 实例）能看到并调用上一个会话存的资产。"""
    from agent.tools.builtin.subagents import RunWorkflowAssetTool

    manager = _manager(tmp_path)
    run = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker", task="体检", params={"workers": 2}
        )
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=run["workflow_id"], name="repo-health", description="体检"
    )
    path = WorkflowAssetStore.for_workspace(tmp_path).path_for("repo-health")
    before = path.read_bytes()

    # 模拟新会话：全新 manager 与全新 store 实例
    fresh = _manager(tmp_path)
    from agent.tools.builtin.subagents import ListWorkflowAssetsTool

    listed = json.loads(await ListWorkflowAssetsTool(fresh).execute())
    assert [a["name"] for a in listed["assets"]] == ["repo-health"]

    out = json.loads(
        await RunWorkflowAssetTool(fresh).execute(name="repo-health", wait=True)
    )
    assert out["status"] == "completed"
    assert out["workflow_id"].startswith("wf_")
    # fork 语义：资产本体不被执行污染（字节不变，不只看 mtime）
    assert path.read_bytes() == before


# --- 键集锁：统一入口返回结构逐字不变（task 2.6b，迁移自 run_pattern） ----


@pytest.mark.asyncio
async def test_run_workflow_result_keyset_is_locked(tmp_path):
    """统一入口的返回键集是契约：加字段必须是有意识的。

    变化 ``workflow-builtin-templates``：``run_pattern`` 退役后，这条键集锁的语义
    （「出口加字段必须是有意识的」）改挂到统一入口 ``RunWorkflow`` 的返回体上。

    变化 ``workflow-tool-discoverability``（C8）：**有意识地**新增 ``warnings`` 键——
    route 节点带 ``task`` 时给可行动提示，且 ``RunWorkflow(spec=...)`` 不经过
    ``DeclareWorkflowTool.execute``，warning 必须挂在 run envelope 上。键**恒存在**
    （无 warning 时为空数组），保持返回体形状稳定；template 路径为 ``[]``。
    """
    manager = _manager(tmp_path)
    result = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker", task="t", params={"workers": 2}
        )
    )
    assert set(result) == {
        "workflow_id",
        "spec_hash",
        "goal",
        "status",
        "nodes",
        "completed",
        "failed",
        "total",
        "cancelled",
        "budget_exceeded",
        "blocked",
        "pending",
        "latest_events",
        "root_result_ref",
        "attribution",
        "attribution_ref",
        "steps",
        "limits",
        "peak_active",
        "critical_path_s",
        "total_cost",
        "run_count",
        "queue_wait_s",
        "queue_cancelled_runs",
        "queue_full_runs",
        "graph_recursion_exceeded",
        "useful_runs",
        "redundancy",
        "rejected_runs",
        "depth_capped_runs",
        "spawn_budget_rejected",
        "workflow_spawn_count",
        "budget",
        "started_at",
        "finished_at",
        "current_nodes",
        "diagnostics",
        "declared_spec_hash",
        "expansion_plan_hash",
        "runtime_graph_hash",
        "inserted_nodes",
        "nodes_total",
        "nodes_omitted",
        "warnings",  # change workflow-tool-discoverability：route `task` 的可行动提示（C8）
    }


@pytest.mark.asyncio
async def test_asset_source_field_does_not_leak_into_result(tmp_path):
    """溯源字段是纯附加：不污染统一入口返回体（键集锁的对照面）。"""
    manager = _manager(tmp_path)
    result = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker", task="t", params={"workers": 2}
        )
    )
    assert "asset_source" not in result


# --- GetWorkflowAsset 手动重放绕过钳制（task 2.10，已知残余面） ------------


@pytest.mark.asyncio
async def test_manual_replay_via_run_workflow_bypasses_clamping(asset_base, tmp_path):
    """把 Q2=A 的已知残余绕过面**显式钉成预期行为**，而不是让它意外存在。

    ``GetWorkflowAsset`` 取回 spec 后由调用方自己 ``RunWorkflow(spec=...)``，
    等价于「模型手写 spec」，按 Q2=A 不收紧——该路径下声明值仍然生效。
    """
    manager = _manager(tmp_path)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(
            spec={**FANOUT_SPEC, "max_runs": 5000}, wait=True
        )
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="big-fanout", description="x"
    )

    got = json.loads(await GetWorkflowAssetTool(manager).execute(name="big-fanout"))
    replay = json.loads(await RunWorkflowTool(manager).execute(spec=got["spec"], wait=True))
    assert replay["limits"]["max_runs"] == {
        "declared": 5000,
        "applied": 5000,
        "clamped": False,
    }

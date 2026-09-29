"""统一 Workflow 入口的 ``template`` 输入（D1/D2/D4）。

``RunWorkflow`` 接受 **exactly one of** `{spec, template}`：

- 两条路径产出**同一种形状**（`parent_envelope()` bounded 投影）。
- 非法组合（同时给 / 都不给 / 缺 task / 未知模板名 / spec 路径带 params 或 task）
  结构化拒绝（``invalid_input``）。
- ``template`` 路径内部走 ``compile_pattern``（D1/D3 的共享编译路径），并把
  ``asset_source`` 置为 pattern 溯源（D4）——保存时才能落成 recipe 资产。
- 工具 schema 摘掉 ``required: ["spec"]``（否则 ``template`` 调用被判缺参）。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent import workflow_assets as wa
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import compile_pattern
from agent.tools.builtin.subagents import RunWorkflowTool, SaveWorkflowAssetTool
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="worker result", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def asset_base(tmp_path, monkeypatch):
    """资产落点是 per-repo 的（``~/.asterwynd/...``）——贴到 tmp 里做隔离。"""
    base = tmp_path / "home" / ".asterwynd" / "projects"
    monkeypatch.setattr(wa, "ASSET_DIR_BASE", base)
    return base


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=5,
    )


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "task a"},
        {"id": "root", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [{"from": "a", "to": "root", "reducer": "concat"}],
    "terminal": ["root"],
}

TERMINAL_STATUSES = {
    "completed",
    "completed_with_failures",
    "stalled",
    "failed",
    "cancelled",
    "budget_exceeded",
    "graph_recursion_exceeded",
}


async def _run(manager, **kwargs) -> dict:
    return json.loads(await RunWorkflowTool(manager).execute(**kwargs))


# --- 入参互斥（D1） ---------------------------------------------------------


@pytest.mark.asyncio
async def test_spec_and_template_mutually_exclusive(manager):
    out = await _run(manager, spec=SPEC, template="orchestrator-worker", task="t")
    assert out["status"] == "invalid_input"
    assert "one of" in out["reason"] or "二选一" in out["reason"] or "exactly" in out["reason"].lower()


@pytest.mark.asyncio
async def test_neither_spec_nor_template_rejected(manager):
    out = await _run(manager)
    assert out["status"] == "invalid_input"


@pytest.mark.asyncio
async def test_template_without_task_rejected(manager):
    out = await _run(manager, template="orchestrator-worker")
    assert out["status"] == "invalid_input"
    assert "task" in out["reason"]


@pytest.mark.asyncio
async def test_unknown_template_rejected(manager):
    out = await _run(manager, template="nope", task="t")
    assert out["status"] == "invalid_input"
    # 自足：列出可用模板
    assert "orchestrator-worker" in out["reason"]


@pytest.mark.asyncio
async def test_spec_path_rejects_params(manager):
    out = await _run(manager, spec=SPEC, params={"workers": 3})
    assert out["status"] == "invalid_input"


@pytest.mark.asyncio
async def test_spec_path_rejects_task(manager):
    out = await _run(manager, spec=SPEC, task="stray")
    assert out["status"] == "invalid_input"


# --- 形状统一（D2） ---------------------------------------------------------


@pytest.mark.asyncio
async def test_template_path_compiles_to_same_spec(manager):
    """template 路径编译出的 spec 与 compile_pattern 逐字一致（spec_hash 相等）。"""
    out = await _run(manager, template="orchestrator-worker", task="t", params={"workers": 2})
    scheduler = manager.get_workflow(out["workflow_id"])
    expected = compile_pattern("orchestrator-worker", task="t", params={"workers": 2})
    assert scheduler.spec.spec_hash == expected.spec_hash


@pytest.mark.asyncio
async def test_both_paths_return_same_keys(manager):
    via_template = await _run(manager, template="orchestrator-worker", task="t", params={"workers": 2})
    via_spec = await _run(manager, spec=SPEC)
    assert set(via_template) == set(via_spec)
    # pattern 专属扁平字段不得出现
    for forbidden in ("pattern", "workers", "selected", "selector", "summary"):
        assert forbidden not in via_template
    assert "bus" not in via_template
    assert "bus" not in via_spec


@pytest.mark.asyncio
async def test_template_path_reports_run_semantics_diagnostics(manager):
    """template 路径返回的 completed/failed 是 run 口径（与 D2 一致）。"""
    out = await _run(manager, template="orchestrator-worker", task="t", params={"workers": 3})
    assert out["status"] in TERMINAL_STATUSES
    # 3 个 worker 各一次 run + aggregate(collect 不起 run) ⇒ completed == 3
    assert out["completed"] == 3


# --- asset_source 溯源迁移（D4） -------------------------------------------


@pytest.mark.asyncio
async def test_template_path_sources_pattern_recipe(asset_base, manager):
    out = await _run(manager, template="orchestrator-worker", task="t", params={"workers": 2})
    saved = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id=out["workflow_id"], name="my-recipe", description="d"
        )
    )
    assert saved["action"] == "created"
    from agent.subagent.workflow_assets import asset_store_for_manager

    asset = asset_store_for_manager(manager).get("my-recipe")
    assert asset.source == "pattern"
    assert asset.recipe["pattern"] == "orchestrator-worker"
    assert asset.recipe["params"] == {"workers": 2}
    assert asset.recipe["task"] == "t"


@pytest.mark.asyncio
async def test_spec_path_sources_dsl_asset(asset_base, manager):
    out = await _run(manager, spec=SPEC)
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=out["workflow_id"], name="my-dsl", description="d"
    )
    from agent.subagent.workflow_assets import asset_store_for_manager

    asset = asset_store_for_manager(manager).get("my-dsl")
    assert asset.source == "dsl"


# --- schema（2.2） ----------------------------------------------------------


def test_schema_drops_required_spec():
    params = RunWorkflowTool.parameters
    assert "template" in params["properties"]
    assert "task" in params["properties"]
    assert params.get("required", []) == []


# --- wait=false 回执（D6） --------------------------------------------------


@pytest.mark.asyncio
async def test_wait_false_returns_receipt_not_result(manager):
    out = await _run(manager, template="orchestrator-worker", task="t", params={"workers": 2}, wait=False)
    assert out["status"] == "running"
    assert out["status"] not in TERMINAL_STATUSES

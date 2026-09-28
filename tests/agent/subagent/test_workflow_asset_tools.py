"""四个资产工具的模型面：保存 / 列表 / 读取 / 按名运行 + 深度闸。

覆盖 tasks 2.3、2.5、2.5c、2.6、2.6b、2.9b、2.10：

- ``SaveWorkflowAsset`` 从 ``workflow_id`` 取 spec（不穿模型输出）、pattern 溯源
  分类、保留名拒绝、权限档 ``AGENT_STATE_PERMISSION``。
- ``RunWorkflowAsset`` 消费 ``manager.effective_mode``（#255 通道），列出将以声明
  mode 运行的节点，返回体带 ``limits_clamped``。
- 深度闸：``RunWorkflowAsset`` ∈ ``SPAWN_TOOL_NAMES``，其余三个不在。
- 命名空间隔离与覆盖未声明拒绝。
"""
from __future__ import annotations

import json

import pytest

from agent.config import AsterwyndConfig, WorkflowLimitsConfig, SubagentsConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent import workflow_assets as wa
from agent.subagent.manager import SPAWN_TOOL_NAMES, SubAgentManager
from agent.subagent.workflow_assets import WorkflowAssetStore
from agent.tool_permissions import AGENT_STATE_PERMISSION
from agent.tools.builtin.subagents import (
    GetWorkflowAssetTool,
    ListWorkflowAssetsTool,
    RunPatternTool,
    RunWorkflowAssetTool,
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

MODE_SPEC = {
    "goal": "mode check",
    "nodes": [
        {"id": "writer", "kind": "subagent", "task": "write", "mode": "build"},
        {"id": "reader", "kind": "subagent", "task": "read", "mode": "read_only"},
        {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"},
    ],
    "edges": [
        {"from": "writer", "to": "join", "reducer": "concat"},
        {"from": "reader", "to": "join", "reducer": "concat"},
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


def _manager(tmp_path, *, mode=AgentMode.BUILD, recursion_limit=25, max_runs=300) -> SubAgentManager:
    config = AsterwyndConfig(
        subagents=SubagentsConfig(
            workflow=WorkflowLimitsConfig(
                recursion_limit=recursion_limit, max_nodes=200, max_runs=max_runs
            )
        )
    )
    return SubAgentManager(
        llm=StaticLLM(),
        config=config,
        parent_mode=mode,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _store(tmp_path) -> WorkflowAssetStore:
    return WorkflowAssetStore.for_workspace(tmp_path)


# --- SaveWorkflowAsset（tasks 2.5c：pattern 溯源 + DSL 分类） ----------------


@pytest.mark.asyncio
async def test_save_dsl_asset_from_workflow_id(asset_base, tmp_path):
    manager = _manager(tmp_path)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=True)
    )
    out = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id=declared["workflow_id"],
            name="release-audit",
            description="审计",
        )
    )
    assert out["action"] == "created"
    saved = _store(tmp_path).get("release-audit")
    assert saved.source == "dsl"
    assert saved.spec["goal"] == "research"


@pytest.mark.asyncio
async def test_save_pattern_asset_keeps_recipe(asset_base, tmp_path):
    """pattern 路径的溯源落在 scheduler.asset_source 上（task 2.5c）。"""
    manager = _manager(tmp_path)
    run = json.loads(
        await RunPatternTool(manager).execute(
            pattern="orchestrator-worker", task="体检", params={"workers": 2}
        )
    )
    out = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id=run["workflow_id"], name="repo-health", description="体检"
        )
    )
    assert out["action"] == "created"
    saved = _store(tmp_path).get("repo-health")
    assert saved.source == "pattern"
    assert saved.recipe == {
        "pattern": "orchestrator-worker",
        "params": {"workers": 2},
        "task": "体检",
    }


@pytest.mark.asyncio
async def test_save_rejects_reserved_name(asset_base, tmp_path):
    manager = _manager(tmp_path)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=True)
    )
    out = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id=declared["workflow_id"], name="bidding", description="x"
        )
    )
    assert out["status"] == "reserved_name"
    assert "bidding" in json.dumps(out)
    # 合法路径必须成功（负向套件不是「永远报错也能过」）
    ok = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id=declared["workflow_id"], name="legal-name", description="x"
        )
    )
    assert ok["action"] == "created"


@pytest.mark.asyncio
async def test_save_unknown_workflow_is_rejected(asset_base, tmp_path):
    manager = _manager(tmp_path)
    out = json.loads(
        await SaveWorkflowAssetTool(manager).execute(
            workflow_id="wf_nope", name="a-name", description="x"
        )
    )
    assert out["status"] == "unknown"


def test_save_tool_permission_is_agent_state():
    assert SaveWorkflowAssetTool.permission is AGENT_STATE_PERMISSION
    assert SaveWorkflowAssetTool.read_only is False


# --- List / Get -------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_and_get_asset(asset_base, tmp_path):
    manager = _manager(tmp_path)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=True)
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="release-audit", description="审计"
    )

    listed = json.loads(await ListWorkflowAssetsTool(manager).execute())
    assert listed["total"] == 1
    assert listed["assets"][0]["name"] == "release-audit"
    assert "spec" not in listed["assets"][0]

    got = json.loads(
        await GetWorkflowAssetTool(manager).execute(name="release-audit")
    )
    assert got["source"] == "dsl"
    assert got["spec"]["goal"] == "research"


@pytest.mark.asyncio
async def test_get_unknown_asset(asset_base, tmp_path):
    manager = _manager(tmp_path)
    out = json.loads(await GetWorkflowAssetTool(manager).execute(name="nope"))
    assert out["status"] == "unknown_asset"


def test_list_and_get_are_read_only():
    assert ListWorkflowAssetsTool.read_only is True
    assert GetWorkflowAssetTool.read_only is True


# --- RunWorkflowAsset：mode 消费 + 钳制报告（tasks 2.3 / 2.10） -------------


@pytest.mark.asyncio
async def test_run_asset_reports_limits_clamped(asset_base, tmp_path):
    manager = _manager(tmp_path, max_runs=300)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(
            spec={**FANOUT_SPEC, "max_runs": 5000}, wait=True
        )
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="big-fanout", description="x"
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(name="big-fanout", wait=True)
    )
    assert out["status"] == "completed"
    assert out["limits"]["max_runs"] == {"declared": 5000, "applied": 300, "clamped": True}
    assert out["limits_clamped"]["max_runs"] == {"declared": 5000, "applied": 300}


@pytest.mark.asyncio
async def test_run_asset_lists_nodes_running_with_declared_mode(asset_base, tmp_path):
    """BUILD 会话下，声明 build 的节点出现在「以声明 mode 运行」清单里。"""
    manager = _manager(tmp_path, mode=AgentMode.BUILD)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(spec=MODE_SPEC, wait=True)
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="writer-graph", description="x"
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(name="writer-graph", wait=True)
    )
    assert out["declared_mode_nodes"] == {"writer": "build", "reader": "read_only"}


@pytest.mark.asyncio
async def test_run_asset_clamps_node_mode_to_session(asset_base, tmp_path):
    """只读会话下，声明 build 的节点被收窄并记 diagnostics（Q5=B）。"""
    manager = _manager(tmp_path, mode=AgentMode.READ_ONLY)
    saver = _manager(tmp_path, mode=AgentMode.BUILD)
    declared = json.loads(
        await RunWorkflowTool(saver).execute(spec=MODE_SPEC, wait=True)
    )
    await SaveWorkflowAssetTool(saver).execute(
        workflow_id=declared["workflow_id"], name="writer-graph", description="x"
    )

    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(name="writer-graph", wait=True)
    )
    # writer 声明 build 但会话只读 ⇒ 不进「以声明 mode 运行」清单，进 diagnostics
    assert "writer" not in out.get("declared_mode_nodes", {})
    assert out["declared_mode_nodes"].get("reader") == "read_only"
    assert any(d["node"] == "writer" for d in out["mode_diagnostics"])
    writer_diag = next(d for d in out["mode_diagnostics"] if d["node"] == "writer")
    assert writer_diag["declared"] == "build"
    assert writer_diag["applied"] == "read_only"


@pytest.mark.asyncio
async def test_run_asset_rejects_override_for_missing_node(asset_base, tmp_path):
    """覆盖面声明了 spec 中不存在的节点 ⇒ 结构化拒绝，不是裸 KeyError。

    M1 回归（building review Round 1）：磁盘上的资产可能被手改/漂移，覆盖面指向
    一个已不存在的节点 id。这条路径必须给出自足的 `override_not_declared`，而不是
    让 `KeyError` 逃逸成 `[Error: 'ghost']`。**对照**：合法节点覆盖必须成功（见
    `test_run_asset_applies_declared_override`）。
    """
    from agent.subagent.workflow_assets import WorkflowAsset
    from agent.tools.builtin.subagents import parse_spec_for_manager

    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, FANOUT_SPEC)
    _store(tmp_path).save(
        WorkflowAsset(
            name="drifted",
            description="x",
            source="dsl",
            goal=spec.goal,
            spec=spec.to_dict(),
            overrides={"ghost": ["task"]},
            spec_hash=spec.spec_hash,
            node_count=len(spec.nodes),
        )
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(
            name="drifted", overrides={"ghost": {"task": "rewritten"}}, wait=True
        )
    )
    assert out["status"] == "override_not_declared"
    assert "ghost" in out["reason"]


@pytest.mark.asyncio
async def test_run_asset_reports_limits_when_not_waiting(asset_base, tmp_path):
    """``wait=False`` 的返回体也报生效值（L1 回归）。

    ``wait=True`` 在协程尚未跑起来时会取到空的 scheduler 报告；报告改为从已解析的
    spec 直接算，两条路径口径一致。
    """
    manager = _manager(tmp_path, max_runs=300)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(
            spec={**FANOUT_SPEC, "max_runs": 5000}, wait=True
        )
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="big-fanout", description="x"
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(name="big-fanout", wait=False)
    )
    assert out["limits"]["max_runs"] == {"declared": 5000, "applied": 300, "clamped": True}
    assert out["limits_clamped"]["max_runs"] == {"declared": 5000, "applied": 300}


@pytest.mark.asyncio
async def test_run_asset_rejects_undeclared_override(asset_base, tmp_path):
    manager = _manager(tmp_path)
    declared = json.loads(
        await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=True)
    )
    await SaveWorkflowAssetTool(manager).execute(
        workflow_id=declared["workflow_id"], name="plain", description="x"
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(
            name="plain", overrides={"a": {"task": "changed"}}
        )
    )
    assert out["status"] == "override_not_declared"


@pytest.mark.asyncio
async def test_run_asset_applies_declared_override(asset_base, tmp_path):
    """声明了覆盖面时，调用传覆盖值在 parse 之前应用（Q3=B）。

    覆盖面由**保存者显式声明**，保存工具不自动推断——这里直接落一份声明了
    ``{"a": ["task"]}`` 的 DSL 资产，再断言调用时覆盖被接受且图能跑通。
    """
    from agent.subagent.workflow_assets import WorkflowAsset
    from agent.tools.builtin.subagents import parse_spec_for_manager

    manager = _manager(tmp_path)
    spec = parse_spec_for_manager(manager, FANOUT_SPEC)
    _store(tmp_path).save(
        WorkflowAsset(
            name="tweakable",
            description="x",
            source="dsl",
            goal=spec.goal,
            spec=spec.to_dict(),
            overrides={"a": ["task"]},
            spec_hash=spec.spec_hash,
            node_count=len(spec.nodes),
        )
    )
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(
            name="tweakable", overrides={"a": {"task": "rewritten"}}, wait=True
        )
    )
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_run_asset_rejects_workflow_id_as_name(asset_base, tmp_path):
    manager = _manager(tmp_path)
    out = json.loads(
        await RunWorkflowAssetTool(manager).execute(name="wf_1a2b3c4d")
    )
    assert out["status"] in ("invalid_asset", "invalid_name", "unknown_asset")
    assert "wf_1a2b3c4d" in json.dumps(out)


@pytest.mark.asyncio
async def test_get_workflow_rejects_slug(asset_base, tmp_path):
    """命名空间隔离：资产名不能当 workflow_id 用（走既有未知路径）。"""
    from agent.tools.builtin.subagents import GetWorkflowTool

    manager = _manager(tmp_path)
    out = json.loads(await GetWorkflowTool(manager).execute(workflow_id="release-audit"))
    assert out["status"] == "unknown"


def test_run_asset_consumes_mode_ceiling_channel():
    """RunWorkflowAsset 走 manager.effective_mode（#255 的 scheduler 可读通道）。"""
    import inspect

    from agent.subagent import manager as manager_module

    assert hasattr(manager_module.SubAgentManager, "effective_mode")
    assert hasattr(manager_module.SubAgentManager, "mode_ceiling")


# --- 深度闸（task 2.6） -----------------------------------------------------


def test_run_asset_is_a_spawn_tool():
    assert "RunWorkflowAsset" in SPAWN_TOOL_NAMES


def test_non_spawn_asset_tools_are_not_in_spawn_list():
    assert "SaveWorkflowAsset" not in SPAWN_TOOL_NAMES
    assert "ListWorkflowAssets" not in SPAWN_TOOL_NAMES
    assert "GetWorkflowAsset" not in SPAWN_TOOL_NAMES


def test_depth_limited_child_has_no_run_asset_but_keeps_save_list(tmp_path):
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        max_depth=1,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    loop = manager._build_subagent_loop(AgentMode.BUILD, depth=1)
    names = {tool["function"]["name"] for tool in loop.tool_registry.get_all_schemas()}
    assert "RunWorkflowAsset" not in names
    assert "SaveWorkflowAsset" in names
    assert "ListWorkflowAssets" in names
    assert "GetWorkflowAsset" in names

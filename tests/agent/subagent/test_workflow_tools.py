"""Workflow 分离式工具入口 + 深度闸 + 三闸配置（tasks 4.1/4.2、5.3；Q1/Q5/Q7/Q8）。

覆盖：

- DeclareWorkflow / StartWorkflow / GetWorkflow / CancelWorkflow / RunWorkflow，
- 工具面元数据：全部不 parallelizable；Declare/Get/Cancel read_only，
  Start/Run 走 SUBAGENT_CONTROL_PERMISSION（Q7），
- 深度到限的子 agent 工具集不含 StartWorkflow/RunWorkflow（grill 决策 6），
- 三闸配置落点 `subagents.workflow.*`（Q5/D6），
- workflow 注册表是 manager 作用域内存（Q1）。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig, load_config
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SPAWN_TOOL_NAMES, SubAgentManager
from agent.tools.builtin.subagents import (
    CancelWorkflowTool,
    DeclareWorkflowTool,
    GetWorkflowTool,
    RunWorkflowTool,
    StartWorkflowTool,
)
from agent.workspace_policy import WorkspacePolicy

FANOUT_SPEC = {
    "goal": "research",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "task a"},
        {"id": "b", "kind": "subagent", "task": "task b"},
        {
            "id": "join",
            "kind": "aggregate",
            "join": "all_required",
            "strategy": "collect",
        },
    ],
    "edges": [
        {"from": "a", "to": "join", "reducer": "concat"},
        {"from": "b", "to": "join", "reducer": "concat"},
    ],
}


class GatedLLM:
    def __init__(self):
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    def release(self) -> None:
        self.gate.set()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.started.set()
        await self.gate.wait()
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- 4.1/4.2 工具入口 -------------------------------------------------------


@pytest.mark.asyncio
async def test_declare_start_get_roundtrip(manager):
    declared = json.loads(
        await DeclareWorkflowTool(manager).execute(spec=FANOUT_SPEC)
    )
    assert declared["status"] == "declared"
    workflow_id = declared["workflow_id"]
    assert declared["spec_hash"]
    assert declared["nodes"] == ["a", "b", "join"]

    started = json.loads(
        await StartWorkflowTool(manager).execute(workflow_id=workflow_id)
    )
    assert started["status"] == "completed"
    assert started["completed"] == 2

    got = json.loads(await GetWorkflowTool(manager).execute(workflow_id=workflow_id))
    assert got["status"] == "completed"
    assert got["spec_hash"] == declared["spec_hash"]


@pytest.mark.asyncio
async def test_get_unknown_workflow_returns_bounded_error(manager):
    out = json.loads(await GetWorkflowTool(manager).execute(workflow_id="wf_nope"))
    assert out["status"] == "unknown"
    assert "unknown workflow_id" in out["reason"]


@pytest.mark.asyncio
async def test_declare_rejects_invalid_spec(manager):
    out = json.loads(
        await DeclareWorkflowTool(manager).execute(
            spec={"goal": "bad", "nodes": [], "edges": []}
        )
    )
    assert out["status"] == "invalid_spec"
    assert "nodes" in out["reason"]


@pytest.mark.asyncio
async def test_run_workflow_declares_and_starts_in_one_call(manager):
    out = json.loads(await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC))
    assert out["status"] == "completed"
    assert out["completed"] == 2
    assert out["workflow_id"].startswith("wf_")
    # RunWorkflow 内部走 Declare+Start，所以注册表里能查到这张图（Q1）
    assert manager.get_workflow(out["workflow_id"]) is not None


@pytest.mark.asyncio
async def test_run_workflow_wait_false_returns_immediately(manager):
    manager.llm = GatedLLM()
    out = json.loads(
        await RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=False)
    )
    assert out["status"] in ("running", "declared")
    assert out["workflow_id"] in manager.list_workflows()
    manager.llm.release()


@pytest.mark.asyncio
async def test_cancel_workflow_returns_cancelling_immediately(manager):
    manager.llm = GatedLLM()
    runner = asyncio.create_task(
        RunWorkflowTool(manager).execute(spec=FANOUT_SPEC, wait=False)
    )
    declared = json.loads(await runner)
    workflow_id = declared["workflow_id"]
    scheduler = manager.get_workflow(workflow_id)
    await asyncio.sleep(0.05)

    out = json.loads(await CancelWorkflowTool(manager).execute(workflow_id=workflow_id))
    # Q8：取消立即返回「取消已提交」，不等 in-flight 停下
    assert out["status"] == "cancelling"
    assert out["workflow_id"] == workflow_id
    manager.llm.release()
    await asyncio.sleep(0.1)
    status = json.loads(await GetWorkflowTool(manager).execute(workflow_id=workflow_id))
    assert status["status"] == "cancelled"
    assert scheduler is not None


@pytest.mark.asyncio
async def test_cancel_unknown_workflow_is_bounded(manager):
    out = json.loads(await CancelWorkflowTool(manager).execute(workflow_id="wf_nope"))
    assert out["status"] == "unknown"


# --- Q7 工具面元数据 --------------------------------------------------------


def test_workflow_tools_are_never_parallelizable():
    """Q7：一轮多个 RunWorkflow(wait=true) 不能同时调度多张图抢 max_active。"""
    for tool_cls in (
        DeclareWorkflowTool,
        StartWorkflowTool,
        GetWorkflowTool,
        CancelWorkflowTool,
        RunWorkflowTool,
    ):
        assert tool_cls.parallelizable is False, tool_cls.__name__


def test_workflow_tools_read_only_flags():
    assert DeclareWorkflowTool.read_only is True
    assert GetWorkflowTool.read_only is True
    assert CancelWorkflowTool.read_only is True


# --- 深度闸（grill 决策 6） -------------------------------------------------


def test_spawn_tool_names_include_workflow_entries():
    assert "StartWorkflow" in SPAWN_TOOL_NAMES
    assert "RunWorkflow" in SPAWN_TOOL_NAMES


def test_depth_limited_child_has_no_workflow_spawn_tools(tmp_path):
    manager = SubAgentManager(
        llm=StaticLLM(), config=AsterwyndConfig(), max_depth=1,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    loop = manager._build_subagent_loop(AgentMode.BUILD, depth=1)
    names = {tool["function"]["name"] for tool in loop.tool_registry.get_all_schemas()}
    assert "StartWorkflow" not in names
    assert "RunWorkflow" not in names
    assert "GetWorkflow" in names  # 只读查询仍可用
    assert "DeclareWorkflow" in names  # 声明不 spawn，保留
    assert "CancelWorkflow" in names


# --- Q5 三闸配置落点 --------------------------------------------------------


def test_workflow_limits_are_configurable(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    (tmp_path / "asterwynd.yaml").write_text(
        """
subagents:
  workflow:
    recursion_limit: 7
    max_nodes: 30
    max_runs: 40
""",
        encoding="utf-8",
    )
    config = load_config(start_dir=tmp_path)
    assert config.subagents.workflow.recursion_limit == 7
    assert config.subagents.workflow.max_nodes == 30
    assert config.subagents.workflow.max_runs == 40


def test_workflow_limits_default_to_documented_values():
    config = AsterwyndConfig()
    assert config.subagents.workflow.recursion_limit == 25
    assert config.subagents.workflow.max_nodes == 200
    assert config.subagents.workflow.max_runs == 300


def test_workflow_limits_reject_non_positive(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    (tmp_path / "asterwynd.yaml").write_text(
        "subagents:\n  workflow:\n    recursion_limit: 0\n", encoding="utf-8"
    )
    with pytest.raises(Exception):
        load_config(start_dir=tmp_path)


@pytest.mark.asyncio
async def test_declared_spec_inherits_config_limits_when_absent(tmp_path, monkeypatch, manager):
    """未在 spec 里写上限时，DeclareWorkflow 用配置的三闸默认值。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    (tmp_path / "asterwynd.yaml").write_text(
        "subagents:\n  workflow:\n    recursion_limit: 3\n", encoding="utf-8"
    )
    manager.config = load_config(start_dir=tmp_path)
    out = json.loads(await DeclareWorkflowTool(manager).execute(spec=FANOUT_SPEC))
    assert out["recursion_limit"] == 3


# --- Q1 注册表作用域 --------------------------------------------------------


def test_registry_is_manager_scoped(tmp_path):
    one = SubAgentManager(
        llm=StaticLLM(), config=AsterwyndConfig(),
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    two = SubAgentManager(
        llm=StaticLLM(), config=AsterwyndConfig(),
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    one.register_workflow(_StubWorkflow("wf_shared"))
    assert one.get_workflow("wf_shared") is not None
    # 另一个 manager 看不到（Q1：不落盘、不跨 session）
    assert two.get_workflow("wf_shared") is None


class _StubWorkflow:
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

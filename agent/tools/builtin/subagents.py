from __future__ import annotations

import asyncio
import json
from typing import Any

from agent.message import Message
from agent.subagent.bus import MessageBus, estimate_tokens
from agent.subagent.context import current_bus
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import run_pattern
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import (
    WorkflowSpec,
    WorkflowValidationError,
    parse_workflow_spec,
)
from agent.subagent.workflow_store import DEFAULT_READ_LIMIT, WorkflowStore
from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import SUBAGENT_CONTROL_PERMISSION


@tool_parameters(
    name="CreateSubagent",
    description="Create a child subagent session for future runs.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "mode": {"type": "string", "enum": ["build", "read_only", "plan"]},
        },
        "required": ["name"],
    },
)
class CreateSubagentTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = self.manager.create_subagent(
            name=kwargs["name"],
            description=kwargs.get("description", ""),
            mode=kwargs.get("mode"),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="RunSubagent",
    description=(
        "Start a new run in an existing child subagent session. Returns "
        "status 'running' when an execution slot was free, or 'queued' with a "
        "run_id when the concurrency limit is saturated — a queued run has not "
        "started yet, so collect its result later with "
        "GetSubagentRun(wait=true). Returns status 'queue_full' when the "
        "pending queue is full: wait for running/queued runs to finish "
        "(GetSubagentRun(wait=true)) before spawning more."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "task": {"type": "string"},
            "wait": {
                "type": "boolean",
                "description": (
                    "Block until the run reaches a terminal state, across both "
                    "queueing and execution. Defaults to false."
                ),
            },
            "timeout_s": {"type": "number"},
        },
        "required": ["subagent_id", "task"],
    },
)
class RunSubagentTool(Tool):
    read_only = True
    parallelizable = True  # fan-out: several calls in one turn run concurrently
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = await self.manager.run_subagent(
            subagent_id=kwargs["subagent_id"],
            task=kwargs["task"],
            wait=kwargs.get("wait", False),
            timeout_s=kwargs.get("timeout_s"),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="ListSubagents",
    description="List child subagent sessions visible to the current parent session.",
    parameters={"type": "object", "properties": {}, "required": []},
)
class ListSubagentsTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        return json.dumps(self.manager.list_subagents(), ensure_ascii=False)


@tool_parameters(
    name="GetSubagentRun",
    description=(
        "Get the result or current status of a child subagent run. Statuses "
        "include 'queued' (waiting for an execution slot; not started yet), "
        "'running', and the terminal states completed/failed/cancelled/"
        "budget_exceeded. Pass wait=true to block until the run reaches a "
        "terminal state — this is how queued results are collected."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "run_id": {"type": "string"},
            "wait": {
                "type": "boolean",
                "description": (
                    "Block until the run reaches a terminal state, across both "
                    "queueing and execution. Defaults to false."
                ),
            },
            "timeout_s": {"type": "number"},
        },
        "required": ["subagent_id"],
    },
)
class GetSubagentRunTool(Tool):
    read_only = True
    parallelizable = True  # collecting several queued results in one turn
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = await self.manager.get_subagent_run(
            subagent_id=kwargs["subagent_id"],
            run_id=kwargs.get("run_id"),
            wait=kwargs.get("wait", False),
            timeout_s=kwargs.get("timeout_s"),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="CancelSubagentRun",
    description="Cancel the active or specified child subagent run.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["subagent_id"],
    },
)
class CancelSubagentRunTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = await self.manager.cancel_subagent_run(
            subagent_id=kwargs["subagent_id"],
            run_id=kwargs.get("run_id"),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="InspectSubagentTranscript",
    description="Inspect a bounded summary or recent messages from a child subagent transcript.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "scope": {"type": "string", "enum": ["summary", "recent_messages"]},
            "run_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1},
            "include_tool_results": {"type": "boolean"},
        },
        "required": ["subagent_id"],
    },
)
class InspectSubagentTranscriptTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = self.manager.inspect_transcript(
            subagent_id=kwargs["subagent_id"],
            scope=kwargs.get("scope", "summary"),
            run_id=kwargs.get("run_id"),
            limit=kwargs.get("limit", 5),
            include_tool_results=kwargs.get("include_tool_results", False),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="PublishBusMessage",
    description="Publish a summary to the active orchestration message bus "
    "(exchanges summarized findings between collaborating subagents).",
    parameters={
        "type": "object",
        "properties": {
            "sender": {"type": "string", "description": "Name identifying the publishing agent."},
            "topic": {"type": "string", "description": "Message topic (e.g. 'finding', 'proposal', 'review')."},
            "content": {"type": "string", "description": "The finding/fact to share."},
            "max_tokens": {"type": "integer", "description": "Token budget for the published summary."},
        },
        "required": ["sender", "topic", "content"],
    },
)
class PublishBusMessageTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        bus = current_bus()
        if bus is None:
            return json.dumps({"error": "no active message bus"}, ensure_ascii=False)
        content = kwargs["content"]
        max_tokens = kwargs.get("max_tokens", 400)
        summary = content
        token_count = estimate_tokens(content)
        if token_count > max_tokens:
            summary = await self._summarize(content, max_tokens)
            token_count = estimate_tokens(summary)
        msg = bus.publish(
            sender=kwargs["sender"],
            topic=kwargs["topic"],
            summary=summary,
            token_count=token_count,
        )
        return json.dumps(msg.to_dict(), ensure_ascii=False)

    async def _summarize(self, content: str, max_tokens: int) -> str:
        """Fold content into a summary under ``max_tokens`` (publish-side layer)."""
        llm = self.manager.llm
        if llm is None:
            return content[: max_tokens * 4]
        try:
            from agent.context.summarizer import LLMSummarizer

            summarizer = LLMSummarizer(llm)
            summary = await summarizer.summarize(
                [Message(role="user", content=content)],
                budget=max_tokens,
            )
            return summary or content[: max_tokens * 4]
        except Exception:
            return content[: max_tokens * 4]


@tool_parameters(
    name="ReadBus",
    description="Read recent summaries from the active orchestration message bus "
    "within a strict token budget.",
    parameters={
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional topic filter.",
            },
            "max_tokens": {"type": "integer", "description": "Consume-side token window."},
            "limit": {"type": "integer", "description": "Max number of messages to return."},
        },
        "required": [],
    },
)
class ReadBusTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        bus = current_bus()
        if bus is None:
            return json.dumps({"error": "no active message bus"}, ensure_ascii=False)
        messages = bus.read(
            topics=kwargs.get("topics"),
            max_tokens=kwargs.get("max_tokens"),
            limit=kwargs.get("limit"),
        )
        return json.dumps(
            {
                "count": len(messages),
                "messages": [m.to_dict() for m in messages],
            },
            ensure_ascii=False,
        )


@tool_parameters(
    name="ResumeSubagent",
    description="Resume a previously interrupted subagent run from its checkpoint.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "run_id": {"type": "string", "description": "The interrupted run's id (its checkpoint key)."},
            "task": {"type": "string", "description": "Continue instruction for the resumed run."},
            "wait": {"type": "boolean"},
            "timeout_s": {"type": "number"},
            "max_tokens": {"type": "integer"},
            "max_time_s": {"type": "number"},
        },
        "required": ["subagent_id", "run_id", "task"],
    },
)
class ResumeSubagentTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = await self.manager.resume_subagent(
            subagent_id=kwargs["subagent_id"],
            run_id=kwargs["run_id"],
            task=kwargs["task"],
            wait=kwargs.get("wait", False),
            timeout_s=kwargs.get("timeout_s"),
            max_tokens=kwargs.get("max_tokens"),
            max_time_s=kwargs.get("max_time_s"),
        )
        return json.dumps(result, ensure_ascii=False)


@tool_parameters(
    name="RunPattern",
    description="Run an orchestration pattern (orchestrator-worker / peer-review / "
    "hierarchical / bidding) over subagents and return the aggregate result.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "enum": ["orchestrator-worker", "peer-review", "hierarchical", "bidding"],
            },
            "task": {"type": "string", "description": "The goal handed to the participating subagents."},
            "params": {
                "type": "object",
                "description": "Pattern params: workers/teams/proposers count, max_rounds, worker_max_tokens, worker_max_time_s.",
            },
        },
        "required": ["pattern", "task"],
    },
)
class RunPatternTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        result = await run_pattern(
            self.manager,
            pattern=kwargs["pattern"],
            task=kwargs["task"],
            params=kwargs.get("params"),
        )
        return json.dumps(result, ensure_ascii=False)


# --- Workflow DSL 入口（change ``workflow-dsl-scheduler``，D1） --------------
#
# 分离式入口：Declare → Start → Get / Cancel；RunWorkflow 是 Declare+Start 的
# 便捷语法（spec 可保存、可哈希、可重放）。五个工具**全部不标 parallelizable**
# （Q7）：一轮里多个 RunWorkflow(wait=true) 若被 asyncio.gather 并发拉起，多张图会
# 同时抢 max_active，可能导致某张图永远等不到槽位。
#
# 深度闸（grill 决策 6）：StartWorkflow/RunWorkflow 已进 ``SPAWN_TOOL_NAMES``，
# 深度到限的子 agent 拿不到它们，无法绕开 max_depth 拉起整张图。


def _spec_bounds(manager: SubAgentManager) -> dict[str, int]:
    """三闸默认值来自配置（Q5/Q9）：spec 未声明时用 ``subagents.workflow.*``。"""
    limits = getattr(getattr(manager.config, "subagents", None), "workflow", None)
    return {
        "default_recursion_limit": getattr(limits, "recursion_limit", 25),
        "default_max_nodes": getattr(limits, "max_nodes", 200),
        "default_max_runs": getattr(limits, "max_runs", 300),
    }


def parse_spec_for_manager(manager: SubAgentManager, raw: Any) -> WorkflowSpec:
    """把模型给的 spec 解析成 WorkflowSpec，带上当前配置的三闸默认值。"""
    return parse_workflow_spec(raw, **_spec_bounds(manager))


def _invalid_spec(exc: Exception) -> str:
    return json.dumps(
        {
            "status": "invalid_spec",
            "reason": str(exc),
            "hint": "fix the workflow spec (see DeclareWorkflow description) and retry",
        },
        ensure_ascii=False,
    )


def _unknown_workflow(workflow_id: str, manager: SubAgentManager) -> str:
    return json.dumps(
        {
            "status": "unknown",
            "workflow_id": workflow_id,
            "reason": (
                f"unknown workflow_id {workflow_id!r}; the registry is per-manager and "
                f"in-memory (known: {sorted(manager.list_workflows())})"
            ),
        },
        ensure_ascii=False,
    )


@tool_parameters(
    name="DeclareWorkflow",
    description=(
        "Declare a workflow topology (a DAG of subagent/aggregate/route/foreach "
        "nodes) and get back a workflow_id. Does not start anything — call "
        "StartWorkflow to run it. Spec shape: {goal, nodes:[{id, kind, task, "
        "outputs, ...}], edges:[{from, to, channel, required, reducer}], entry, "
        "terminal, recursion_limit, max_nodes, max_runs}. Parallel branches "
        "writing the same output slot must declare a reducer "
        "(concat/merge_dict/first_non_empty/last). Cycles are only allowed "
        "through a route node."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spec": {
                "type": "object",
                "description": "The workflow spec (see the tool description).",
            }
        },
        "required": ["spec"],
    },
)
class DeclareWorkflowTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        try:
            spec = parse_spec_for_manager(self.manager, kwargs["spec"])
        except WorkflowValidationError as exc:
            return _invalid_spec(exc)
        scheduler = WorkflowScheduler(self.manager, bus=MessageBus())
        # Attach the parsed spec up front: StartWorkflow executes what was declared
        # here, so the declaration step must carry it (D1).
        scheduler.spec = spec
        self.manager.register_workflow(scheduler)
        return json.dumps(
            {
                "status": "declared",
                "workflow_id": scheduler.workflow_id,
                "spec_hash": spec.spec_hash,
                "goal": spec.goal,
                "nodes": [node.id for node in spec.nodes],
                "entry": list(spec.entry),
                "terminal": list(spec.terminal),
                "recursion_limit": spec.recursion_limit,
                "max_nodes": spec.max_nodes,
                "max_runs": spec.max_runs,
            },
            ensure_ascii=False,
        )


@tool_parameters(
    name="StartWorkflow",
    description=(
        "Start a workflow declared with DeclareWorkflow. With wait=true (default) "
        "blocks until the workflow reaches a terminal state and returns the "
        "bounded run envelope; with wait=false returns immediately with a "
        "'running' envelope that GetWorkflow can poll. A run that exceeds the "
        "graph recursion limit returns status 'graph_recursion_exceeded' with "
        "diagnostics (steps / current nodes / reason), not an exception."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string"},
            "wait": {
                "type": "boolean",
                "description": "Block until the workflow terminates. Defaults to true.",
            },
        },
        "required": ["workflow_id"],
    },
)
class StartWorkflowTool(Tool):
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        workflow_id = kwargs["workflow_id"]
        scheduler = self.manager.get_workflow(workflow_id)
        if scheduler is None:
            return _unknown_workflow(workflow_id, self.manager)
        wait = kwargs.get("wait", True)
        if not wait:
            asyncio.ensure_future(_drive_scheduler(scheduler))
            return json.dumps(
                {"status": "running", "workflow_id": workflow_id, "nodes": []},
                ensure_ascii=False,
            )
        return json.dumps(await _drive_scheduler(scheduler), ensure_ascii=False)


async def _drive_scheduler(scheduler: WorkflowScheduler) -> dict:
    """跑一张已声明的图；已有 spec 则直接执行，否则视为未声明。"""
    spec = scheduler.spec
    if spec is None:
        return {
            "status": "unknown",
            "workflow_id": scheduler.workflow_id,
            "reason": "workflow has no spec attached (declare it with DeclareWorkflow)",
        }
    return await scheduler.run(spec)


@tool_parameters(
    name="ReadWorkflowResult",
    description=(
        "Read a workflow result artifact by its result_ref (page through the "
        "full text). Refs come from a workflow envelope's root_result_ref, from "
        "GetWorkflow(detail='nodes') node refs, or from a run envelope's "
        "result_ref. Pass offset/limit to page; the response reports total_chars "
        "and truncated so you can decide whether to keep reading."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Artifact ref, e.g. artifact://workflow/wf_123/root.",
            },
            "offset": {"type": "integer", "minimum": 0, "description": "Char offset."},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "description": "Max characters to return (default 4000, cap 20000).",
            },
        },
        "required": ["ref"],
    },
)
class ReadWorkflowResultTool(Tool):
    """Q1：把 ``result_ref`` 换成内容的唯一通道（只读、分页）。

    不是 spawn 类工具（不拉起新工作），因此**不进** ``SPAWN_TOOL_NAMES``：深度到限
    的子 agent 仍能读回自己的结果。
    """
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        ref = kwargs["ref"]
        try:
            workflow_id, _key = WorkflowStore.parse_ref(ref)
        except ValueError as exc:
            return json.dumps(
                {"ref": ref, "missing": True, "content": "", "reason": str(exc)},
                ensure_ascii=False,
            )
        store = self.manager.workflow_store(workflow_id)
        page = store.read(ref, offset=kwargs.get("offset", 0), limit=kwargs.get("limit", DEFAULT_READ_LIMIT))
        return json.dumps(page, ensure_ascii=False)


@tool_parameters(
    name="GetWorkflow",
    description=(
        "Get the bounded status of a declared workflow: per-node "
        "{id, kind, status, runs, summary, reason}, run totals, steps, "
        "peak_active, critical_path_s, total_cost and diagnostics. Summaries are "
        "truncated so a large graph cannot blow up the caller's context. Use "
        "detail to pick what the response focuses on: 'summary' (default, node "
        "summaries only), 'nodes' (node summaries plus each node's result_ref — "
        "read the body with ReadWorkflowResult), or 'events' (the latest terminal "
        "transitions)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string"},
            "detail": {
                "type": "string",
                "enum": ["summary", "nodes", "events"],
                "description": "Response focus. Defaults to 'summary'.",
            },
        },
        "required": ["workflow_id"],
    },
)
class GetWorkflowTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    _DETAILS = ("summary", "nodes", "events")

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        workflow_id = kwargs["workflow_id"]
        scheduler = self.manager.get_workflow(workflow_id)
        if scheduler is None:
            return _unknown_workflow(workflow_id, self.manager)
        detail = kwargs.get("detail", "summary")
        if detail not in self._DETAILS:
            return json.dumps(
                {
                    "status": "invalid_detail",
                    "workflow_id": workflow_id,
                    "reason": f"unknown detail {detail!r}; expected one of {list(self._DETAILS)}",
                },
                ensure_ascii=False,
            )
        payload = scheduler.status()
        payload["detail"] = detail
        if detail == "nodes":
            # 节点级摘要 + 各自的 result_ref（**不**展开正文，Q1）。
            refs = _node_refs(scheduler)
            for node in payload["nodes"]:
                ref = refs.get(node["id"])
                if ref:
                    node["result_ref"] = ref
        elif detail == "events":
            payload["nodes"] = []
        return json.dumps(payload, ensure_ascii=False)


def _node_refs(scheduler: WorkflowScheduler) -> dict[str, str]:
    """node_id -> result_ref（只读投影；没有落盘件的节点不出现）。"""
    refs: dict[str, str] = {}
    manager = scheduler.manager
    for node_id, state in scheduler._states.items():
        if not state.subagent_id or not state.run_id:
            continue
        run = manager.find_run(state.subagent_id, state.run_id)
        ref = getattr(run, "result_ref", None) if run is not None else None
        if ref:
            refs[node_id] = ref
    return refs


@tool_parameters(
    name="CancelWorkflow",
    description=(
        "Cancel a workflow. Returns immediately with status 'cancelling' — "
        "in-flight runs are cancelled (writing checkpoints for later resume) "
        "without waiting for them to stop. Poll GetWorkflow for the final state."
    ),
    parameters={
        "type": "object",
        "properties": {"workflow_id": {"type": "string"}},
        "required": ["workflow_id"],
    },
)
class CancelWorkflowTool(Tool):
    read_only = True
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        workflow_id = kwargs["workflow_id"]
        scheduler = self.manager.get_workflow(workflow_id)
        if scheduler is None:
            return _unknown_workflow(workflow_id, self.manager)
        return json.dumps(scheduler.cancel(), ensure_ascii=False)


@tool_parameters(
    name="RunWorkflow",
    description=(
        "Convenience: declare a workflow spec and start it in one call "
        "(Declare+Start). Use DeclareWorkflow/StartWorkflow when you want to "
        "inspect or cancel the graph between the two steps."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spec": {
                "type": "object",
                "description": "The workflow spec (see DeclareWorkflow).",
            },
            "wait": {
                "type": "boolean",
                "description": "Block until the workflow terminates. Defaults to true.",
            },
        },
        "required": ["spec"],
    },
)
class RunWorkflowTool(Tool):
    permission = SUBAGENT_CONTROL_PERMISSION

    def __init__(self, manager: SubAgentManager):
        self.manager = manager

    async def execute(self, **kwargs) -> str:
        try:
            spec = parse_spec_for_manager(self.manager, kwargs["spec"])
        except WorkflowValidationError as exc:
            return _invalid_spec(exc)
        scheduler = WorkflowScheduler(self.manager, bus=MessageBus())
        self.manager.register_workflow(scheduler)
        if not kwargs.get("wait", True):
            asyncio.ensure_future(scheduler.run(spec))
            return json.dumps(
                {
                    "status": "running",
                    "workflow_id": scheduler.workflow_id,
                    "spec_hash": spec.spec_hash,
                    "nodes": [],
                },
                ensure_ascii=False,
            )
        return json.dumps(await scheduler.run(spec), ensure_ascii=False)

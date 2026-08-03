from __future__ import annotations

import json

from agent.message import Message
from agent.subagent.bus import estimate_tokens
from agent.subagent.context import current_bus
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import run_pattern
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
    description="Start a new run in an existing child subagent session.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "task": {"type": "string"},
            "wait": {"type": "boolean"},
            "timeout_s": {"type": "number"},
        },
        "required": ["subagent_id", "task"],
    },
)
class RunSubagentTool(Tool):
    read_only = True
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
    description="Get the result or current status of a child subagent run.",
    parameters={
        "type": "object",
        "properties": {
            "subagent_id": {"type": "string"},
            "run_id": {"type": "string"},
            "wait": {"type": "boolean"},
            "timeout_s": {"type": "number"},
        },
        "required": ["subagent_id"],
    },
)
class GetSubagentRunTool(Tool):
    read_only = True
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

from __future__ import annotations

import json

from agent.subagent.manager import SubAgentManager
from agent.tools.base import Tool, tool_parameters


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

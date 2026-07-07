from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import AGENT_STATE_PERMISSION


SavePlanCallback = Callable[[str, str, list[str]], Awaitable[dict[str, Any]]]


@tool_parameters(
    name="UpdatePlan",
    description=(
        "Save the current draft Markdown plan document and structured "
        "implementation steps while continuing plan-mode discussion. This does "
        "not edit files or execute the plan."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the plan document.",
            },
            "plan_markdown": {
                "type": "string",
                "description": (
                    "Detailed Markdown plan document covering goal, approach, "
                    "steps, risks, and suggested verification."
                ),
            },
            "steps": {
                "type": "array",
                "description": "High-level implementation steps from the plan.",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "required": ["title", "plan_markdown", "steps"],
        "additionalProperties": False,
    },
)
class UpdatePlanTool(Tool):
    name = "UpdatePlan"
    read_only = True
    dangerous = False
    allowed_modes = ("plan",)
    permission = AGENT_STATE_PERMISSION

    def __init__(self, save_plan: SavePlanCallback):
        self._save_plan = save_plan

    async def execute(self, **kwargs) -> str:
        title, plan_markdown, steps_or_error = self._parse_args(kwargs)
        if isinstance(steps_or_error, str):
            return steps_or_error

        document = await self._save_plan(title, plan_markdown, steps_or_error)
        step_count = len(document["steps"])
        return f"[Plan draft updated: {document['title']} ({step_count} steps)]"

    def _parse_args(self, kwargs: dict[str, Any]) -> tuple[str, str, list[str] | str]:
        title = kwargs.get("title")
        plan_markdown = kwargs.get("plan_markdown")
        steps = kwargs.get("steps")

        if not isinstance(title, str) or not title.strip():
            return "", "", "[Error: title must be a non-empty string]"
        if not isinstance(plan_markdown, str) or not plan_markdown.strip():
            return "", "", "[Error: plan_markdown must be a non-empty string]"
        if not isinstance(steps, list) or not steps:
            return "", "", "[Error: steps must be a non-empty array of strings]"
        if any(not isinstance(step, str) or not step.strip() for step in steps):
            return "", "", "[Error: every step must be a non-empty string]"

        return title.strip(), plan_markdown.strip(), steps


@tool_parameters(
    name="ExitPlanMode",
    description=(
        "Submit the final plan-mode Markdown plan document and structured "
        "implementation steps. This finalizes the plan but does not edit files "
        "or execute the plan."
    ),
    parameters=UpdatePlanTool.parameters,
)
class ExitPlanModeTool(UpdatePlanTool):
    name = "ExitPlanMode"

    async def execute(self, **kwargs) -> str:
        title, plan_markdown, steps_or_error = self._parse_args(kwargs)
        if isinstance(steps_or_error, str):
            return steps_or_error

        document = await self._save_plan(title, plan_markdown, steps_or_error)
        step_count = len(document["steps"])
        return f"[Plan submitted: {document['title']} ({step_count} steps)]"

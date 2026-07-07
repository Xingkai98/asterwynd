from __future__ import annotations

from agent.skills.runtime import SkillActivationResult, SkillRuntime
from agent.tools.base import Tool, tool_parameters


@tool_parameters(
    name="ActivateSkill",
    description="Activate a loaded skill for the current run when its full instructions are needed.",
    parameters={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the loaded skill to activate.",
            },
            "reason": {
                "type": "string",
                "description": "Short reason why this skill is needed.",
            },
        },
        "required": ["skill_name"],
    },
)
class ActivateSkillTool(Tool):
    name = "ActivateSkill"
    description = "Activate a loaded skill for the current run."
    parameters = {}
    read_only = True

    def __init__(self, runtime: SkillRuntime):
        self.runtime = runtime
        self.last_activation: SkillActivationResult | None = None

    async def execute(self, skill_name: str, reason: str = "") -> str:
        result = self.runtime.activate_skill(
            skill_name,
            source="llm_tool",
            reason=reason or None,
        )
        self.last_activation = result
        return result.message

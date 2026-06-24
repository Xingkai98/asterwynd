import pytest

from agent.loop import AgentLoop
from agent.llm import LLMResponse, ToolCallDelta
from agent.message import Message
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tools.base import Tool, tool_parameters, ToolCall
from agent.tools.builtin.plan import ExitPlanModeTool, UpdatePlanTool
from agent.tools.registry import ToolRegistry


@tool_parameters(
    name="WriteLike",
    description="write-like tool",
    parameters={"type": "object", "properties": {}},
)
class WriteLikeTool(Tool):
    name = "WriteLike"
    read_only = False
    dangerous = False

    async def execute(self, **kwargs) -> str:
        return "wrote"


class PlanLLM:
    def __init__(self):
        self.messages = []
        self.tools_seen = []
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.messages.append(list(messages))
        self.tools_seen.append(tools or [])
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallDelta(
                        id="plan-1",
                        name="ExitPlanMode",
                        arguments=(
                            '{"title":"Add plan mode",'
                            '"plan_markdown":"# Add plan mode\\n\\n## Steps\\n- Read docs\\n- Implement",'
                            '"steps":["Read docs","Implement plan mode"]}'
                        ),
                    )
                ],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="计划已生成。")


class DraftThenFinalPlanLLM(PlanLLM):
    async def chat(self, messages, tools=None, model="gpt-4"):
        self.messages.append(list(messages))
        self.tools_seen.append(tools or [])
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallDelta(
                        id="draft-1",
                        name="UpdatePlan",
                        arguments=(
                            '{"title":"Draft plan",'
                            '"plan_markdown":"# Draft plan",'
                            '"steps":["Draft step"]}'
                        ),
                    )
                ],
                stop_reason="tool_calls",
            )
        if self.calls == 2:
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallDelta(
                        id="plan-1",
                        name="ExitPlanMode",
                        arguments=(
                            '{"title":"Plan required",'
                            '"plan_markdown":"# Plan required",'
                            '"steps":["Submit plan"]}'
                        ),
                    )
                ],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="计划已提交。")


def _schema_names(registry):
    return {schema["function"]["name"] for schema in registry.get_all_schemas()}


def test_plan_tools_are_only_visible_in_plan_mode():
    async def save_plan(title, markdown, steps):
        return {"title": title, "markdown": markdown, "steps": steps}

    plan_registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    )
    plan_registry.register(UpdatePlanTool(save_plan))
    plan_registry.register(ExitPlanModeTool(save_plan))

    read_only_registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )
    read_only_registry.register(UpdatePlanTool(save_plan))
    read_only_registry.register(ExitPlanModeTool(save_plan))

    assert "ExitPlanMode" in _schema_names(plan_registry)
    assert "UpdatePlan" in _schema_names(plan_registry)
    assert "ExitPlanMode" not in _schema_names(read_only_registry)
    assert "UpdatePlan" not in _schema_names(read_only_registry)


@pytest.mark.asyncio
async def test_exit_plan_mode_tool_is_denied_outside_plan_mode():
    called = False

    async def submit_plan(title, markdown, steps):
        nonlocal called
        called = True
        return {"title": title, "markdown": markdown, "steps": steps}

    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )
    registry.register(ExitPlanModeTool(submit_plan))

    result = await registry.execute(
        ToolCall(
            id="p1",
            name="ExitPlanMode",
            arguments={
                "title": "Plan",
                "plan_markdown": "# Plan",
                "steps": ["Do work"],
            },
        )
    )

    assert "Permission denied" in result
    assert called is False


@pytest.mark.asyncio
async def test_update_plan_tool_is_denied_outside_plan_mode():
    called = False

    async def save_plan(title, markdown, steps):
        nonlocal called
        called = True
        return {"title": title, "markdown": markdown, "steps": steps}

    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY))
    )
    registry.register(UpdatePlanTool(save_plan))

    result = await registry.execute(
        ToolCall(
            id="p1",
            name="UpdatePlan",
            arguments={
                "title": "Plan",
                "plan_markdown": "# Plan",
                "steps": ["Do work"],
            },
        )
    )

    assert "Permission denied" in result
    assert called is False


@pytest.mark.asyncio
async def test_plan_mode_submits_plan_document_and_structured_state():
    events = []
    llm = PlanLLM()
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    )
    registry.register(WriteLikeTool())
    loop = AgentLoop(
        llm=llm,
        tool_registry=registry,
        run_config=AgentRunConfig(mode=AgentMode.PLAN),
    )

    async def on_event(event_type: str, data: dict):
        events.append({"type": event_type, "data": data})

    result = await loop.run([Message(role="user", content="先规划 add-plan-mode")], on_event=on_event)

    first_tool_names = {
        schema["function"]["name"]
        for schema in llm.tools_seen[0]
    }
    assert "ExitPlanMode" in first_tool_names
    assert "UpdatePlan" in first_tool_names
    assert "WriteLike" not in first_tool_names
    assert any(
        "You are running in plan mode" in message.content
        for message in llm.messages[0]
        if message.role == "system"
    )
    assert result.content == "计划已生成。"
    assert loop.plan_document["title"] == "Add plan mode"
    assert loop.plan_document["status"] == "submitted"
    assert loop.plan_document_final is True
    assert loop.planning_state["summary"]["total"] == 2
    assert [event["type"] for event in events] == [
        "run_started",
        "llm_response",
        "planning_state_updated",
        "plan_document_submitted",
        "tool_call",
        "tool_result",
        "llm_response",
        "done",
    ]
    plan_event = next(event for event in events if event["type"] == "plan_document_submitted")
    assert plan_event["data"]["markdown"].startswith("# Add plan mode")
    assert plan_event["data"]["steps"] == ["Read docs", "Implement plan mode"]


@pytest.mark.asyncio
async def test_plan_mode_requires_exit_plan_mode_before_final_answer():
    llm = DraftThenFinalPlanLLM()
    registry = ToolRegistry(
        mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
    )
    loop = AgentLoop(
        llm=llm,
        tool_registry=registry,
        run_config=AgentRunConfig(mode=AgentMode.PLAN),
    )

    events = []

    async def on_event(event_type: str, data: dict):
        events.append({"type": event_type, "data": data})

    result = await loop.run([Message(role="user", content="plan")], on_event=on_event)

    assert result.content == "计划已提交。"
    assert loop.plan_document["title"] == "Plan required"
    assert loop.plan_document["status"] == "submitted"
    assert loop.plan_document_final is True
    assert "plan_document_updated" in [event["type"] for event in events]
    assert "plan_document_submitted" in [event["type"] for event in events]


@pytest.mark.asyncio
async def test_plan_mode_allows_discussion_without_plan_tool_call():
    class DiscussionLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            return LLMResponse(content="我需要先确认验收标准。")

    loop = AgentLoop(
        llm=DiscussionLLM(),
        tool_registry=ToolRegistry(
            mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.PLAN))
        ),
        run_config=AgentRunConfig(mode=AgentMode.PLAN),
    )

    result = await loop.run([Message(role="user", content="先讨论计划")])

    assert result.content == "我需要先确认验收标准。"
    assert loop.plan_document is None
    assert loop.plan_document_final is False

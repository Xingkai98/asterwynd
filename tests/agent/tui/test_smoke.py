"""基于真实 AgentLoop + 共享 ScriptedLLM 的 TUI 入口 smoke 测试。

覆盖输入、运行事件消费和屏幕状态更新。
不得使用只服务 TUI 的私有 fake AgentLoop 替代入口 smoke。
"""

import asyncio
import json

import pytest

from agent.approval import FailClosedApprovalHandler
from agent.commands.registry import build_default_slash_command_registry
from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.planning import PlanningManager
from agent.run_config import AgentMode, AgentRunConfig
from agent.run_identity import new_session_id
from agent.tools.registry import ToolRegistry
from agent.tui.controller import TUIController
from agent.llm import ToolCallDelta
from tests.support.llm_harness import ScriptedLLM, LLMResponse


async def _run_controller_one_turn(
    controller: TUIController,
    user_input: str,
) -> dict:
    """同步运行 controller 的一轮：发送输入，收集 run 结果。"""
    result = await controller.run_async(user_input)
    return result


# ---------------------------------------------------------------------------
# smoke: basic text-only response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tui_controller_with_scripted_llm_text_response():
    """真实 AgentLoop + ScriptedLLM: 文本回复事件消费。"""
    llm = ScriptedLLM(
        [LLMResponse(content="Hello from TUI!", stop_reason="end_turn")],
        model="scripted-test",
    )
    agent = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        planning_manager=PlanningManager(),
        approval_handler=FailClosedApprovalHandler(),
    )
    session_id = new_session_id()
    registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(agent=agent, session_id=session_id, command_registry=registry)

    result = await controller.run_async("say hello")

    assert result["session_id"] == session_id
    assert result["run_id"] is not None
    # 状态不应该是 running
    assert controller.state.is_running is False
    # transcript 应有 user 和 assistant 条目
    roles = [entry.role for entry in controller.state.transcript]
    assert "user" in roles
    assert "assistant" in roles
    # assistant 内容应包含 LLM 回复
    assistant_entries = [
        entry for entry in controller.state.transcript
        if entry.role == "assistant"
    ]
    assert len(assistant_entries) >= 1
    assert "Hello from TUI!" in assistant_entries[-1].content


# ---------------------------------------------------------------------------
# smoke: tool call response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tui_controller_with_tool_calls():
    """真实 AgentLoop + ScriptedLLM: 工具调用事件消费。"""
    import tempfile, os
    tmp_file = os.path.join(tempfile.gettempdir(), "tui_smoke_test.txt")
    with open(tmp_file, "w") as f:
        f.write("test content")

    llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallDelta(
                    id="call-1",
                    name="Read",
                    arguments=json.dumps({"file_path": tmp_file}),
                )
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="I read the file.", stop_reason="end_turn"),
    ])
    from agent.tools.factory import build_default_tool_registry
    from agent.run_config import ModePolicy
    registry = build_default_tool_registry()
    agent = AgentLoop(
        llm=llm,
        tool_registry=registry,
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        planning_manager=PlanningManager(),
        approval_handler=FailClosedApprovalHandler(),
    )
    session_id = new_session_id()
    cmd_registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(agent=agent, session_id=session_id, command_registry=cmd_registry)

    result = await controller.run_async("read the file")

    # 应有工具事件
    assert len(controller.state.tool_events) >= 1
    tool_names = [t.name for t in controller.state.tool_events]
    assert "Read" in tool_names
    # 最终状态
    assert controller.state.is_running is False
    # transcript 应有 assistant 回复
    assistant_entries = [
        entry for entry in controller.state.transcript
        if entry.role == "assistant"
    ]
    assert any("I read the file" in e.content for e in assistant_entries)


# ---------------------------------------------------------------------------
# smoke: multiple turns with session id reuse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tui_controller_multiple_turns_reuses_session_id():
    """多轮对话复用 session id，每轮新 run id。"""
    llm = ScriptedLLM([
        LLMResponse(content="First response", stop_reason="end_turn"),
        LLMResponse(content="Second response", stop_reason="end_turn"),
    ])
    agent = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        planning_manager=PlanningManager(),
        approval_handler=FailClosedApprovalHandler(),
    )
    session_id = new_session_id()
    cmd_registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(agent=agent, session_id=session_id, command_registry=cmd_registry)

    result1 = await controller.run_async("first")
    result2 = await controller.run_async("second")

    # session id 相同
    assert result1["session_id"] == session_id
    assert result2["session_id"] == session_id
    # run id 不同
    assert result1["run_id"] != result2["run_id"]
    # run id 更新到 state
    assert controller.state.run_id == result2["run_id"]
    # message history 累积
    user_messages = [m.content for m in controller.messages if m.role == "user"]
    assert user_messages == ["first", "second"]


# ---------------------------------------------------------------------------
# smoke: agent mode propagates to state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tui_controller_plan_mode_propagates():
    """Plan mode 下 TUI 状态应反映正确的 mode。"""
    llm = ScriptedLLM(
        [LLMResponse(content="Plan draft", stop_reason="end_turn")],
        model="scripted-test",
    )
    agent = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        run_config=AgentRunConfig(mode=AgentMode.PLAN),
        planning_manager=PlanningManager(),
        approval_handler=FailClosedApprovalHandler(),
    )
    session_id = new_session_id()
    cmd_registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(agent=agent, session_id=session_id, command_registry=cmd_registry)

    await controller.run_async("plan something")

    assert controller.state.current_mode == "plan"


# ---------------------------------------------------------------------------
# smoke: error event handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tui_controller_error_event_stops_run():
    """错误事件应停止运行并记录到 transcript。"""
    llm = ScriptedLLM(
        [LLMResponse(content="ok", stop_reason="end_turn")],
        model="scripted-test",
    )
    agent = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        planning_manager=PlanningManager(),
        approval_handler=FailClosedApprovalHandler(),
    )
    session_id = new_session_id()
    cmd_registry = build_default_slash_command_registry(skill_runtime=None)
    controller = TUIController(agent=agent, session_id=session_id, command_registry=cmd_registry)

    # 手动发送 error 事件
    controller.state.is_running = True
    await controller._handle_event("error", {"message": "test error"})

    assert controller.state.is_running is False
    assert any("error" in e.content.lower() for e in controller.state.transcript)

import pytest
import asyncio
from agent.subagent.manager import SubAgentManager
from agent.llm import LLMResponse


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="subagent done", stop_reason="end_turn")


class FailingLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise RuntimeError("llm failed")


class SlowLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        await asyncio.sleep(10)
        return LLMResponse(content="late", stop_reason="end_turn")

@pytest.mark.asyncio
async def test_delegate_returns_subagent_id():
    manager = SubAgentManager()
    task_id = await manager.delegate(
        task="do something",
        tools=[],
        model="gpt-4o-mini",
        llm=None,
    )
    assert task_id is not None
    assert len(task_id) == 8  # hex ID

@pytest.mark.asyncio
async def test_list_subagents():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=SlowLLM())
    assert task_id in manager.list_subagents()
    assert await manager.cancel(task_id) is True


@pytest.mark.asyncio
async def test_subagent_success_writes_result_to_channel():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=StaticLLM())
    channel = manager.get_channel(task_id)

    result = await channel.get_result(timeout=1)

    assert result.task == "task1"
    assert result.tool_call_id == f"subagent_{task_id}"
    assert result.result == "subagent done"
    assert task_id not in manager.list_subagents()


@pytest.mark.asyncio
async def test_subagent_without_llm_writes_result_to_channel():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=None)
    channel = manager.get_channel(task_id)

    result = await channel.get_result(timeout=1)

    assert result.task == "task1"
    assert "LLM not configured" in result.result


@pytest.mark.asyncio
async def test_subagent_llm_exception_writes_error_to_channel():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=FailingLLM())
    channel = manager.get_channel(task_id)

    result = await channel.get_result(timeout=1)

    assert result.task == "task1"
    assert "[Error] llm failed" in result.result

@pytest.mark.asyncio
async def test_cancel_subagent():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="long task", tools=[], model="gpt-4o-mini", llm=SlowLLM())
    cancelled = await manager.cancel(task_id)
    assert cancelled is True
    assert task_id not in manager.list_subagents()

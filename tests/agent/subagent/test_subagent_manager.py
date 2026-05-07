# tests/Agent/subagent/test_manager.py
import pytest
import asyncio
from unittest.mock import AsyncMock
from agent.subagent.manager import SubAgentManager

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
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=None)
    assert task_id in manager.list_subagents()

@pytest.mark.asyncio
async def test_cancel_subagent():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="long task", tools=[], model="gpt-4o-mini", llm=None)
    cancelled = await manager.cancel(task_id)
    assert cancelled is True
    assert task_id not in manager.list_subagents()
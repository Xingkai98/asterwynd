# tests/agent/subagent/test_protocol.py
import pytest
import asyncio
from agent.subagent.protocol import ParentChannel

def test_parent_channel_put_get():
    channel = ParentChannel(parent_id="p1", subagent_id="s1")
    channel.put_result("task done", "c1")
    result = channel.get_result_nowait()
    assert result.task == "task done"
    assert result.subagent_id == "s1"

@pytest.mark.asyncio
async def test_parent_channel_timeout():
    channel = ParentChannel(parent_id="p1", subagent_id="s1")
    with pytest.raises(asyncio.TimeoutError):
        await channel.get_result(timeout=0.1)
import asyncio

import pytest

from agent.background import BackgroundTaskManager
from agent.tools.builtin.tasks import TaskOutputTool, TaskStopTool
from agent.tools.sandbox import SandboxExecutor


@pytest.fixture
def sandbox():
    return SandboxExecutor()


@pytest.fixture
def manager(sandbox):
    return BackgroundTaskManager(sandbox=sandbox)


async def _get_task_cb(manager, task_id, block, timeout):
    """GetTaskCb 实现。"""
    entry = manager.get_task_output(task_id)
    if entry is None:
        return f"Error: Unknown task {task_id}"

    if not block or entry["status"] != "running":
        return _format_output(task_id, entry)

    # 阻塞轮询
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        await asyncio.sleep(0.1)
        entry = manager.get_task_output(task_id)
        if entry is None or entry["status"] != "running":
            return _format_output(task_id, entry)
        if asyncio.get_event_loop().time() >= deadline:
            return f"[Task {task_id} timeout] {_format_output(task_id, entry)}"


async def _stop_task_cb(manager, task_id):
    """StopTaskCb 实现。"""
    return await manager.stop(task_id)


def _format_output(task_id, entry):
    return (
        f"[Task {task_id}]\n"
        f"status: {entry['status']}\n"
        f"exit_code: {entry.get('exit_code')}\n"
        f"stdout: {entry.get('stdout', '')}"
    )


@pytest.mark.asyncio
async def test_task_output_block_waits_for_completion(manager):
    task_id = await manager.start(
        cmd="sleep 0.3 && echo done",
        tool_call_id="tc_block",
        cwd="/tmp",
        timeout=None,
    )
    tool = TaskOutputTool(get_task_cb=lambda tid, blk, to: _get_task_cb(manager, tid, blk, to))
    result = await tool.execute(task_id=task_id, block=True, timeout=5.0)
    assert "done" in result
    assert "completed" in result


@pytest.mark.asyncio
async def test_task_output_nonblocking(manager):
    task_id = await manager.start(
        cmd="sleep 5",
        tool_call_id="tc_nonblock",
        cwd="/tmp",
        timeout=None,
    )
    tool = TaskOutputTool(get_task_cb=lambda tid, blk, to: _get_task_cb(manager, tid, blk, to))
    result = await tool.execute(task_id=task_id, block=False)
    assert "running" in result.lower()

    await manager.stop(task_id)


@pytest.mark.asyncio
async def test_task_output_unknown_task(manager):
    tool = TaskOutputTool(get_task_cb=lambda tid, blk, to: _get_task_cb(manager, tid, blk, to))
    result = await tool.execute(task_id="nonexistent", block=False)
    assert "Unknown" in result or "not found" in result.lower()


@pytest.mark.asyncio
async def test_task_stop_terminates_running_task(manager):
    task_id = await manager.start(
        cmd="sleep 60",
        tool_call_id="tc_stop",
        cwd="/tmp",
        timeout=None,
    )
    tool = TaskStopTool(stop_task_cb=lambda tid: _stop_task_cb(manager, tid))
    result = await tool.execute(task_id=task_id)
    assert "stopped" in result.lower() or "killed" in result.lower()

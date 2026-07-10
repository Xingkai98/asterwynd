import asyncio

import pytest

from agent.background import BackgroundTaskManager
from agent.tools.sandbox import SandboxExecutor


@pytest.fixture
def sandbox():
    return SandboxExecutor()


@pytest.fixture
def manager(sandbox):
    return BackgroundTaskManager(sandbox=sandbox)


@pytest.mark.asyncio
async def test_start_and_check_completed(manager):
    task_id = await manager.start(
        cmd="echo hello",
        tool_call_id="tc_001",
        cwd="/tmp",
        timeout=None,
    )
    assert task_id.startswith("bg_")

    # 给 monitor task 时间完成
    await asyncio.sleep(0.3)

    completed = manager.check_completed()
    assert len(completed) == 1
    task = completed[0]
    assert task["status"] == "completed"
    assert task["tool_call_id"] == "tc_001"
    assert "hello" in task["stdout"]


@pytest.mark.asyncio
async def test_task_failed_status(manager):
    task_id = await manager.start(
        cmd="exit 1",
        tool_call_id="tc_002",
        cwd="/tmp",
        timeout=None,
    )
    await asyncio.sleep(0.3)
    completed = manager.check_completed()
    assert completed[0]["status"] == "failed"
    assert completed[0]["exit_code"] == 1


@pytest.mark.asyncio
async def test_task_timeout(manager):
    task_id = await manager.start(
        cmd="echo starting && sleep 30",
        tool_call_id="tc_003",
        cwd="/tmp",
        timeout=0.3,
    )
    await asyncio.sleep(1.0)
    completed = manager.check_completed()
    assert completed[0]["status"] == "timeout"
    assert completed[0]["output_truncated"] is False


@pytest.mark.asyncio
async def test_task_stop(manager):
    task_id = await manager.start(
        cmd="sleep 60",
        tool_call_id="tc_004",
        cwd="/tmp",
        timeout=None,
    )
    result = await manager.stop(task_id)
    assert task_id in result
    assert result[task_id]["status"] == "killed"


@pytest.mark.asyncio
async def test_check_completed_dedup(manager):
    task_id = await manager.start(
        cmd="echo done",
        tool_call_id="tc_005",
        cwd="/tmp",
        timeout=None,
    )
    await asyncio.sleep(0.3)

    first = manager.check_completed()
    assert len(first) == 1

    second = manager.check_completed()
    assert len(second) == 0


@pytest.mark.asyncio
async def test_cleanup_terminates_running_tasks(manager):
    task_id = await manager.start(
        cmd="sleep 30",
        tool_call_id="tc_006",
        cwd="/tmp",
        timeout=None,
    )
    await asyncio.sleep(0.3)
    remaining = manager.cleanup()
    assert task_id in remaining
    assert remaining[task_id]["status"] in ("killed", "orphaned")


@pytest.mark.asyncio
async def test_multiple_tasks(manager):
    ids = []
    for i in range(3):
        task_id = await manager.start(
            cmd=f"echo task_{i}",
            tool_call_id=f"tc_multi_{i}",
            cwd="/tmp",
            timeout=None,
        )
        ids.append(task_id)

    await asyncio.sleep(0.5)
    completed = manager.check_completed()
    assert len(completed) == 3
    stdouts = {t["stdout"] for t in completed}
    for i in range(3):
        assert any(f"task_{i}" in s for s in stdouts)


@pytest.mark.asyncio
async def test_task_output_truncated(manager):
    """大输出应触发 output_truncated 标志。"""
    task_id = await manager.start(
        cmd="python3 -c 'print(\"X\" * 100000)'",
        tool_call_id="tc_007",
        cwd="/tmp",
        timeout=None,
    )
    await asyncio.sleep(0.5)
    completed = manager.check_completed()
    assert completed[0]["output_truncated"]

from collections.abc import Awaitable, Callable

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION, COMMAND_EXECUTE_PERMISSION

GetTaskCb = Callable[[str], Awaitable[str]]
StopTaskCb = Callable[[str], Awaitable[str]]


@tool_parameters(
    name="TaskOutput",
    description="获取后台任务的输出和状态。block=True 时等待直到任务完成或超时。",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "后台任务的 ID（由 Bash run_in_background=True 返回）"},
            "block": {
                "type": "boolean",
                "description": "设为 True 时等待直到任务完成（默认 True）",
                "default": True,
            },
            "timeout": {
                "type": "number",
                "description": "等待超时时间（秒），默认 30.0",
                "default": 30.0,
            },
        },
        "required": ["task_id"],
    },
)
class TaskOutputTool(Tool):
    read_only = True
    parallelizable = False
    permission = WORKSPACE_READ_PERMISSION

    def __init__(self, get_task_cb: GetTaskCb | None = None):
        self._get_task_cb = get_task_cb

    async def execute(
        self,
        task_id: str,
        block: bool = True,
        timeout: float = 30.0,
        **kwargs,
    ) -> str:
        if self._get_task_cb is None:
            return "Error: Task management is not available (no manager configured)."

        return await self._get_task_cb(task_id, block, timeout)


@tool_parameters(
    name="TaskStop",
    description="终止正在运行的后台任务。返回最终输出。",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "要终止的后台任务 ID"},
        },
        "required": ["task_id"],
    },
)
class TaskStopTool(Tool):
    read_only = False
    dangerous = True
    parallelizable = False
    permission = COMMAND_EXECUTE_PERMISSION

    def __init__(self, stop_task_cb: StopTaskCb | None = None):
        self._stop_task_cb = stop_task_cb

    async def execute(self, task_id: str, **kwargs) -> str:
        if self._stop_task_cb is None:
            return "Error: Task management is not available (no manager configured)."

        result = await self._stop_task_cb(task_id)
        if isinstance(result, dict):
            task_status = result.get(task_id, result)
            if isinstance(task_status, dict):
                return (
                    f"[Task {task_id} stopped]\n"
                    f"status: {task_status.get('status', 'unknown')}\n"
                    f"stdout: {task_status.get('stdout', '')}"
                )
        return str(result)

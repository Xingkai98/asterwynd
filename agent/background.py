import asyncio
import os
import signal
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from agent.tools.sandbox import BackgroundProcessHandle, SandboxExecutor

current_tool_call_id: ContextVar[str] = ContextVar("current_tool_call_id", default="")

MAX_OUTPUT_BYTES = 64 * 1024


@dataclass
class _TaskEntry:
    handle: BackgroundProcessHandle
    tool_call_id: str
    command: str
    started_at: float
    timeout: float | None
    status: str = "running"  # running|completed|failed|timeout|killed|orphaned
    exit_code: int | None = None
    stdout: str = ""
    output_truncated: bool = False
    reported: bool = False
    _monitor_task: asyncio.Task | None = field(default=None, repr=False)


class BackgroundTaskManager:
    def __init__(
        self,
        sandbox: SandboxExecutor,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        cleanup_timeout: float = 5.0,
    ):
        self._sandbox = sandbox
        self.max_output_bytes = max_output_bytes
        self.cleanup_timeout = cleanup_timeout
        self._tasks: dict[str, _TaskEntry] = {}
        self._counter = 0

    async def start(
        self,
        cmd: str,
        tool_call_id: str,
        cwd: str,
        timeout: float | None = None,
    ) -> str:
        task_id = self._new_task_id()
        handle = await self._sandbox.run_background(cmd, cwd=cwd)
        entry = _TaskEntry(
            handle=handle,
            tool_call_id=tool_call_id,
            command=cmd,
            started_at=time.time(),
            timeout=timeout,
        )
        entry._monitor_task = asyncio.create_task(self._monitor(task_id, entry))
        self._tasks[task_id] = entry
        return task_id

    def check_completed(self) -> list[dict]:
        results = []
        for task_id, entry in self._tasks.items():
            if entry.status != "running" and not entry.reported:
                entry.reported = True
                results.append(self._task_to_dict(task_id, entry))
        return results

    def get_task_output(self, task_id: str) -> dict | None:
        entry = self._tasks.get(task_id)
        if entry is None:
            return None
        if entry.status != "running":
            entry.reported = True
        return self._task_to_dict(task_id, entry)

    async def stop(self, task_id: str) -> dict:
        entry = self._tasks.get(task_id)
        if entry is None or entry.status != "running":
            return {task_id: self._task_to_dict(task_id, entry) if entry else {"status": "not_found"}}

        await entry.handle.terminate()
        try:
            await asyncio.wait_for(entry.handle.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            await entry.handle.kill()
            try:
                await asyncio.wait_for(entry.handle.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

        entry.status = "killed"
        entry.reported = True
        return {task_id: self._task_to_dict(task_id, entry)}

    def cleanup(self) -> dict[str, dict]:
        remaining = {}
        for task_id, entry in list(self._tasks.items()):
            if entry._monitor_task and not entry._monitor_task.done():
                entry._monitor_task.cancel()
            self._force_kill_sync(entry)
            if entry.status == "running":
                entry.status = "killed"
            remaining[task_id] = self._task_to_dict(task_id, entry)
        return remaining

    def _new_task_id(self) -> str:
        self._counter += 1
        return f"bg_{self._counter:04d}"

    async def _monitor(self, task_id: str, entry: _TaskEntry):
        drain_task: asyncio.Task | None = None

        try:
            # 并发 drain，边运行边读输出
            drain_task = asyncio.create_task(self._drain_output(entry))

            if entry.timeout is not None:
                await asyncio.wait_for(entry.handle.wait(), timeout=entry.timeout)
            else:
                await entry.handle.wait()
        except asyncio.TimeoutError:
            entry.status = "timeout"
            try:
                await entry.handle.kill()
                await entry.handle.wait()
            except Exception:
                pass
        except asyncio.CancelledError:
            if drain_task:
                drain_task.cancel()
            return
        except Exception:
            if entry.status == "running":
                entry.status = "orphaned"
            if drain_task:
                drain_task.cancel()
            return

        # drain 完成后获取 exit code
        if drain_task:
            try:
                await drain_task
            except asyncio.CancelledError:
                pass

        if entry.status == "running":
            entry.exit_code = await entry.handle.poll()
            entry.status = "completed" if entry.exit_code == 0 else "failed"

    async def _drain_output(self, entry: _TaskEntry):
        while True:
            chunk = await entry.handle.read_chunk(4096)
            if not chunk:
                break
            remaining = self.max_output_bytes - len(entry.stdout)
            if remaining <= 0:
                entry.output_truncated = True
                continue
            entry.stdout += chunk.decode(errors="replace")[:remaining]
            if len(entry.stdout) >= self.max_output_bytes:
                entry.output_truncated = True

    def _force_kill_sync(self, entry: _TaskEntry):
        """同步强制终止（cleanup 路径使用，不依赖 event loop）。"""
        entry.handle.force_kill_sync(wait_timeout=self.cleanup_timeout)

    def _task_to_dict(self, task_id: str, entry: _TaskEntry) -> dict:
        return {
            "task_id": task_id,
            "tool_call_id": entry.tool_call_id,
            "command": entry.command,
            "status": entry.status,
            "exit_code": entry.exit_code,
            "stdout": entry.stdout,
            "output_truncated": entry.output_truncated,
        }

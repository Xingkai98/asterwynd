# agent/subagent/protocol.py
import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class SubAgentResult:
    subagent_id: str
    task: str
    result: str
    tool_call_id: str

class ParentChannel:
    def __init__(self, parent_id: str, subagent_id: str):
        self.parent_id = parent_id
        self.subagent_id = subagent_id
        self._queue: asyncio.Queue[SubAgentResult] = asyncio.Queue()

    def put_result(self, task: str, tool_call_id: str, result: str = "") -> None:
        self._queue.put_nowait(
            SubAgentResult(
                subagent_id=self.subagent_id,
                task=task,
                result=result,
                tool_call_id=tool_call_id,
            )
        )

    def get_result_nowait(self) -> SubAgentResult:
        return self._queue.get_nowait()

    async def get_result(self, timeout: Optional[float] = None) -> SubAgentResult:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)
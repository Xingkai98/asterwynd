# agent/subagent/manager.py
import asyncio
import uuid
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message
    from agent.subagent.protocol import ParentChannel

class SubAgentManager:
    def __init__(self):
        self._subagents: dict[str, asyncio.Task] = {}
        self._channels: dict[str, "ParentChannel"] = {}

    async def delegate(
        self,
        task: str,
        tools: list,
        model: str,
        llm: Optional["LLM"],
    ) -> str:
        subagent_id = uuid.uuid4().hex[:8]
        from agent.subagent.protocol import ParentChannel
        channel = ParentChannel(parent_id="main", subagent_id=subagent_id)
        self._channels[subagent_id] = channel

        t = asyncio.create_task(
            self._run_subagent(subagent_id, task, tools, model, llm, channel)
        )
        self._subagents[subagent_id] = t
        return subagent_id

    async def _run_subagent(
        self,
        subagent_id: str,
        task: str,
        tools: list,
        model: str,
        llm: Optional["LLM"],
        channel: "ParentChannel",
    ):
        try:
            if llm is None:
                result = f"[SubAgent {subagent_id}] LLM not configured"
            else:
                from agent.message import Message
                messages = [
                    Message(role="system", content=f"你是一个子 agent，任务：{task}"),
                    Message(role="user", content=task),
                ]
                response = await llm.chat(messages, model=model)
                result = response.content or "[无内容返回]"

            channel.put_result(
                task=task,
                tool_call_id=f"subagent_{subagent_id}",
                result=result,
            )
        except Exception as e:
            channel.put_result(
                task=task,
                tool_call_id=f"subagent_{subagent_id}",
                result=f"[Error] {e}",
            )
        finally:
            self._subagents.pop(subagent_id, None)

    def get_channel(self, subagent_id: str) -> Optional["ParentChannel"]:
        return self._channels.get(subagent_id)

    def list_subagents(self) -> list[str]:
        return list(self._subagents.keys())

    async def cancel(self, subagent_id: str) -> bool:
        task = self._subagents.pop(subagent_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

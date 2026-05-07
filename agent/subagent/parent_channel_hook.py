# agent/subagent/parent_channel_hook.py
"""
ParentChannelHook：把子 agent 结果注入父 agent 当前轮次。
"""
import asyncio
from typing import TYPE_CHECKING
from agent.hooks.manager import Hook

if TYPE_CHECKING:
    from agent.message import Message
    from agent.result import RunResult
    from agent.llm import LLMResponse
    from agent.tools.base import ToolCall
    from agent.subagent.protocol import SubAgentResult, ParentChannel

class ParentChannelHook(Hook):
    def __init__(
        self,
        subagent_id: str,
        channel: "ParentChannel",
        parent_messages: list["Message"],
    ):
        self.subagent_id = subagent_id
        self.channel = channel
        self.parent_messages = parent_messages

    async def after_tool_execute(self, tool_call: "ToolCall", result: str) -> None:
        try:
            sub_result: "SubAgentResult" = await self.channel.get_result(timeout=0.01)
            from agent.message import Message
            self.parent_messages.append(
                Message(
                    role="tool",
                    content=sub_result.result,
                    tool_call_id=sub_result.tool_call_id,
                )
            )
        except asyncio.TimeoutError:
            pass

    async def before_iteration(self, iteration: int, messages: list["Message"]) -> None: pass
    async def after_llm_call(self, response: "LLMResponse") -> None: pass
    async def before_tool_execute(self, tool_call: "ToolCall") -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass
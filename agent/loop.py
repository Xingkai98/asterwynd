# agent/loop.py
import asyncio
import logging
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from agent.message import Message, tool_result_message
from agent.result import RunResult, StopReason, ToolCallMade
from agent.tools.base import ToolCall
from agent.llm import LLMResponse, ToolCallDelta
from agent.hooks.manager import HookManager
from agent.tools.registry import ToolRegistry
from agent.memory.manager import MemoryManager
from agent.subagent.manager import SubAgentManager

if TYPE_CHECKING:
    from agent.llm import LLM

logger = logging.getLogger("myagent.loop")

class AgentLoop:
    def __init__(
        self,
        llm: "LLM",
        tool_registry: ToolRegistry,
        hooks: Optional[HookManager] = None,
        memory: Optional[MemoryManager] = None,
        subagent_manager: Optional[SubAgentManager] = None,
        max_iterations: int = 20,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.hooks = hooks or HookManager()
        self.memory = memory or MemoryManager()
        self.subagent_manager = subagent_manager or SubAgentManager()
        self.max_iterations = max_iterations

    async def run(
        self,
        messages: list[Message],
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    ) -> RunResult:
        tool_calls_made: list[ToolCallMade] = []

        for iteration in range(self.max_iterations):
            await self.hooks.before_iteration(iteration, messages)

            tool_schemas = self.tool_registry.get_all_schemas()

            response = await self.llm.chat(
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
            )
            await self.hooks.after_llm_call(response)

            if on_event:
                await on_event("llm_response", {
                    "content": response.content,
                    "stop_reason": response.stop_reason,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                })

            if not response.tool_calls:
                # Bug 2: LLM 被 max_tokens 截断时，追加续接消息并继续迭代
                if response.stop_reason == "max_tokens":
                    if response.content:
                        messages.append(Message(role="assistant", content=response.content))
                    messages.append(Message(role="user", content="Please continue from where you left off."))
                    continue

                await self.hooks.on_completion(RunResult(
                    content=response.content or "",
                    stop_reason=StopReason.END_TURN,
                    tool_calls_made=tool_calls_made,
                ))
                if on_event:
                    await on_event("done", {
                        "content": response.content or "",
                        "stop_reason": "end_turn",
                    })
                return RunResult(
                    content=response.content or "",
                    stop_reason=StopReason.END_TURN,
                    tool_calls_made=tool_calls_made,
                )

            # Bug 3: assistant 消息只追加一次（移到 for 循环之外）
            messages.append(Message(role="assistant", content="", tool_calls=list(response.tool_calls), reasoning_content=response.reasoning_content))

            for delta in response.tool_calls:
                tool_call = ToolCall(
                    id=delta.id,
                    name=delta.name,
                    arguments=self._parse_arguments(delta.arguments),
                )

                await self.hooks.before_tool_execute(tool_call)

                try:
                    result = await self.tool_registry.execute(tool_call)
                except Exception as e:
                    logger.error(f"[AgentLoop] tool {tool_call.name} raised: {e}")
                    await self.hooks.on_error(e)
                    result = f"[Error: {e}]"

                await self.hooks.after_tool_execute(tool_call, result)

                if on_event:
                    await on_event("tool_call", {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    })
                    await on_event("tool_result", {
                        "name": tool_call.name,
                        "result": result,
                    })

                messages.append(tool_result_message(tool_call.id, result))
                tool_calls_made.append(ToolCallMade(
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                    result=result,
                ))

            self.memory.compact_if_needed()
            if on_event:
                await on_event("memory_compaction", {
                    "total_messages": len(messages),
                })

        logger.warning(f"[AgentLoop] 达到最大迭代次数 {self.max_iterations}")
        await self.hooks.on_completion(RunResult(
            content=messages[-1].content if messages else "",
            stop_reason=StopReason.MAX_ITERATIONS,
            tool_calls_made=tool_calls_made,
        ))
        if on_event:
            await on_event("done", {
                "content": messages[-1].content if messages else "",
                "stop_reason": "max_iterations",
            })
        return RunResult(
            content=messages[-1].content if messages else "",
            stop_reason=StopReason.MAX_ITERATIONS,
            tool_calls_made=tool_calls_made,
        )

    def _parse_arguments(self, arguments: str) -> dict:
        import json
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {}
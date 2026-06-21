# agent/loop.py
import asyncio
import logging
import time
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
    from agent.trace_recorder import TraceRecorder

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
        self.memory = memory or MemoryManager(llm=llm)
        self.subagent_manager = subagent_manager or SubAgentManager()
        self.max_iterations = max_iterations

    async def run(
        self,
        messages: list[Message],
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
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
            if trace_recorder:
                trace_recorder.record_iteration(
                    iteration,
                    assistant_preview=response.content or "",
                    tool_calls=[
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                )

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
                messages.append(Message(role="assistant", content=response.content or "", reasoning_content=response.reasoning_content))
                return RunResult(
                    content=response.content or "",
                    stop_reason=StopReason.END_TURN,
                    tool_calls_made=tool_calls_made,
                )

            # Bug 3: assistant 消息只追加一次（移到 for 循环之外）
            messages.append(Message(role="assistant", content=response.content or "", tool_calls=list(response.tool_calls), reasoning_content=response.reasoning_content))

            for delta in response.tool_calls:
                try:
                    arguments = self._parse_arguments(delta.arguments)
                except ValueError as e:
                    tool_call = ToolCall(id=delta.id, name=delta.name, arguments={})
                    logger.error(f"[AgentLoop] invalid arguments for tool {delta.name}: {e}")
                    await self.hooks.on_error(e)
                    result = f"[Error: {e}]"
                    if trace_recorder:
                        trace_recorder.record_tool_call(tool_call.name, tool_call.arguments)
                        trace_recorder.record_tool_result(
                            tool_call.name,
                            "error",
                            0,
                            result,
                        )

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
                    continue

                tool_call = ToolCall(
                    id=delta.id,
                    name=delta.name,
                    arguments=arguments,
                )

                await self.hooks.before_tool_execute(tool_call)
                if trace_recorder:
                    trace_recorder.record_tool_call(tool_call.name, tool_call.arguments)

                tool_start = time.time()
                try:
                    result = await self.tool_registry.execute(tool_call)
                except Exception as e:
                    logger.error(f"[AgentLoop] tool {tool_call.name} raised: {e}")
                    await self.hooks.on_error(e)
                    result = f"[Error: {e}]"
                tool_duration_ms = (time.time() - tool_start) * 1000

                await self.hooks.after_tool_execute(tool_call, result)
                if trace_recorder:
                    status = "error" if result.startswith("[Error") or result.startswith("Error") else "ok"
                    trace_recorder.record_tool_result(
                        tool_call.name,
                        status,
                        tool_duration_ms,
                        result,
                    )
                    if tool_call.name == "Edit":
                        path = str(tool_call.arguments.get("path", ""))
                        trace_recorder.record_edit(path, status, result)

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

            compacted = await self.memory.compact_if_needed(messages)
            if compacted and on_event:
                await on_event("memory_compaction", {
                    "total_messages": len(messages),
                })

        logger.warning(f"[AgentLoop] 达到最大迭代次数 {self.max_iterations}")
        final_content = self._last_assistant_content(messages)
        result = RunResult(
            content=final_content,
            stop_reason=StopReason.MAX_ITERATIONS,
            tool_calls_made=tool_calls_made,
        )
        await self.hooks.on_completion(result)
        if on_event:
            await on_event("done", {
                "content": final_content,
                "stop_reason": "max_iterations",
            })
        return result

    def _parse_arguments(self, arguments: str) -> dict:
        import json
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON tool arguments: {e.msg}") from e
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments must be a JSON object")
        return parsed

    def _last_assistant_content(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "assistant" and message.content:
                return message.content
        return ""

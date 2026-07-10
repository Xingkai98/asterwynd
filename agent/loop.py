# agent/loop.py
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalHandler,
    ApprovalResponse,
    FailClosedApprovalHandler,
    build_approval_request,
    redact_value,
)
from agent.message import Message, system_message, tool_result_message
from agent.result import RunResult, StopReason, ToolCallMade
from agent.tools.base import ToolCall
from agent.llm import LLMResponse, ToolCallDelta
from agent.hooks.manager import HookManager
from agent.tools.registry import ToolRegistry
from agent.memory.manager import MemoryManager
from agent.memory.persistent import PersistentMemory
from agent.planning import PlanStatus, PlanningManager
from agent.subagent.manager import SubAgentManager
from agent.run_config import AgentMode, AgentRunConfig, AgentRuntimeState
from agent.run_identity import new_run_id
from agent.tools.builtin.plan import ExitPlanModeTool, UpdatePlanTool
from agent.tools.builtin.subagents import (
    CancelSubagentRunTool,
    CreateSubagentTool,
    GetSubagentRunTool,
    InspectSubagentTranscriptTool,
    ListSubagentsTool,
    RunSubagentTool,
)
from agent.tools.builtin.activate_skill import ActivateSkillTool
from agent.tools.builtin.tasks import TaskOutputTool, TaskStopTool
from agent.tools.builtin.todo import TodoWriteTool
from agent.hooks.builtin.retry import RetryHook
from agent.planning import PlanItem
from agent.skills.runtime import SkillRuntime
from agent.tool_result_display import ToolResultDisplayConfig, summarize_tool_result
from agent.background import BackgroundTaskManager, current_tool_call_id
from agent.session import CURRENT_SCHEMA_VERSION, SessionSnapshot, SessionStore

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.mcp.manager import McpManager
    from agent.trace_recorder import TraceRecorder

logger = logging.getLogger("asterwynd.loop")

class AgentLoop:
    def __init__(
        self,
        llm: "LLM",
        tool_registry: ToolRegistry,
        hooks: Optional[HookManager] = None,
        memory: Optional[MemoryManager] = None,
        persistent_memory: PersistentMemory | None = None,
        planning_manager: Optional[PlanningManager] = None,
        subagent_manager: Optional[SubAgentManager] = None,
        expose_subagent_tools: bool = False,
        max_iterations: int = 20,
        run_config: AgentRunConfig | None = None,
        tool_result_display: ToolResultDisplayConfig | None = None,
        skill_runtime: SkillRuntime | None = None,
        approval_handler: ApprovalHandler | None = None,
        mcp_manager: "McpManager | None" = None,
        background_manager: BackgroundTaskManager | None = None,
        session_store: SessionStore | None = None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.hooks = hooks or HookManager()
        self.memory = memory or MemoryManager(llm=llm)
        self.persistent_memory = persistent_memory
        self._planning = planning_manager or PlanningManager()
        self.subagent_manager = subagent_manager or SubAgentManager()
        self.subagent_manager.configure_runtime(
            llm=llm,
            parent_mode_provider=lambda: self.runtime_state.current_mode,
        )
        self.max_iterations = max_iterations
        self.run_config = run_config or AgentRunConfig()
        policy_state = getattr(self.tool_registry.mode_policy, "runtime_state", None)
        self.runtime_state = policy_state or AgentRuntimeState(self.run_config.mode)
        self.tool_registry.mode_policy.runtime_state = self.runtime_state
        self.tool_result_display = tool_result_display or ToolResultDisplayConfig()
        self.skill_runtime = skill_runtime
        self.approval_handler = approval_handler or FailClosedApprovalHandler()
        self.mcp_manager = mcp_manager
        self.background_manager = background_manager
        self.session_store = session_store
        self._active_on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None
        self._active_trace_recorder: Optional["TraceRecorder"] = None
        self._plan_document: dict | None = None
        self._plan_document_final = False
        self._plan_tools_registered = False
        self._subagent_tools_registered = False
        self._todo_tool_registered = False
        self._bg_tools_registered = False
        self._execution_todos: list[PlanItem] = []
        self._todo_next_id = 1
        self._iteration = 0
        self._retry = RetryHook(max_retries=3, base_delay=1.0)
        if self.runtime_state.current_mode is AgentMode.PLAN:
            self._ensure_plan_tools_registered()
        if expose_subagent_tools:
            self._ensure_subagent_tools_registered()
        self._ensure_todo_tool_registered()
        self._ensure_background_task_tools_registered()
        if self.skill_runtime is not None:
            self.tool_registry.register(ActivateSkillTool(self.skill_runtime))

    @property
    def planning_state(self) -> dict:
        return self._planning.snapshot()

    @property
    def plan_document(self) -> dict | None:
        return self._plan_document

    @property
    def plan_document_final(self) -> bool:
        return self._plan_document_final

    async def set_mode(
        self,
        mode: str | AgentMode,
        *,
        source: str,
        reason: str | None = None,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        transition = self.runtime_state.set_mode(mode, source=source, reason=reason)
        if self.runtime_state.current_mode is AgentMode.PLAN:
            self._ensure_plan_tools_registered()
        if session_id is not None:
            transition["session_id"] = session_id
        trace_sink = trace_recorder or self._active_trace_recorder
        if trace_sink and trace_sink.session_id is not None and "session_id" not in transition:
            transition["session_id"] = trace_sink.session_id
        if run_id is not None:
            transition["run_id"] = run_id
        elif trace_sink and trace_sink.run_id is not None:
            transition["run_id"] = trace_sink.run_id
        event_sink = on_event or self._active_on_event
        if trace_sink:
            trace_sink.record_mode_changed(transition)
        if event_sink:
            await event_sink("mode_changed", transition)
        return transition

    async def set_plan(
        self,
        contents: list[str],
        *,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> dict:
        snapshot = self._planning.set_plan(contents)
        await self._publish_planning_state(snapshot, on_event, trace_recorder)
        return snapshot

    async def update_plan_item(
        self,
        item_id: str,
        status: PlanStatus,
        note: str | None = None,
        *,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> dict:
        snapshot = self._planning.update_item(item_id, status, note=note)
        await self._publish_planning_state(snapshot, on_event, trace_recorder)
        return snapshot

    async def update_plan_document(
        self,
        title: str,
        plan_markdown: str,
        steps: list[str],
        *,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> dict:
        snapshot = await self.set_plan(
            steps,
            on_event=on_event,
            trace_recorder=trace_recorder,
        )
        document = {
            "title": title,
            "markdown": plan_markdown,
            "steps": [item["content"] for item in snapshot["items"]],
            "planning_state": snapshot,
            "status": "draft",
        }
        self._plan_document = document
        self._plan_document_final = False
        await self._publish_plan_document(
            "plan_document_updated",
            document,
            on_event,
            trace_recorder,
        )
        return document

    async def submit_plan_document(
        self,
        title: str,
        plan_markdown: str,
        steps: list[str],
        *,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> dict:
        snapshot = await self.set_plan(
            steps,
            on_event=on_event,
            trace_recorder=trace_recorder,
        )
        document = {
            "title": title,
            "markdown": plan_markdown,
            "steps": [item["content"] for item in snapshot["items"]],
            "planning_state": snapshot,
            "status": "submitted",
        }
        self._plan_document = document
        self._plan_document_final = True
        await self._publish_plan_document(
            "plan_document_submitted",
            document,
            on_event,
            trace_recorder,
        )
        return document

    async def _publish_planning_state(
        self,
        snapshot: dict,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> None:
        trace_sink = trace_recorder or self._active_trace_recorder
        event_sink = on_event or self._active_on_event
        if trace_sink:
            trace_sink.record_planning_state(snapshot)
        if event_sink:
            await event_sink("planning_state_updated", snapshot)

    async def _publish_plan_document(
        self,
        event_type: str,
        document: dict,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
    ) -> None:
        trace_sink = trace_recorder or self._active_trace_recorder
        event_sink = on_event or self._active_on_event
        if trace_sink:
            trace_sink.record_plan_document(event_type, document)
        if event_sink:
            await event_sink(event_type, document)

    def _ensure_plan_tools_registered(self) -> None:
        if self._plan_tools_registered:
            return
        self.tool_registry.register(UpdatePlanTool(self.update_plan_document))
        self.tool_registry.register(ExitPlanModeTool(self.submit_plan_document))
        self._plan_tools_registered = True

    def _ensure_subagent_tools_registered(self) -> None:
        if self._subagent_tools_registered:
            return
        self.tool_registry.register(CreateSubagentTool(self.subagent_manager))
        self.tool_registry.register(RunSubagentTool(self.subagent_manager))
        self.tool_registry.register(ListSubagentsTool(self.subagent_manager))
        self.tool_registry.register(GetSubagentRunTool(self.subagent_manager))
        self.tool_registry.register(CancelSubagentRunTool(self.subagent_manager))
        self.tool_registry.register(InspectSubagentTranscriptTool(self.subagent_manager))
        self._subagent_tools_registered = True

    def _ensure_todo_tool_registered(self) -> None:
        if self._todo_tool_registered:
            return
        self.tool_registry.register(TodoWriteTool(
            create_cb=self._todo_create,
            update_cb=self._todo_update,
            list_cb=self._todo_list,
        ))
        self._todo_tool_registered = True

    def _todo_create(self, content: str) -> PlanItem:
        item = PlanItem(id=self._new_todo_id(), content=content, status="pending")
        self._execution_todos.append(item)
        return item

    def _todo_update(self, item_id: str, status: str, note: str | None) -> PlanItem:
        for item in self._execution_todos:
            if item.id == item_id:
                item.status = status  # type: ignore[assignment]
                item.note = note
                return item
        raise ValueError(f"unknown todo item: {item_id}")

    def _todo_list(self, status_filter: str | None) -> list[PlanItem]:
        if status_filter is None:
            return list(self._execution_todos)
        return [item for item in self._execution_todos if item.status == status_filter]

    def _new_todo_id(self) -> str:
        item_id = f"todo-{self._todo_next_id}"
        self._todo_next_id += 1
        return item_id

    def _sync_todo_next_id(self) -> None:
        max_id = 0
        for item in self._execution_todos:
            if item.id.startswith("todo-"):
                try:
                    n = int(item.id.split("-", 1)[1])
                    if n > max_id:
                        max_id = n
                except ValueError:
                    pass
        self._todo_next_id = max_id + 1

    def _ensure_background_task_tools_registered(self) -> None:
        if self._bg_tools_registered:
            return
        if self.background_manager is None:
            return
        self.tool_registry.register(TaskOutputTool(
            get_task_cb=self._get_task_output,
        ))
        self.tool_registry.register(TaskStopTool(
            stop_task_cb=self._stop_task,
        ))
        try:
            bash_tool = self.tool_registry.get_tool("Bash")
            bash_tool.set_run_in_background_cb(self._run_in_background)
        except KeyError:
            pass
        self._bg_tools_registered = True

    async def _get_task_output(self, task_id: str, block: bool, timeout: float) -> str:
        entry = self.background_manager.get_task_output(task_id)
        if entry is None:
            return f"Error: Unknown task {task_id}"

        if not block or entry["status"] != "running":
            return self._format_task_output(task_id, entry)

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            await asyncio.sleep(0.1)
            entry = self.background_manager.get_task_output(task_id)
            if entry is None or entry["status"] != "running":
                return self._format_task_output(task_id, entry)
            if asyncio.get_event_loop().time() >= deadline:
                return f"[Task {task_id} timeout] {self._format_task_output(task_id, entry)}"

    async def _stop_task(self, task_id: str) -> str:
        result = await self.background_manager.stop(task_id)
        if isinstance(result, dict):
            task_status = result.get(task_id, result)
            if isinstance(task_status, dict):
                return (
                    f"[Task {task_id} stopped]\n"
                    f"status: {task_status.get('status', 'unknown')}\n"
                    f"stdout: {task_status.get('stdout', '')}"
                )
        return str(result)

    async def _run_in_background(self, cmd: str, cwd: str, timeout: float | None, tool_call_id: str) -> str:
        return await self.background_manager.start(
            cmd=cmd,
            tool_call_id=tool_call_id,
            cwd=cwd,
            timeout=timeout,
        )

    @staticmethod
    def _format_task_output(task_id: str, entry: dict) -> str:
        return (
            f"[Task {task_id}]\n"
            f"status: {entry['status']}\n"
            f"exit_code: {entry.get('exit_code')}\n"
            f"stdout: {entry.get('stdout', '')}"
        )

    @property
    def execution_todos(self) -> list[PlanItem]:
        return list(self._execution_todos)

    def _todo_snapshot(self) -> dict:
        items = [item.to_dict() for item in self._execution_todos]
        return {
            "items": items,
            "count": len(items),
        }

    async def run(
        self,
        messages: list[Message],
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
        session_id: str | None = None,
        run_id: str | None = None,
        resume_snapshot: SessionSnapshot | None = None,
    ) -> RunResult:
        resolved_run_id = run_id or new_run_id()
        if trace_recorder:
            trace_recorder.set_run_identity(
                session_id=session_id,
                run_id=resolved_run_id,
            )
        previous_on_event = self._active_on_event
        previous_trace_recorder = self._active_trace_recorder
        self._active_on_event = on_event
        self._active_trace_recorder = trace_recorder
        try:
            return await self._run(
                messages,
                on_event,
                trace_recorder,
                session_id=session_id,
                run_id=resolved_run_id,
                resume_snapshot=resume_snapshot,
            )
        finally:
            if self.background_manager is not None:
                self.background_manager.cleanup()
            if self.session_store is not None and session_id:
                try:
                    self._save_session(messages, session_id, resolved_run_id, resume_snapshot)
                except Exception:
                    logger.warning("Failed to save session", exc_info=True)
            self._active_on_event = previous_on_event
            self._active_trace_recorder = previous_trace_recorder

    async def _run(
        self,
        messages: list[Message],
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        trace_recorder: Optional["TraceRecorder"] = None,
        session_id: str | None = None,
        run_id: str | None = None,
        resume_snapshot: SessionSnapshot | None = None,
    ) -> RunResult:
        tool_calls_made: list[ToolCallMade] = []
        start_iteration = 0

        if resume_snapshot is not None:
            current_system = [m for m in messages if m.role == "system"]
            new_user_input = [m for m in messages if m.role != "system"]

            if resume_snapshot.mode != self.runtime_state.current_mode:
                await self.set_mode(resume_snapshot.mode, source="resume")
            self._execution_todos = list(resume_snapshot.todos)
            self._sync_todo_next_id()
            if self.skill_runtime is not None and resume_snapshot.active_skills:
                self.skill_runtime.restore_skills(resume_snapshot.active_skills)

            conversation = [m for m in resume_snapshot.messages if m.role != "system"]
            messages.clear()
            messages.extend(current_system)
            messages.extend(conversation)
            messages.append(Message(role="user", content="[Session resumed. Continuing from where we left off.]"))
            messages.extend(new_user_input)
            start_iteration = 0

            mode = self.runtime_state.current_mode.value
            logger.info(
                "Agent run resumed mode=%s session_id=%s run_id=%s",
                mode,
                session_id or "",
                run_id or "",
            )
        else:
            mode = self.runtime_state.current_mode.value
            if self.skill_runtime is not None:
                self.skill_runtime.begin_run(self._last_user_content(messages))

            logger.info(
                "Agent run started mode=%s session_id=%s run_id=%s",
                mode,
                session_id or "",
                run_id or "",
            )
            await self.hooks.on_run_started(AgentRunConfig(mode=self.runtime_state.current_mode))
            if trace_recorder:
                trace_recorder.record_run_started(mode)
            if on_event:
                event_data = {"mode": mode, "run_id": run_id}
                if session_id is not None:
                    event_data["session_id"] = session_id
                await on_event("run_started", event_data)

        for iteration in range(start_iteration, self.max_iterations):
            self._iteration = iteration
            await self.hooks.before_iteration(iteration, messages)

            if self.background_manager is not None:
                completed = self.background_manager.check_completed()
                for task in completed:
                    observation = (
                        f"[Background task {task['task_id']} completed]\n"
                        f"Command: {task['command']}\n"
                        f"Status: {task['status']}\n"
                        f"Exit code: {task['exit_code']}\n"
                        f"Output:\n{task['stdout']}"
                    )
                    if task.get("output_truncated"):
                        observation += "\n[output truncated]"
                    messages.append(Message(role="user", content=observation))

            tool_schemas = self.tool_registry.get_all_schemas()

            response, streamed = await self._call_llm(
                messages=self._messages_with_run_context(messages),
                tools=tool_schemas if tool_schemas else None,
                on_event=on_event,
            )
            await self.hooks.after_llm_call(response)
            if trace_recorder:
                trace_recorder.record_iteration(
                    iteration,
                    assistant_preview=response.content or "",
                    tool_calls=[
                        self._observed_tool_call_delta(tc)
                        for tc in response.tool_calls
                    ],
                )

            if on_event:
                llm_event = {
                    "content": response.content,
                    "stop_reason": response.stop_reason,
                    "tool_calls": [
                        self._observed_tool_call_delta(tc)
                        for tc in response.tool_calls
                    ],
                }
                if streamed:
                    llm_event["streamed"] = True
                await on_event("llm_response", llm_event)

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

            # Phase 1: Pre-process tool calls (parse, validate, approve)
            pending: list[dict] = []
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
                            "display": summarize_tool_result(
                                tool_call.name,
                                result,
                                self.tool_result_display,
                            ).to_dict(),
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

                try:
                    tool = self.tool_registry.get_tool(tool_call.name)
                except KeyError:
                    logger.error(f"[AgentLoop] unknown tool: {tool_call.name}")
                    # Add as pre-denied entry — post-processing handles all side effects in order
                    pending.append({
                        "tool_call": tool_call,
                        "observed_tool_call": tool_call,
                        "tool": None,
                        "approval_granted": False,
                        "approval_request_data": None,
                        "pre_denied_result": f"[Error: unknown tool '{tool_call.name}']",
                        "decision": None,
                    })
                    continue

                decision = self.tool_registry.mode_policy.decide_tool(tool)
                observed_tool_call = tool_call
                approval_granted = False
                approval_request_data: dict | None = None
                pre_denied_result: str | None = None
                if decision.requires_approval:
                    approval_request = build_approval_request(
                        tool_call_id=tool_call.id,
                        arguments=tool_call.arguments,
                        decision=decision,
                        mode=self.runtime_state.current_mode,
                        session_id=session_id,
                        run_id=run_id,
                    )
                    approval_request_data = approval_request.to_event_data()
                    observed_tool_call = ToolCall(
                        id=tool_call.id,
                        name=tool_call.name,
                        arguments=approval_request.redacted_args,
                    )
                    if trace_recorder:
                        trace_recorder.record_approval_request(approval_request_data)
                    if on_event:
                        await on_event("approval_request", approval_request_data)
                    try:
                        approval_response = await self.approval_handler.request_approval(
                            approval_request
                        )
                    except Exception as exc:
                        logger.exception("Approval handler failed")
                        approval_response = ApprovalResponse(
                            approval_id=approval_request.approval_id,
                            status=ApprovalDecisionStatus.UNAVAILABLE,
                            reason=f"{type(exc).__name__}: {exc}",
                        )
                    approval_granted = approval_response.approved
                    approval_response_data = {
                        "approval_id": approval_response.approval_id,
                        "tool_name": tool_call.name,
                        "status": approval_response.status.value,
                        "reason": approval_response.reason,
                        "session_id": session_id,
                        "run_id": run_id,
                    }
                    if trace_recorder:
                        trace_recorder.record_approval_response(approval_response_data)
                    if on_event:
                        await on_event("approval_response", approval_response_data)
                    if not approval_granted:
                        if approval_response.status is ApprovalDecisionStatus.DENIED:
                            pre_denied_result = (
                                f"[Approval denied: tool {tool_call.name} was not "
                                f"approved in {self.runtime_state.current_mode.value} "
                                f"mode: {approval_response.reason}]"
                            )
                        else:
                            pre_denied_result = (
                                f"[Approval unavailable: tool {tool_call.name} requires "
                                f"approval in {self.runtime_state.current_mode.value} "
                                f"mode: {approval_response.reason}]"
                            )

                pending.append({
                    "tool_call": tool_call,
                    "observed_tool_call": observed_tool_call,
                    "tool": tool,
                    "approval_granted": approval_granted,
                    "approval_request_data": approval_request_data,
                    "pre_denied_result": pre_denied_result,
                    "decision": decision,
                })

            # Phase 2: Execute with grouping
            executed = await self._execute_tool_calls(pending)

            # Phase 3: Post-process results in original order
            for entry in executed:
                tool_call = entry["tool_call"]
                observed_tool_call = entry["observed_tool_call"]
                result = entry["result"]
                duration_ms = entry["duration_ms"]
                approval_request_data = entry.get("approval_request_data")
                tool = entry["tool"]

                if trace_recorder:
                    trace_recorder.record_tool_call(
                        observed_tool_call.name,
                        observed_tool_call.arguments,
                    )
                    status = (
                        "error"
                        if result.startswith("[Error")
                        or result.startswith("Error")
                        or result.startswith("[Permission denied")
                        else "ok"
                    )
                    trace_recorder.record_tool_result(
                        tool_call.name,
                        status,
                        duration_ms,
                        result,
                    )
                    if tool_call.name == "Edit" and status == "ok":
                        path = str(tool_call.arguments.get("path", ""))
                        trace_recorder.record_edit(path, status, result)

                if on_event:
                    await on_event("tool_call", {
                        "name": observed_tool_call.name,
                        "arguments": observed_tool_call.arguments,
                        "approval": approval_request_data,
                    })
                    await on_event("tool_result", {
                        "name": tool_call.name,
                        "result": result,
                        "display": summarize_tool_result(
                            tool_call.name,
                            result,
                            self.tool_result_display,
                        ).to_dict(),
                        })
                    activation = getattr(tool, "last_activation", None)
                    if activation and getattr(activation, "activated", False):
                        await on_event("skill_activated", {
                            "skill_name": activation.skill_name,
                            "source": activation.source,
                        })
                    if tool_call.name == "TodoWrite" and not result.startswith("[Error"):
                        await on_event("todo_updated", self._todo_snapshot())

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

    async def _call_llm(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    ) -> tuple[LLMResponse, bool]:
        if not self._should_stream_llm():
            return await self.llm.chat(
                messages=messages,
                tools=tools,
            ), False

        response: LLMResponse | None = None
        content = ""
        stream_chat = getattr(self.llm, "stream_chat")
        async for event in stream_chat(messages=messages, tools=tools):
            if event.type == "assistant_delta":
                content = event.content or f"{content}{event.delta}"
                if on_event and event.delta:
                    await on_event("assistant_delta", {
                        "delta": event.delta,
                        "content": content,
                    })
                continue

            if event.type == "complete":
                response = event.response or LLMResponse(
                    content=event.content or content,
                    stop_reason=event.stop_reason,
                )
                content = event.content or response.content or content
                if on_event:
                    await on_event("assistant_stream_complete", {
                        "content": content,
                        "stop_reason": response.stop_reason,
                    })

        if response is None:
            response = LLMResponse(content=content, stop_reason="end_turn")
            if on_event:
                await on_event("assistant_stream_complete", {
                    "content": content,
                    "stop_reason": response.stop_reason,
                })
        return response, True

    def _should_stream_llm(self) -> bool:
        stream_chat = getattr(self.llm, "stream_chat", None)
        if not callable(stream_chat):
            return False
        if hasattr(self.llm, "stream"):
            return bool(getattr(self.llm, "stream"))
        return True

    def _parse_arguments(self, arguments: str) -> dict:
        import json
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON tool arguments: {e.msg}") from e
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments must be a JSON object")
        return parsed

    async def _execute_single_tool(
        self, tool_call: ToolCall, observed_tool_call: ToolCall, approval_granted: bool
    ) -> tuple[str, float]:
        """Execute one tool call. `tool_call` has original args for execution;
        `observed_tool_call` may have redacted args for hooks/events."""
        await self.hooks.before_tool_execute(observed_tool_call)
        current_tool_call_id.set(tool_call.id)
        tool_start = time.time()
        if tool_call.name == "Bash":
            try:
                result = await self.tool_registry.execute(
                    tool_call, approval_granted=approval_granted,
                )
            except Exception as e:
                logger.error(f"[AgentLoop] tool {tool_call.name} raised: {e}")
                await self.hooks.on_error(e)
                result = f"[Error: {e}]"
        else:
            result = await self._retry.execute_with_retry(
                tool_call,
                execute_fn=lambda tc: self.tool_registry.execute(
                    tc, approval_granted=approval_granted,
                ),
            )
            if result.startswith("[Error"):
                logger.error(
                    f"[AgentLoop] tool {tool_call.name} retry exhausted: {result}"
                )
        duration_ms = (time.time() - tool_start) * 1000
        await self.hooks.after_tool_execute(observed_tool_call, result)
        return result, duration_ms

    async def _execute_tool_calls(self, items: list[dict]) -> list[dict]:
        """Execute pre-processed tool calls with parallel grouping.

        Consecutive parallelizable tools are gathered concurrently.
        Non-parallelizable tools and pre-denied calls are executed serially.
        Results are returned in original order.
        """
        # Build groups: consecutive parallelizable (non-denied, non-approved) calls form one group
        groups: list[list[dict]] = []
        current_group: list[dict] = []
        for item in items:
            tool = item.get("tool")
            decision = item.get("decision")
            # Exclude from parallel if: pre-denied, not parallelizable, or required approval
            pre_denied = item.get("pre_denied_result")
            requires_approval = decision is not None and decision.requires_approval
            is_parallel = (
                tool is not None
                and tool.parallelizable
                and not pre_denied
                and not requires_approval
            )
            if is_parallel:
                current_group.append(item)
            else:
                if current_group:
                    groups.append(current_group)
                    current_group = []
                groups.append([item])
        if current_group:
            groups.append(current_group)

        # Execute groups
        results: list[dict] = []
        for group in groups:
            if len(group) > 1:
                # Parallel group — gather concurrently
                group_names = [item["tool_call"].name for item in group]
                if self._active_trace_recorder:
                    self._active_trace_recorder.record_parallel_execution(group_names)

                async def _run_one(item: dict) -> dict:
                    pre_denied = item.get("pre_denied_result")
                    if pre_denied is not None:
                        return {**item, "result": pre_denied, "duration_ms": 0.0}
                    result, duration_ms = await self._execute_single_tool(
                        item["tool_call"], item["observed_tool_call"], item["approval_granted"],
                    )
                    return {**item, "result": result, "duration_ms": duration_ms}

                group_results = await asyncio.gather(
                    *[_run_one(item) for item in group],
                    return_exceptions=True,
                )
                # Unwrap exceptions from gather
                for i, r in enumerate(group_results):
                    if isinstance(r, Exception):
                        group_results[i] = {
                            **group[i],
                            "result": f"[Error: {r}]",
                            "duration_ms": 0.0,
                        }
                results.extend(group_results)
            else:
                # Serial group (single item)
                item = group[0]
                pre_denied = item.get("pre_denied_result")
                if pre_denied is not None:
                    results.append({**item, "result": pre_denied, "duration_ms": 0.0})
                else:
                    result, duration_ms = await self._execute_single_tool(
                        item["tool_call"], item["observed_tool_call"], item["approval_granted"],
                    )
                    results.append({**item, "result": result, "duration_ms": duration_ms})

        return results

    def _observed_tool_call_delta(self, delta: ToolCallDelta) -> dict:
        try:
            parsed = self._parse_arguments(delta.arguments)
        except ValueError:
            arguments: dict | str = delta.arguments
        else:
            redacted = redact_value(parsed)
            arguments = redacted if isinstance(redacted, dict) else {}
        return {"id": delta.id, "name": delta.name, "arguments": arguments}

    def _messages_with_run_context(self, messages: list[Message]) -> list[Message]:
        injected_contexts = []
        if self.persistent_memory is not None:
            memory_index = self.persistent_memory.load_index()
            if memory_index:
                injected_contexts.append(
                    "## Project Memory\n"
                    "The following persistent memories from prior sessions are available. "
                    "Use RecallMemory to retrieve specific entries.\n"
                    "---\n"
                    f"{memory_index}\n"
                    "---"
                )
        if self.skill_runtime is not None:
            skill_index = self.skill_runtime.render_skill_index()
            if skill_index:
                injected_contexts.append(skill_index)
            active_skill_context = self.skill_runtime.render_active_skill_context()
            if active_skill_context:
                injected_contexts.append(active_skill_context)
        plan_context = self._plan_mode_context()
        if plan_context:
            injected_contexts.append(plan_context)
        planning_context = self._planning.render_context()
        if planning_context:
            injected_contexts.append(planning_context)
        todo_context = self._todo_context()
        if todo_context:
            injected_contexts.append(todo_context)
        if not injected_contexts:
            return messages

        insert_at = 0
        while insert_at < len(messages) and messages[insert_at].role == "system":
            insert_at += 1

        context_messages = [
            system_message(context)
            for context in injected_contexts
        ]
        return [
            *messages[:insert_at],
            *context_messages,
            *messages[insert_at:],
        ]

    def _plan_mode_context(self) -> str:
        if self.runtime_state.current_mode is not AgentMode.PLAN:
            return ""
        return (
            "You are running in plan mode. Inspect the repository with read-only "
            "tools and discuss the plan with the user until it is clear. When the "
            "draft changes materially, call UpdatePlan with the current Markdown "
            "Plan Document and high-level steps. When the user confirms the plan "
            "or the plan is ready to finalize, call ExitPlanMode with the final "
            "Plan Document and steps. Steps can seed a later build-mode todo list. "
            "Do not edit files, run shell commands, or implement changes in plan "
            "mode."
        )

    def _todo_context(self) -> str:
        mode = self.runtime_state.current_mode
        if mode not in (AgentMode.BUILD, AgentMode.READ_ONLY):
            return ""
        if not self._execution_todos:
            return ""

        status_order = {"in_progress": 0, "pending": 1, "completed": 2}
        sorted_items = sorted(
            self._execution_todos[-10:],
            key=lambda item: (status_order.get(str(item.status), 99), self._execution_todos.index(item)),
        )

        lines = ["## Current Progress"]
        for item in sorted_items:
            marker = {"pending": " ", "in_progress": "▶", "completed": "✓"}.get(str(item.status), " ")
            line = f"- [{marker}] {item.content}"
            if item.note:
                line = f"{line} ({item.note})"
            lines.append(line)
        return "\n".join(lines)

    def _last_assistant_content(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "assistant" and message.content:
                return message.content
        return ""

    def _last_user_content(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content
        return ""

    def _save_session(
        self,
        messages: list[Message],
        session_id: str,
        run_id: str,
        resume_snapshot: SessionSnapshot | None,
    ) -> None:
        if self.session_store is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        created_at = resume_snapshot.created_at if resume_snapshot else now
        snapshot = SessionSnapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            session_id=session_id,
            created_at=created_at,
            updated_at=now,
            messages=list(messages),
            mode=self.runtime_state.current_mode,
            todos=list(self._execution_todos),
            active_skills=self.skill_runtime.active_skill_names if self.skill_runtime else [],
            run_id=run_id,
            iteration=self._iteration,
            runtime_fingerprint=self._build_runtime_fingerprint(),
        )
        self.session_store.save(snapshot)

    def _build_runtime_fingerprint(self) -> dict:
        model = getattr(self.llm, "model", "unknown")
        provider = getattr(self.llm, "provider", "unknown")
        try:
            from agent import __version__ as agent_version
        except ImportError:
            agent_version = "unknown"
        return {
            "cwd": os.getcwd(),
            "model": str(model),
            "provider": str(provider),
            "agent_version": agent_version,
        }

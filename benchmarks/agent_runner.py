from __future__ import annotations

import asyncio
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from agent.cost_tracker import CostLedger
from agent.loop import AgentLoop
from agent.config import AsterwyndConfig
from agent.mcp import build_mcp_manager
from agent.memory.manager import MemoryManager
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.subagent.bus import MessageBus
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import compile_pattern
from agent.subagent.scheduler import WorkflowScheduler
from agent.tools.builtin.subagents import parse_spec_for_manager
from agent.tools.factory import build_coding_tool_registry, build_sandbox_from_config
from agent.trace_recorder import TraceRecorder
from agent.workspace_policy import WorkspacePolicy
from benchmarks.models import AgentRunResult, BenchmarkReason
from benchmarks.report import REPLAY_STATUS
from benchmarks.prompt import CodingPromptBuilder
from benchmarks.task_schema import TaskSpec
from benchmarks.workflow_replay import (
    COLLECTION_STATUS_FAILED,
    COLLECTION_STATUS_MISSING,
    COLLECTION_STATUS_OK,
    build_record,
    collect_workflow_records,
    read_workflow_record,
    write_workflow_record,
)

#: benchmark 的三种 workflow 运行模式（C5 D1 / grill Q8）。
WORKFLOW_MODES: tuple[str, ...] = ("template", "dynamic-record", "dynamic-replay")
#: ``template`` 模式默认使用的 pattern（固定回归 baseline）。
DEFAULT_TEMPLATE_PATTERN = "orchestrator-worker"


class AgentRunner(ABC):
    @abstractmethod
    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        ...

    async def close(self) -> None:
        """Release resources (e.g. LLM client). Default no-op."""
        pass


class FakeAgentRunner(AgentRunner):
    def __init__(
        self,
        edit_file: str | None = None,
        old_string: str | None = None,
        new_string: str | None = None,
        status: str = "completed",
        iterations: int = 1,
        tool_calls: int = 1,
    ):
        self.edit_file = edit_file
        self.old_string = old_string
        self.new_string = new_string
        self.status = status
        self.iterations = iterations
        self.tool_calls = tool_calls

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        trace.record_iteration(
            0,
            assistant_preview=f"Fake agent received task: {problem_statement[:120]}",
            tool_calls=[],
        )
        edit_count = 0
        if self.edit_file and self.old_string is not None and self.new_string is not None:
            target = workspace / self.edit_file
            trace.record_tool_call(
                "FakeEdit",
                {"path": self.edit_file, "old_string": self.old_string},
            )
            if not target.exists():
                trace.record_tool_result("FakeEdit", "error", 0, "file not found")
                return AgentRunResult(
                    status="error",
                    reason=BenchmarkReason.EDIT_VALIDATION.value,
                    output="file not found",
                )
            content = target.read_text(errors="replace")
            if self.old_string not in content:
                trace.record_tool_result("FakeEdit", "error", 0, "old_string not found")
                return AgentRunResult(
                    status="error",
                    reason=BenchmarkReason.EDIT_VALIDATION.value,
                    output="old_string not found",
                )
            target.write_text(content.replace(self.old_string, self.new_string, 1), errors="replace")
            edit_count = 1
            trace.record_tool_result("FakeEdit", "ok", 0, "edit applied")
            trace.record_edit(self.edit_file, "ok", "1 replacement")

        return AgentRunResult(
            status=self.status,
            iterations=self.iterations,
            tool_calls=self.tool_calls,
            edit_count=edit_count,
            output="fake agent completed",
        )


class ShellCommandRunner(AgentRunner):
    def __init__(self, command: str, timeout_seconds: int = 300):
        self.command = command
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        start = time.time()
        trace.record_tool_call("ShellAgent", {"command": self.command})

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                self.command,
                cwd=workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=os.environ.copy(),
            )

        try:
            result = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            trace.record_tool_result(
                "ShellAgent",
                "timeout",
                (time.time() - start) * 1000,
                f"timeout after {self.timeout_seconds}s",
            )
            return AgentRunResult(
                status="error",
                tool_calls=1,
                reason=BenchmarkReason.TOOL_ERROR.value,
                output="timeout",
            )

        output = (result.stdout or "") + (result.stderr or "")
        status = "completed" if result.returncode == 0 else "error"
        trace.record_tool_result(
            "ShellAgent",
            "ok" if result.returncode == 0 else "error",
            (time.time() - start) * 1000,
            output,
        )
        return AgentRunResult(
            status=status,
            tool_calls=1,
            reason=None if result.returncode == 0 else BenchmarkReason.TOOL_ERROR.value,
            output=output,
        )


class ClaudeCodeRunner(AgentRunner):
    """Subprocess adapter for the Claude Code CLI (`claude`).

    Invokes ``claude -p`` (headless/print mode) inside the task worktree with
    the raw issue content as the prompt.  Only the final git diff and the
    stdout / stderr transcript are collected — no per-turn tool-call trace is
    available from the external CLI.
    """

    def __init__(self, timeout_seconds: int = 600):
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        start = time.time()

        prompt = (
            "You are working in a code repository.\n"
            "Complete the following task:\n\n"
            f"{problem_statement}\n\n"
            "Verification command (run this before finishing):\n"
            f"{task.test_command}"
        )

        env = os.environ.copy()
        env.setdefault("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")

        cmd = [
            "claude", "-p",
            "--model", "deepseek-chat",
            "--dangerously-skip-permissions",
            "--output-format", "text",
            prompt,
        ]
        trace.record_tool_call("ClaudeCode", {"cmd": " ".join(cmd[:5])})

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )

        try:
            result = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            trace.record_tool_result(
                "ClaudeCode", "timeout",
                (time.time() - start) * 1000,
                f"timeout after {self.timeout_seconds}s",
            )
            return AgentRunResult(
                status="error",
                reason=BenchmarkReason.TOOL_ERROR.value,
                output="Claude Code timed out",
            )

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        trace.record_tool_result(
            "ClaudeCode",
            "ok" if result.returncode == 0 else "error",
            (time.time() - start) * 1000,
            output,
        )
        return AgentRunResult(
            status="completed" if result.returncode == 0 else "error",
            reason=None if result.returncode == 0 else BenchmarkReason.TOOL_ERROR.value,
            output=output,
        )


class CountingLLM:
    """Transparent wrapper that counts ``chat`` calls.

    ``__getattr__`` delegates everything else (``model`` above all) to the
    wrapped LLM. Without the delegation the cost ledger reads
    ``getattr(self.llm, "model", "unknown")`` → ``"unknown"`` → the legacy
    2-tier ``compute_cost`` returns ``None`` for an unpriced model and
    ``CostLedger.total()`` stays exactly 0 — the same "fake zero" failure mode
    the ledger injection exists to prevent (grill Confirmed Decision 14).
    """

    def __init__(self, llm):
        self.llm = llm
        self.call_count = 0

    def __getattr__(self, name):
        return getattr(self.llm, name)

    async def chat(self, *args, **kwargs):
        self.call_count += 1
        return await self.llm.chat(*args, **kwargs)


class AsterwyndRunner(AgentRunner):
    def __init__(
        self,
        llm,
        model: str = "",
        mode: str | AgentMode = AgentMode.BUILD,
        max_iterations: int = 20,
        prompt_builder: CodingPromptBuilder | None = None,
        timeout_seconds: int = 1800,
        config: AsterwyndConfig | None = None,
        workflow_mode: str | None = None,
        workflow_record: str | Path | None = None,
        template_pattern: str = DEFAULT_TEMPLATE_PATTERN,
        temperature: float | None = None,
        seed: int | None = None,
    ):
        self.llm = llm
        self.model = model
        resolved_mode = mode if isinstance(mode, AgentMode) else parse_agent_mode(mode)
        self.run_config = AgentRunConfig(mode=resolved_mode)
        self.max_iterations = max_iterations
        self.prompt_builder = prompt_builder or CodingPromptBuilder()
        self.timeout_seconds = timeout_seconds
        self.config = config or AsterwyndConfig()
        # 三模式接线（grill Q8）：CLI 标志透传到构造参数，``AgentRunner.run`` 的
        # 五参签名不动、模式不塞进 ``TaskSpec``（那会污染任务语义）。
        self.workflow_mode = workflow_mode
        #: ``dynamic-replay`` 的记录来源 = 上次 record 的 **run 目录**；文件名按
        #: ``task_id`` 推导（``<run-dir>/tasks/<task_id>/workflow_record.json``）。
        self.workflow_record = Path(workflow_record).resolve() if workflow_record else None
        self.template_pattern = template_pattern
        self.temperature = temperature
        self.seed = seed

    async def close(self) -> None:
        close_fn = getattr(self.llm, "close", None)
        if close_fn:
            try:
                await close_fn()
            except Exception:
                pass

    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        policy = WorkspacePolicy(
            workspace,
            command_denylist=self.config.tools.command_denylist,
        )
        mcp_manager = await build_mcp_manager(self.config)
        sandbox = build_sandbox_from_config(self.config)
        registry = build_coding_tool_registry(
            policy=policy,
            mode_policy=ModePolicy(
                self.run_config,
                deny_tools_by_mode=self.config.deny_tools_by_mode(),
                permission_profiles_by_mode=self.config.permission_profiles_by_mode(),
            ),
            ignore_patterns=self.config.tools.ignore_patterns,
            code_intelligence_config=self.config.tools.code_intelligence,
            mcp_manager=mcp_manager,
            sandbox=sandbox,
        )

        counting_llm = CountingLLM(self.llm)
        # CostLedger 必须显式注入（grill Confirmed Decision 14）：benchmark 路径
        # 今天没挂 ledger，``manager.cost_ledger`` 为 None → ``AgentLoop`` 的
        # ``if self.cost_ledger:`` 整段跳过 → scheduler 的 ``_ledger_total()`` 恒为 0，
        # ``workflow_cost_usd`` 与 envelope ``total_cost`` 全是假 0。
        cost_ledger = CostLedger()
        subagent_manager = SubAgentManager(
            llm=counting_llm,
            config=self.config,
            workspace_policy=policy,
            parent_mode=self.run_config.mode,
            sandbox=sandbox,
            cost_ledger=cost_ledger,
        )
        agent = AgentLoop(
            llm=counting_llm,
            tool_registry=registry,
            memory=MemoryManager(max_tokens=80_000),
            max_iterations=self.max_iterations,
            subagent_manager=subagent_manager,
            expose_subagent_tools=True,
            run_config=self.run_config,
            tool_result_display=self.config.tools.display,
            mcp_manager=mcp_manager,
            cost_ledger=cost_ledger,
        )
        effective_timeout = self.timeout_seconds
        # 三模式的驱动入口（grill Q8）：只有 dynamic-record（与不指定模式时的
        # 既有行为）走 AgentLoop；template 把 pattern 当被测编排；dynamic-replay
        # 离线重放已保存的 spec、不跑规划模型。三条路都返回同一形状的结果对象，
        # 超时边界与采集点因此不需要分叉。
        if self.workflow_mode == "dynamic-replay":
            coro = self._run_dynamic_replay(
                task=task, subagent_manager=subagent_manager, trace=trace
            )
        elif self.workflow_mode == "template":
            coro = self._run_template_pattern(
                problem_statement=problem_statement,
                subagent_manager=subagent_manager,
                trace=trace,
            )
        else:
            messages = self.prompt_builder.build_messages(
                task=task,
                problem_statement=problem_statement,
                workspace=str(workspace),
            )
            coro = agent.run(
                messages,
                trace_recorder=trace,
                session_id=trace.session_id,
                run_id=trace.run_id,
            )
        try:
            result = await asyncio.wait_for(coro, timeout=effective_timeout)
        except asyncio.TimeoutError:
            # 超时分支绕过正常采集点（grill Confirmed Decision 4）：必须在这里也采
            # 一次，否则超时任务的 workflow 字段会「假装不存在」而不是「采集失败」。
            await mcp_manager.aclose()
            tool_count = sum(1 for step in trace.steps if step.type == "tool_call")
            trace.record_completion(
                "error",
                f"Asterwynd timed out after {effective_timeout}s",
            )
            return AgentRunResult(
                status="error",
                iterations=counting_llm.call_count,
                tool_calls=tool_count,
                reason=BenchmarkReason.MODEL_FAILURE.value,
                output=f"Asterwynd timed out after {effective_timeout}s ({counting_llm.call_count} iterations, {tool_count} tool calls)",
                **self._collect_workflow_fields(subagent_manager, output_dir),
            )
        if isinstance(result, _WorkflowModeResult):
            edit_count, tool_calls_made = 0, 0
        else:
            tool_calls_made = len(result.tool_calls_made)
            edit_count = sum(
                1
                for call in result.tool_calls_made
                if call.name == "Edit"
                and call.result
                and not call.result.startswith("[Permission denied")
                and not call.result.startswith("[Error")
            )
        workflow_fields = self._collect_workflow_fields(subagent_manager, output_dir)
        await mcp_manager.aclose()
        if self.workflow_mode == "dynamic-replay":
            # replay 只比编排、不判分（grill Q10 读法 A）：状态用专用值
            # ``replayed``，由 ``_valid_results`` 显式排除，避免与 record 双重计数。
            # ``template`` **不**走这里——它是被测编排，照走既有 verifier 判分（Q8
            # 读法 1：baseline 同时衡量任务结果与编排指标）。
            return AgentRunResult(
                status=REPLAY_STATUS,
                iterations=counting_llm.call_count,
                output=result.content,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_tokens=result.cache_read_input_tokens,
                cache_write_tokens=result.cache_creation_input_tokens,
                **workflow_fields,
            )
        ended_turn = _stop_reason_value(result.stop_reason) == "end_turn"
        return AgentRunResult(
            status="completed" if ended_turn else "error",
            iterations=counting_llm.call_count,
            tool_calls=tool_calls_made,
            edit_count=edit_count,
            reason=(
                None
                if ended_turn
                else BenchmarkReason.MAX_ITERATIONS.value
            ),
            output=result.content,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_input_tokens,
            cache_write_tokens=result.cache_creation_input_tokens,
            **workflow_fields,
        )

    # -- workflow 三模式（C5 D1/D2/D3） -------------------------------------

    async def _run_template_pattern(
        self,
        *,
        problem_statement: str,
        subagent_manager: SubAgentManager,
        trace: TraceRecorder,
    ) -> "_WorkflowModeResult":
        """``template`` 读法 1：pattern 当**被测编排**，走既有 verifier（Q8）。

        ``problem_statement`` 直接作 ``compile_pattern(..., task=...)`` 的 task 文本。
        """
        spec = compile_pattern(self.template_pattern, task=problem_statement)
        scheduler = WorkflowScheduler(subagent_manager, bus=MessageBus())
        # 与 ``RunPatternTool`` 同路：先注册再驱动，``run()`` 内部会幂等自注册。
        subagent_manager.register_workflow(scheduler)
        envelope = await scheduler.run(spec)
        trace.record(
            "workflow_template",
            status=envelope.get("status"),
            spec_hash=envelope.get("spec_hash"),
            pattern=self.template_pattern,
        )
        return _WorkflowModeResult(
            content=(
                f"template pattern {self.template_pattern} -> "
                f"{envelope.get('status')}"
            )
        )

    async def _run_dynamic_replay(
        self,
        *,
        task: TaskSpec,
        subagent_manager: SubAgentManager,
        trace: TraceRecorder,
    ) -> "_WorkflowModeResult":
        """``dynamic-replay``：读记录 → 离线重放全部图（不重跑规划模型）。"""
        record = (
            read_workflow_record(Path(self.workflow_record) / "tasks" / task.id)
            if self.workflow_record
            else None
        )
        self._replay_record = record
        if record is None:
            trace.record(
                "workflow_replay",
                status=COLLECTION_STATUS_MISSING,
                task_id=task.id,
            )
            return _WorkflowModeResult(
                content=(
                    f"no workflow record for task {task.id} under "
                    f"{self.workflow_record}"
                )
            )
        entries = record.get("workflows") or []
        summaries: list[str] = []
        for entry in entries:
            # parse 必须带 ``_spec_bounds``（D1/Confirmed Decision 13）：否则三闸
            # 退回模块常量而不是 record 时的 ``subagents.workflow.*`` 配置，同一份
            # spec dict 会算出不同运行期上限。
            spec = parse_spec_for_manager(subagent_manager, entry["spec"])
            scheduler = WorkflowScheduler(subagent_manager, bus=MessageBus())
            subagent_manager.register_workflow(scheduler)
            envelope = await scheduler.run(spec)
            summaries.append(
                f"[{envelope['workflow_id']}] {envelope['status']}: "
                f"{envelope.get('spec_hash')}"
            )
        self._replayed_count = len(entries)
        return _WorkflowModeResult(content="\n".join(summaries))

    def _collect_workflow_fields(
        self, manager: SubAgentManager, output_dir: Path
    ) -> dict:
        """采集 workflow 字段（旁路：挂在 ``await agent.run(...)`` 返回之后）。

        采集失败**不影响** run 完成（D1 Risks）：异常一律折成 ``failed`` 状态字段。
        """
        if self.workflow_mode is None:
            return {}
        try:
            return self._collect_workflow_fields_inner(manager, output_dir)
        except Exception as exc:  # noqa: BLE001 - 采集是旁路，绝不打断 run
            return {
                "workflow_mode": self.workflow_mode,
                "workflow_collection_status": COLLECTION_STATUS_FAILED,
                "workflow_envelope": {"collection_error": f"{type(exc).__name__}: {exc}"},
            }

    def _collect_workflow_fields_inner(
        self, manager: SubAgentManager, output_dir: Path
    ) -> dict:
        if self.workflow_mode == "dynamic-replay":
            record = getattr(self, "_replay_record", None)
            if record is None:
                return {
                    "workflow_mode": self.workflow_mode,
                    "workflow_collection_status": COLLECTION_STATUS_MISSING,
                }
            entries = record.get("workflows") or []
            fields: dict = {
                "workflow_mode": self.workflow_mode,
                "workflow_count": len(entries),
                "workflow_collection_status": record.get(
                    "collection_status", COLLECTION_STATUS_OK
                ),
            }
            if entries:
                # 唯一可硬断言的字段（Q6 乙）：同一份 spec dict 走同一个
                # ``parse_workflow_spec``，hash 必然相等。
                fields["workflow_spec_hash"] = entries[0].get("workflow_spec_hash")
                fields["scheduler_version"] = entries[0].get("scheduler_version")
            fields.update(self._envelope_fields(manager))
            return fields

        records, status, error = collect_workflow_records(
            manager,
            model=self.model,
            temperature=self.temperature,
            seed=self.seed,
        )
        write_workflow_record(
            output_dir,
            build_record(
                workflow_mode=self.workflow_mode,
                records=records,
                collection_status=status,
                collection_error=error,
            ),
        )
        fields = {
            "workflow_mode": self.workflow_mode,
            "workflow_count": len(records),
            "workflow_collection_status": status,
        }
        if records:
            fields["workflow_spec_hash"] = records[0]["workflow_spec_hash"]
            fields["scheduler_version"] = records[0]["scheduler_version"]
        fields.update(self._envelope_fields(manager))
        return fields

    def _envelope_fields(self, manager: SubAgentManager) -> dict:
        """从每张图的 scheduler envelope 汇总编排字段（D3）。

        多图时取**第一张**的字段做代表值（``workflow_count`` 另记图数）；单图场景
        下这就是全部信息。
        """
        ids = manager.list_workflows()
        if not ids:
            return {}
        scheduler = manager.get_workflow(ids[0])
        if scheduler is None or not getattr(scheduler, "started", False):
            return {}
        envelope = scheduler.status()
        if envelope.get("status") == "declared":
            return {}
        return {
            "workflow_node_count": len(envelope.get("nodes") or []),
            "workflow_run_count": envelope.get("run_count"),
            "workflow_peak_active": envelope.get("peak_active"),
            "workflow_queue_wait_s": envelope.get("queue_wait_s"),
            "workflow_critical_path_s": envelope.get("critical_path_s"),
            "workflow_cost_usd": envelope.get("total_cost"),
            "workflow_steps": envelope.get("steps"),
            "workflow_spawn_count": envelope.get("workflow_spawn_count"),
            "workflow_redundancy": envelope.get("redundancy"),
            "workflow_rejected_runs": envelope.get("rejected_runs"),
            "workflow_depth_capped_runs": envelope.get("depth_capped_runs"),
            "workflow_queue_cancelled_runs": envelope.get("queue_cancelled_runs"),
            "workflow_queue_full_runs": envelope.get("queue_full_runs"),
            "workflow_envelope": {
                "status": envelope.get("status"),
                "spec_hash": envelope.get("spec_hash"),
                "diagnostics": envelope.get("diagnostics"),
            },
        }


def _stop_reason_value(stop_reason) -> str:
    """``StopReason`` 枚举或裸字符串都归一成字符串（两条驱动路径共用）。"""
    return getattr(stop_reason, "value", stop_reason) or ""


@dataclass
class _WorkflowModeResult:
    """``template`` / ``dynamic-replay`` 的返回面。

    只暴露 ``AgentLoop.RunResult`` 在这两条路径上被消费的字段（``content``、
    ``stop_reason`` 与 token 四项），使调用方的超时/采集路径不必按模式分叉。
    """

    content: str = ""
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

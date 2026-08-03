# tests/agent/test_error_type_wiring.py
"""结构化 error_type 全链路接入（issue #89）集成测试。

覆盖：ToolResult 协议泄漏防护、Bash 超时误判回归、approval 预拒绝打标、
MCP 错误打标、LLM 错误可观测化、词汇映射、TracingHook success 判定。
"""
import json

import pytest

from agent.approval import ApprovalDecisionStatus, ApprovalResponse
from agent.hooks.builtin.tracing import TracingHook
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta
from agent.loop import AgentLoop
from agent.message import Message
from agent.observability import ErrorCategory, ErrorClassifier
from agent.run_config import AgentMode, AgentRunConfig
from agent.tools.base import Tool, ToolCall, ToolResult
from agent.tools.builtin.bash import BashTool
from agent.tools.registry import ToolRegistry
from agent.tools.sandbox.base import SandboxResult
from agent.trace_recorder import TraceRecorder
from agent.workspace_policy import WorkspacePolicy


class ToolThenDoneLLM:
    """First call requests a tool; second ends the turn."""

    def __init__(self, tool_name: str = "Echo", arguments: str = "{}"):
        self.tool_name = tool_name
        self.arguments = arguments
        self.call_count = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content="using tool",
                tool_calls=[ToolCallDelta(id="c1", name=self.tool_name, arguments=self.arguments)],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


class FailingLLM:
    """LLM that always raises (for llm_error observability tests)."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        raise self._exc


class StaticApprovalHandler:
    def __init__(self, status: ApprovalDecisionStatus):
        self.status = status
        self.requests = []

    async def request_approval(self, request):
        self.requests.append(request)
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=self.status,
            reason=f"{self.status.value} in test",
        )


def _tool_result_steps(trace: TraceRecorder) -> list[dict]:
    return [s.data for s in trace.steps if s.type == "tool_result"]


# ── 1.6 协议级泄漏测试：ToolResult 不得泄漏到 hook / record_tool_result ──

class TaggedTool(Tool):
    name = "Tagged"
    description = "returns tagged result"
    parameters = {}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(text="boom", error_type="timeout")


class CapturingHook:
    def __init__(self):
        self.seen: list[tuple] = []

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        pass

    async def after_tool_execute(self, tool_call, result, error_type=None) -> None:
        self.seen.append((tool_call, result, error_type))

    async def before_iteration(self, iteration, messages) -> None: pass
    async def after_llm_call(self, response) -> None: pass
    async def on_error(self, error) -> None: pass
    async def on_completion(self, result) -> None: pass


@pytest.mark.asyncio
async def test_tool_result_does_not_leak_to_hook_or_record_tool_result():
    """回归：ToolResult 只存在于 registry→loop 边界，hook 收到解包 text，
    record_tool_result 收到 error_type 独立参数（grill R1 / Q7）。"""
    registry = ToolRegistry()
    registry.register(TaggedTool())
    hook = CapturingHook()
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=ToolThenDoneLLM(tool_name="Tagged"),
        tool_registry=registry,
        hooks=HookManager([hook]),  # type: ignore[list-item]
    )

    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    # Hook 收到解包后的 str，不是 ToolResult
    assert hook.seen, "hook 应收到 after_tool_execute"
    _, result, error_type = hook.seen[0]
    assert isinstance(result, str)
    assert result == "boom"
    assert error_type == "timeout"

    # record_tool_result 收到结构化 error_type
    steps = _tool_result_steps(trace)
    assert steps, "应记录 tool_result"
    assert steps[0]["status"] == "error"
    assert steps[0]["error_type"] == "timeout"


# ── 3.6 Bash 超时误判回归：JSON timed_out 不再被判为 ok ──

class TimedOutSandbox:
    """Fake ExecutionBackend whose run() returns a timed_out SandboxResult."""

    def is_available(self) -> bool:
        return True

    async def run(self, command, *, timeout=None, cwd=None) -> SandboxResult:
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=100.0,
            timed_out=True,
        )

    async def run_background(self, command, *, cwd=None):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_bash_timeout_json_no_longer_judged_ok():
    """回归：Bash 超时（SandboxResult.timed_out=True）在 trace 中必须记为
    status=error + error_type=timeout，而不是从 JSON 文本误判为 ok。"""
    registry = ToolRegistry()
    registry.register(BashTool(
        policy=WorkspacePolicy("/tmp"),
        sandbox=TimedOutSandbox(),  # type: ignore[arg-type]
    ))
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=ToolThenDoneLLM(tool_name="Bash", arguments='{"cmd": "sleep 60"}'),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=StaticApprovalHandler(ApprovalDecisionStatus.APPROVED),
    )

    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    steps = _tool_result_steps(trace)
    assert steps, "应记录 tool_result"
    assert steps[0]["status"] == "error"
    assert steps[0]["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_bash_normal_json_still_ok():
    """非超时的 Bash 正常结果保持 status=ok（error_type=None），不误伤。"""
    class NormalSandbox:
        def is_available(self) -> bool:
            return True

        async def run(self, command, *, timeout=None, cwd=None) -> SandboxResult:
            return SandboxResult(
                exit_code=0,
                stdout="hello",
                stderr="",
                duration_ms=5.0,
                timed_out=False,
            )

        async def run_background(self, command, *, cwd=None):
            raise NotImplementedError

    registry = ToolRegistry()
    registry.register(BashTool(
        policy=WorkspacePolicy("/tmp"),
        sandbox=NormalSandbox(),  # type: ignore[arg-type]
    ))
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=ToolThenDoneLLM(tool_name="Bash", arguments='{"cmd": "echo hello"}'),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=StaticApprovalHandler(ApprovalDecisionStatus.APPROVED),
    )

    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    steps = _tool_result_steps(trace)
    assert steps, "应记录 tool_result"
    assert steps[0]["status"] == "ok"
    assert steps[0]["error_type"] is None


# ── 3.6 approval 预拒绝打标 ──

class HighRiskTool(Tool):
    name = "HighRisk"
    description = "needs approval"
    parameters = {}
    dangerous = True

    async def execute(self, **kwargs) -> str:
        return "ran"


@pytest.mark.asyncio
async def test_approval_denied_records_approval_denied_error_type():
    """回归：approval DENIED 预拒绝结果此前被判为 ok，现必须 error +
    error_type=approval_denied（Q6：status=error，executed=False 不污染 quality）。"""
    from agent.tool_permissions import ToolCapability, ToolPermission, ToolRiskLevel

    class ApprovalTool(Tool):
        name = "ApprovalNeeded"
        description = "needs approval"
        parameters = {}
        permission = ToolPermission(
            capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
            risk_level=ToolRiskLevel.HIGH,
        )

        async def execute(self, **kwargs) -> str:
            return "ran"

    registry = ToolRegistry(mode_policy=__import__("agent.run_config", fromlist=["ModePolicy"]).ModePolicy(
        AgentRunConfig(mode=AgentMode.BUILD)
    ))
    registry.register(ApprovalTool())
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=ToolThenDoneLLM(tool_name="ApprovalNeeded"),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=StaticApprovalHandler(ApprovalDecisionStatus.DENIED),
    )

    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    steps = _tool_result_steps(trace)
    assert steps, "应记录 tool_result"
    assert steps[0]["status"] == "error"
    assert steps[0]["error_type"] == "approval_denied"


# ── 3.6 MCP 错误打标（经 ToolResult 通道）──

@pytest.mark.asyncio
async def test_tagged_mcp_error_records_mcp_error():
    """MCP 错误经 McpTool.execute 转为 ToolResult(error_type="mcp_error")，
    loop 记录结构化 mcp_error 而非文本猜测。"""
    class McpFailingTool(Tool):
        name = "McpFail"
        description = "fails via mcp"
        parameters = {}

        async def execute(self, **kwargs) -> ToolResult:
            return ToolResult(
                text="[MCP tool error: servers/x: ConnectionError: boom]",
                error_type="mcp_error",
            )

    registry = ToolRegistry()
    registry.register(McpFailingTool())
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=ToolThenDoneLLM(tool_name="McpFail"),
        tool_registry=registry,
        hooks=HookManager(),
    )

    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    steps = _tool_result_steps(trace)
    assert steps, "应记录 tool_result"
    assert steps[0]["status"] == "error"
    assert steps[0]["error_type"] == "mcp_error"


# ── 4.3 LLM 错误可观测化：record_llm_error + re-raise ──

@pytest.mark.asyncio
async def test_llm_error_records_llm_error_and_reraised():
    """LLM 调用抛错时 trace 记录 llm_error（error_type=network_timeout），
    且异常继续上抛（run 失败语义不变，Q4 re-raise）。"""
    registry = ToolRegistry()
    registry.register(TaggedTool())
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=FailingLLM(ConnectionError("boom")),
        tool_registry=registry,
        hooks=HookManager(),
    )

    with pytest.raises(ConnectionError):
        await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    llm_error_steps = [s for s in trace.steps if s.type == "llm_error"]
    assert llm_error_steps, "应记录 llm_error"
    assert llm_error_steps[0].data["error_type"] == "network_timeout"
    assert "boom" in llm_error_steps[0].data["message"]


@pytest.mark.asyncio
async def test_llm_error_model_error_classification():
    """非网络类 LLM 异常（如 API/auth）归为 model_error。"""
    registry = ToolRegistry()
    trace = TraceRecorder()
    loop = AgentLoop(
        llm=FailingLLM(RuntimeError("rate limited")),
        tool_registry=registry,
        hooks=HookManager(),
    )

    with pytest.raises(RuntimeError):
        await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    llm_error_steps = [s for s in trace.steps if s.type == "llm_error"]
    assert llm_error_steps
    assert llm_error_steps[0].data["error_type"] == "model_error"


# ── 5.3 词汇映射与 TracingHook success ──

def test_error_type_to_category_mapping():
    """新增 error_type 值映射到粗粒度四类类别（Q1/Q8）。"""
    classifier = ErrorClassifier()
    assert classifier.classify(error_type="approval_denied") is ErrorCategory.PERMISSION_DENIED
    assert classifier.classify(error_type="approval_unavailable") is ErrorCategory.PERMISSION_DENIED
    assert classifier.classify(error_type="approval_required") is ErrorCategory.PERMISSION_DENIED
    assert classifier.classify(error_type="network_error") is ErrorCategory.NETWORK_TIMEOUT
    assert classifier.classify(error_type="unknown_tool") is ErrorCategory.PARAMETER_ERROR
    assert classifier.classify(error_type="resource_exhausted") is ErrorCategory.UNKNOWN
    assert classifier.classify(error_type="mcp_error") is ErrorCategory.UNKNOWN
    assert classifier.classify(error_type="unavailable") is ErrorCategory.UNKNOWN


@pytest.mark.asyncio
async def test_tracing_hook_success_uses_error_type_signal():
    """TracingHook: 结构化 error_type 判失败（Bash 超时），无 signal 回退文本。"""
    hook = TracingHook()
    call = ToolCall(id="c1", name="Bash", arguments={})

    await hook.before_tool_execute(call)
    await hook.after_tool_execute(call, json.dumps({"timed_out": True}), error_type="timeout")
    assert hook.calls[-1].success is False

    await hook.before_tool_execute(call)
    await hook.after_tool_execute(call, json.dumps({"timed_out": False}))
    assert hook.calls[-1].success is True

    # 未打标工具错误文本回退
    await hook.before_tool_execute(call)
    await hook.after_tool_execute(call, "[Permission denied: can't write]")
    assert hook.calls[-1].success is False

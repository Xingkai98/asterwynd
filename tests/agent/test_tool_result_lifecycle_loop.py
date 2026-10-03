"""Loop 级工具结果生命周期（change ``tool-result-lifecycle``）：入库通道 + GC 不变量 +
D12 事件 payload。

对应 design D0/D2/D6b/D8/D12：
- GC 不变量（**断言内存字段**，不只靠弱引用——``asdict`` 对 str 子类复制，D0）；
- tool-call 链在剪枝后仍合法；
- 账本池（trace / tool_calls_made）超阈 bounded，分析字段保留；
- 无回读工具时不 spill（D8）；
- ``tool_result`` 事件不含全文、带 ``tool_call_id``（D12）。

剪枝时机（D3/A1=-1）：结果在 iteration k 入库、k+1 末尾（又有工具调用 ⇒ Phase 3 再跑）
才剪。故测试脚本让模型连续两轮各调一次工具，第二轮末尾剪掉第一轮的结果。
"""
import gc
import weakref

import pytest

from agent.artifact_store import ArtifactRef, AgentArtifactStore, extract_result_ref
from agent.hooks.manager import HookManager
from agent.llm import LLMResponse, ToolCallDelta
from agent.loop import AgentLoop
from agent.memory import manager as _manager_mod
from agent.memory.manager import MemoryManager
from agent.message import Message, extract_text
from agent.run_config import AgentRunConfig
from agent.subagent.manager import SubAgentManager
from agent.tools.base import Tool, tool_parameters
from agent.tools.registry import ToolRegistry
from agent.trace_recorder import TraceRecorder
from agent.workspace_policy import WorkspacePolicy


def _counter(text: str) -> int:
    return len(text) // 4


@pytest.fixture(autouse=True)
def _fast_token_counter(monkeypatch):
    monkeypatch.setattr(_manager_mod, "_count_tokens", _counter)


class _WeakStr(str):
    """可弱引用的 ``str`` 子类（``weakref.ref(str)`` 抛 TypeError）。"""


@tool_parameters(name="BigTool", description="Returns a huge payload",
                 parameters={"type": "object", "properties": {}, "required": []})
class BigTool(Tool):
    name = "BigTool"
    description = "Returns a huge payload"
    parameters = {}

    def __init__(self, big, small="ok"):
        self._big = big
        self._small = small
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            out = self._big
            self._big = None   # drop the tool's own ref — only holders left are
            return out         # messages + ledger, which the change makes bounded
        return self._small


@tool_parameters(name="SmallTool", description="echo",
                 parameters={"type": "object", "properties": {}, "required": []})
class SmallTool(Tool):
    name = "SmallTool"
    description = "echo"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "ok"


class ScriptedLLM:
    """Emit ``n_tool_calls`` tool-call iterations (ids c0..), then finish."""

    def __init__(self, tool_name, n_tool_calls=2, arguments="{}"):
        self.calls = 0
        self._tool_name = tool_name
        self._n = n_tool_calls
        self._arguments = arguments

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        index = self.calls
        self.calls += 1
        if index < self._n:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallDelta(id=f"c{index}", name=self._tool_name,
                                          arguments=self._arguments)],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


def _loop(tmp_path, scripted, tool, *, memory=None, expose=True):
    registry = ToolRegistry()
    registry.register(tool)
    registry.workspace_policy = WorkspacePolicy(workspace_root=tmp_path)
    return AgentLoop(
        llm=scripted,
        tool_registry=registry,
        hooks=HookManager(),
        memory=memory or MemoryManager(max_tokens=80_000, recent_window=2),
        subagent_manager=SubAgentManager(
            workspace_policy=WorkspacePolicy(workspace_root=tmp_path)
        ),
        expose_subagent_tools=expose,
        run_config=AgentRunConfig(),
    )


def _tool_messages(messages):
    return [m for m in messages if m.role == "tool"]


# ── GC 不变量（A0/D0）────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gc_invariant_three_holders_all_bounded(tmp_path):
    """两轮工具调用 ⇒ 第一轮的 400KB 结果被剪；三处内存字段均有界；全文可 GC。"""
    payload = _WeakStr("A" * 400_000)
    w = weakref.ref(payload)
    trace = TraceRecorder(full_trace=False)
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(payload))

    messages = [Message(role="user", content="go")]
    result = await loop.run(messages, trace_recorder=trace, session_id="s-gc", run_id="r-1")

    tool_msgs = _tool_messages(messages)
    assert len(tool_msgs) == 2
    # c0（第一轮，已消费一轮）被替换为预览 + ref；c1（末轮）仍保全文（B: small）。
    first_body = extract_text(tool_msgs[0].content)
    assert "truncated" in first_body.lower()
    assert extract_result_ref(first_body) is not None
    # 内存态断言（D0：不能只靠弱引用）
    assert all(len(str(s.data.get("observation") or "")) < 400_000
               for s in trace.steps if s.type == "tool_result")
    assert all(len(str(tc.result or "")) < 400_000 for tc in result.tool_calls_made)
    # 原对象可被 GC（messages 的 c0 已换预览、账本已 bounded）
    del payload
    gc.collect()
    assert w() is None


@pytest.mark.asyncio
async def test_gc_invariant_not_falsely_passing(tmp_path):
    """反假通过（D0 硬约束）：断言账本池**内存字段**已 bounded，而非只看弱引用。

    若账本池未 bounded，``trace.steps[*].data["observation"]`` 与
    ``tool_calls_made[*].result`` 会仍是全文——下面的断言直接失败。
    """
    payload = _WeakStr("B" * 400_000)
    trace = TraceRecorder(full_trace=False)
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=1), BigTool(payload))
    messages = [Message(role="user", content="go")]
    result = await loop.run(messages, trace_recorder=trace, session_id="s-2", run_id="r-2")
    # 末轮结果剪不掉，但账本池在**入库时**即 bounded。
    assert all(len(str(s.data.get("observation") or "")) < 400_000
               for s in trace.steps if s.type == "tool_result")
    assert len(str(result.tool_calls_made[0].result)) < 400_000


@pytest.mark.asyncio
async def test_tool_call_chain_valid_after_prune(tmp_path):
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(_WeakStr("C" * 400_000)))
    messages = [Message(role="user", content="go")]
    await loop.run(messages, session_id="s-chain", run_id="r-3")

    tool_msgs = _tool_messages(messages)
    assert [m.tool_call_id for m in tool_msgs] == ["c0", "c1"]
    assistants = [m for m in messages if m.role == "assistant" and m.tool_calls]
    assert [a.tool_calls[0].id for a in assistants] == ["c0", "c1"]
    # 链有序：user → assistant(c0) → tool(c0) → assistant(c1) → tool(c1) → assistant(final)
    roles = [m.role for m in messages]
    assert roles == ["user", "assistant", "tool", "assistant", "tool", "assistant"]


@pytest.mark.asyncio
async def test_spilled_message_reads_back_verbatim_via_ref(tmp_path):
    """A3：剪枝写盘后，按预览内嵌 ref 逐字节无损回读。"""
    payload = "D" * 400_000
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(payload))
    messages = [Message(role="user", content="go")]
    await loop.run(messages, session_id="s-ref", run_id="r-4")

    ref = extract_result_ref(_tool_messages(messages)[0].content)
    assert ref is not None
    parsed = ArtifactRef.parse(ref)
    assert parsed.kind == "agent"
    store = AgentArtifactStore.for_workspace(tmp_path, parsed.scope_id)
    assert store.load(ref) == payload


@pytest.mark.asyncio
async def test_oversized_result_not_spilled_when_read_tool_unavailable(tmp_path):
    """D8：``expose_subagent_tools=False`` ⇒ 回读工具未注册 ⇒ 不 spill（不谎称 ref）。"""
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2),
                 BigTool(_WeakStr("E" * 400_000)), expose=False)
    messages = [Message(role="user", content="go")]
    await loop.run(messages, session_id="s-noref", run_id="r-5")
    first = _tool_messages(messages)[0]
    # 仍被剪（内存有界），但标记如实为 [truncated]，不指向 ref。
    assert first.content.endswith("[truncated]")
    assert extract_result_ref(first.content) is None


@pytest.mark.asyncio
async def test_small_result_kept_within_window(tmp_path):
    """窗口内的小结果不被替换（滑出窗口才剪——spec scenario「当轮保留」）。"""
    memory = MemoryManager(max_tokens=80_000, recent_window=10)
    loop = _loop(tmp_path, ScriptedLLM("SmallTool", n_tool_calls=2), SmallTool(), memory=memory)
    messages = [Message(role="user", content="go")]
    await loop.run(messages, session_id="s-small", run_id="r-6")
    for m in _tool_messages(messages):
        assert m.content == "ok"


@pytest.mark.asyncio
async def test_second_run_same_scope_does_not_overwrite_earlier_ref(tmp_path):
    """resume 语义：同 scope（session_id）跑两次，第二次的 spill 不覆盖第一次的 ref。"""
    first_payload = "P" * 400_000
    second_payload = "Q" * 400_000

    # Run 1
    loop1 = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(first_payload))
    msgs1 = [Message(role="user", content="go")]
    await loop1.run(msgs1, session_id="s-shared", run_id="r-a")
    ref1 = extract_result_ref(_tool_messages(msgs1)[0].content)
    assert ref1 is not None
    parsed = ArtifactRef.parse(ref1)
    store = AgentArtifactStore.for_workspace(tmp_path, parsed.scope_id)
    assert store.load(ref1) == first_payload

    # Run 2 (same session scope, fresh loop) — must not clobber ref1's file.
    loop2 = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(second_payload))
    msgs2 = [Message(role="user", content="go")]
    await loop2.run(msgs2, session_id="s-shared", run_id="r-b")
    ref2 = extract_result_ref(_tool_messages(msgs2)[0].content)
    assert ref2 is not None and ref2 != ref1

    assert store.load(ref1) == first_payload     # run 1's ref still reads its own body
    assert store.load(ref2) == second_payload


@pytest.mark.asyncio
async def test_resumed_history_tool_result_is_spilled(tmp_path):
    """M2 回归：resume 重载的历史工具结果（快照时仍是全文）在后续轮被剪（有界）。"""
    legacy = "Z" * 400_000
    loop = _loop(tmp_path, ScriptedLLM("SmallTool", n_tool_calls=2), SmallTool())

    # Build a resume snapshot carrying a full (unspilled) historical tool result.
    from agent.session import SessionSnapshot
    from agent.run_config import AgentMode
    from agent.message import Message as M

    snapshot_messages = [
        M(role="user", content="earlier task"),
        M(role="assistant", content="",
          tool_calls=[ToolCallDelta(id="h1", name="Read", arguments="{}")]),
        M(role="tool", content=legacy, tool_call_id="h1"),
    ]
    snapshot = SessionSnapshot(
        schema_version="1.0", session_id="s-resume", created_at="", updated_at="",
        messages=snapshot_messages, mode=AgentMode.BUILD, todos=[], active_skills=[],
        run_id="r-old", iteration=1,
    )
    messages = [M(role="user", content="go")]
    await loop.run(messages, session_id="s-resume", run_id="r-new", resume_snapshot=snapshot)

    historic = next(m for m in _tool_messages(messages) if m.tool_call_id == "h1")
    assert len(extract_text(historic.content)) < 400_000     # spilled, not resident
    assert extract_result_ref(extract_text(historic.content)) is not None


@pytest.mark.asyncio
async def test_arguments_bounded_in_ledger(tmp_path):
    """D6b：一次工具带 300KB 参数时，``tool_calls_made[*].arguments`` 有界（保结构）。"""
    import json

    class ArgTool(Tool):
        name = "BigTool"
        description = "x"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            return "ok"

    huge_args = json.dumps({"path": "/a", "content": "W" * 400_000})
    scripted = ScriptedLLM("BigTool", n_tool_calls=1, arguments=huge_args)
    loop = _loop(tmp_path, scripted, ArgTool())
    messages = [Message(role="user", content="go")]
    result = await loop.run(messages, session_id="s-args", run_id="r-9")
    bounded = result.tool_calls_made[0].arguments
    assert bounded["path"] == "/a"                       # structure preserved
    assert len(bounded["content"]) < 400_000             # big leaf bounded
    assert bounded["content"].endswith("[truncated]")


# ── D12：事件 payload ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_result_event_has_no_full_text_and_carries_tool_call_id(tmp_path):
    events = []

    async def on_event(event_type, data):
        events.append((event_type, data))

    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool("F" * 400_000))
    messages = [Message(role="user", content="go")]
    await loop.run(messages, on_event=on_event, session_id="s-ev", run_id="r-7")

    tool_results = [d for (t, d) in events if t == "tool_result"]
    assert tool_results
    payload = tool_results[0]
    assert payload["tool_call_id"] == "c0"          # D12: stable id
    assert "result" not in payload                  # no full text on the event
    assert payload["display"]["char_count"] == 400_000   # metadata still full-length


@pytest.mark.asyncio
async def test_spill_observability_emitted(tmp_path):
    """D9：剪枝发生（c0 被 spill）时发 tool_result_spill 事件 + trace step。"""
    events = []

    async def on_event(event_type, data):
        events.append((event_type, data))

    trace = TraceRecorder()
    loop = _loop(tmp_path, ScriptedLLM("BigTool", n_tool_calls=2), BigTool(_WeakStr("G" * 400_000)))
    messages = [Message(role="user", content="go")]
    await loop.run(messages, trace_recorder=trace, on_event=on_event,
                   session_id="s-obs", run_id="r-8")

    spill_events = [d for (t, d) in events if t == "tool_result_spill"]
    assert spill_events
    assert max(d["spilled_messages"] for d in spill_events) >= 1
    assert max(d["released_bytes"] for d in spill_events) > 0
    assert any(s.type == "tool_result_spill" for s in trace.steps)

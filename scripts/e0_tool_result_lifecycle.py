"""E0 端到端对照：工具结果生命周期对**常驻内存**的影响（change tool-result-lifecycle）。

#278 复现器（单 agent 逐文件审查大源码树）的缩比版：驱动真实 ``AgentLoop`` 跑 N 轮，
每轮返回一个 ~192KB 工具结果，测量循环结束、``gc.collect()`` 后的 **RSS 峰值** 与
**常驻文本总量**。两态对照：

- ``--mode legacy``：把工具结果按全文留在 ``messages`` / ``tool_calls_made`` /
  ``trace``（模拟 change 前的行为——直接构造三处持有，不经 loop 的有界化）；
- ``--mode bounded``：走真实 ``AgentLoop``（剪枝 + 账本 bounded + spill）。

**E0 是对照观测，不设门槛**（design D0/Risks）：RSS 受 cgroup 邻居与采样时机影响，
机制正确性由 GC 不变量（A0）机械证明。本脚本如实打印两组数字对比。

用法::

    uv run python scripts/e0_tool_result_lifecycle.py --n 30 --mode bounded
    uv run python scripts/e0_tool_result_lifecycle.py --n 30 --mode legacy
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.hooks.manager import HookManager  # noqa: E402
from agent.llm import LLMResponse, ToolCallDelta  # noqa: E402
from agent.loop import AgentLoop  # noqa: E402
from agent.memory.manager import MemoryManager  # noqa: E402
from agent.message import Message  # noqa: E402
from agent.message import tool_result_message  # noqa: E402
from agent.result import ToolCallMade  # noqa: E402
from agent.run_config import AgentRunConfig  # noqa: E402
from agent.subagent.manager import SubAgentManager  # noqa: E402
from agent.tools.base import Tool, tool_parameters  # noqa: E402
from agent.tools.registry import ToolRegistry  # noqa: E402
from agent.trace_recorder import TraceRecorder  # noqa: E402
from agent.workspace_policy import WorkspacePolicy  # noqa: E402

BODY = "line of content here\n" * 9_000  # ~192KB


def _rss_kb() -> int:
    """当前进程 RSS（KB）。Linux ``/proc/self/statm``。"""
    try:
        with open("/proc/self/statm") as fh:
            pages = int(fh.read().split()[1])
        return pages * (os.sysconf("SC_PAGE_SIZE") // 1024)
    except (OSError, ValueError, IndexError):
        return -1


@tool_parameters(name="ReadBig", description="return a big file chunk",
                 parameters={"type": "object", "properties": {}, "required": []})
class ReadBigTool(Tool):
    name = "ReadBig"
    description = "return a big file chunk"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return BODY


class _ScriptedLLM:
    """Drive ``n`` tool-call iterations, then finish."""

    def __init__(self, n: int):
        self.n = n
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        i = self.calls
        self.calls += 1
        if i < self.n:
            return LLMResponse(
                content="",
                tool_calls=[ToolCallDelta(id=f"c{i}", name="ReadBig", arguments="{}")],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


async def run_loop(n: int, tmp: Path, *, bound: bool) -> dict:
    """真实 ``AgentLoop`` 路径。``bound=False`` 在同一 loop 上关掉本 change 的
    有界化（no-op 剪枝 + identity 账本 + full_trace）——两次走同一套 loop 脚手架，
    差异只来自本 change，是真 A/B。"""
    import tracemalloc

    registry = ToolRegistry()
    registry.register(ReadBigTool())
    registry.workspace_policy = WorkspacePolicy(workspace_root=tmp)
    loop = AgentLoop(
        llm=_ScriptedLLM(n),
        tool_registry=registry,
        hooks=HookManager(),
        memory=MemoryManager(max_tokens=80_000, recent_window=4),
        subagent_manager=SubAgentManager(workspace_policy=WorkspacePolicy(workspace_root=tmp)),
        expose_subagent_tools=True,
        run_config=AgentRunConfig(),
    )
    if not bound:
        # 关掉本 change 的三处有界化，保留其余一切（真·基线的入径）。
        from agent.memory.manager import PruneStats

        loop.memory.prune_tool_results = lambda *a, **k: PruneStats()  # type: ignore[assignment]
        loop._bound_ledger_result = lambda result: result  # type: ignore[assignment]

    messages = [Message(role="user", content="review the tree")]
    trace = TraceRecorder(full_trace=not bound)
    gc.collect()
    rss_before = _rss_kb()
    tracemalloc.start()
    result = await loop.run(messages, trace_recorder=trace, session_id="e0", run_id="e0-run")
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()
    rss_after = _rss_kb()
    return {
        "rss_delta_kb": max(0, rss_after - rss_before),
        "tm_current_kb": cur // 1024,
        "tm_peak_kb": peak // 1024,
        "resident_chars": _resident_chars(messages, result),
    }


async def run_bounded(n: int, tmp: Path) -> dict:
    return await run_loop(n, tmp, bound=True)


def run_legacy(n: int) -> dict:
    """Change 前行为：三处持全文（直接构造，不经有界化）。"""
    import tracemalloc

    msgs: list = [Message(role="user", content="review the tree")]
    tcms: list = []
    trace = TraceRecorder(full_trace=False)
    gc.collect()
    rss_before = _rss_kb()
    tracemalloc.start()
    for i in range(n):
        body = f"[file {i}]\n{BODY}"
        msgs.append(tool_result_message(f"c{i}", body))
        tcms.append(ToolCallMade(name="ReadBig", arguments={}, result=body))
        trace.record_tool_result("ReadBig", "ok", 1.0, body)
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()
    rss_after = _rss_kb()
    holder = type("R", (), {"tool_calls_made": tcms})()
    resident = _resident_chars(msgs, holder)
    del msgs, tcms, trace, holder
    gc.collect()
    return {
        "rss_delta_kb": max(0, rss_after - rss_before),
        "tm_current_kb": cur // 1024,
        "tm_peak_kb": peak // 1024,
        "resident_chars": resident,
    }


def _resident_chars(messages, result) -> int:
    """常驻文本总量：messages 工具结果 + tool_calls_made.result + trace observation。"""
    from agent.message import extract_text

    total = 0
    for m in messages:
        if m.role == "tool":
            total += len(extract_text(m.content))
    for tc in getattr(result, "tool_calls_made", []) or []:
        total += len(extract_text(tc.result)) if tc.result is not None else 0
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=["bounded", "unbounded", "legacy", "both"],
        default="both",
        help="bounded/unbounded = 同一 AgentLoop 的 A/B；legacy = 直接构造三处持有；"
             "both = bounded + legacy（各自独立进程时为干净对照）。",
    )
    args = parser.parse_args()

    if args.mode == "bounded":
        _print_loop(args.n, bound=True, label="bounded")
    elif args.mode == "unbounded":
        _print_loop(args.n, bound=False, label="unbounded")
    elif args.mode == "legacy":
        print(_fmt("legacy ", args.n, run_legacy(args.n)))
    else:  # both
        _print_loop(args.n, bound=True, label="bounded")
        print(_fmt("legacy ", args.n, run_legacy(args.n)))


def _print_loop(n: int, *, bound: bool, label: str) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with tempfile.TemporaryDirectory() as d:
            m = asyncio.run(run_loop(n, Path(d), bound=bound))
    print(_fmt(label, n, m))


def _fmt(label: str, n: int, m: dict) -> str:
    return (
        f"[{label:9s}] N={n}  RSS增量={m['rss_delta_kb']}KB  "
        f"tracemalloc cur={m['tm_current_kb']}KB peak={m['tm_peak_kb']}KB  "
        f"常驻文本={m['resident_chars']/1024:.0f}KB"
    )


if __name__ == "__main__":
    main()

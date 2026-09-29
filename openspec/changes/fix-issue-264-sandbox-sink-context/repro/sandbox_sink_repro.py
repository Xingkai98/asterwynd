"""issue #264 复现（源自 #261 派生调查）（变体 A）：`set_sandbox_sink` 是否受同一「遗留 pending task
的跨上下文收尾」机制影响？—— 本脚本复现**事件静默丢失**形态。

**结论（实测，确定性）：能复现，且可观测。**

  遗留子 run 的 enqueue 上下文里 sink 为**默认 `_NOOP`**（无 trace recorder 的
  父子链，最常见）→ 其跨上下文收尾把这个 `_NOOP` 写进当前上下文 → **后续 run 的
  sandbox sink 被清成 `_NOOP`** → 后续 run 发出的 sandbox 事件**静默丢失**
  （不写进任何 trace）。

更严重的**串写**形态（覆盖成过期真 sink、事件落进别的 trace）见
`sandbox_sink_misroute.py`（同样实测确定性 3/3，含对照）。

机制回顾（`diagnosis.md` 的 `## Root Cause`）
------------------------------------------------
`AgentLoop.run` 的 ``finally`` 里有两个 contextvar 恢复：

    set_sandbox_sink(previous_sandbox_sink)   # agent/loop.py ~601，**无条件**
    reset_mode_ceiling(ceiling_token)         # issue #261 已改为守护式 reset

`set_sandbox_sink`（`agent/sandbox_events.py:46`）只是 `ContextVar.set`，**没有**
token/reset 版本。当某个**被遗留的 pending 子 run task**（其 event loop 已关闭）在
**后续 run 的上下文里**被 GC 终结时，`GeneratorExit` 会展开它的所有嵌套 ``finally``——
包括这句 `set_sandbox_sink(previous_sandbox_sink)`；由于它写「当前正在运行的上下文」，
就会把**后续 run 正在使用的 sink** 覆盖掉。

复现要点（与 `realpath_ab.py` 同源，实测确定性）：
1. 在独立 event loop 上跑一个会挂住的**子 run**，然后关闭该 loop（task 仍 pending，
   即 CI 日志 ``Task was destroyed but it is pending!``）。`asyncio.set_event_loop`
   把该 loop 保活到 live 阶段，使遗留 task 的终结落在 live run 的上下文里。
2. plant 与 live 之间**不得** `gc.collect()`——否则 task 会在主上下文（无活跃 sink）
   里无害终结，复现消失。
3. 跑一个带 `TraceRecorder` 的**后续 root run**；在它的轮次里 `gc.collect()` 终结
   遗留 task（正是在本 run 的 sink 生效窗口内），并发出一个 sandbox 事件。
4. 检查：后续 run 的 sink 是否被覆盖、覆盖成什么、事件是否丢失。

退出码：0 = 未复现；1 = 复现。
本脚本**只读**生产代码（sandbox sink 的修复待用户拍板）。
"""
from __future__ import annotations

import asyncio
import gc
import pathlib
import sys
import tempfile

def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up to the checkout root.

    The archived #261 scripts hard-coded ``parents[4]``, which only resolves to
    the repo root while the change lives in ``openspec/changes/<id>/``; after
    archiving (one directory deeper) it silently points at ``openspec/``. They
    still ran because callers passed ``PYTHONPATH=.`` — a latent trap. Walk up
    to a real marker instead, so the script works active *and* archived.
    """
    for candidate in (start, *start.parents):
        if (candidate / "agent" / "loop.py").is_file():
            return candidate
    raise RuntimeError("repo root not found (no agent/loop.py above this file)")


REPO = _find_repo_root(pathlib.Path(__file__).resolve())
sys.path.insert(0, str(REPO))

from agent.config import AsterwyndConfig  # noqa: E402
from agent.llm import LLMResponse, Usage  # noqa: E402
from agent.loop import AgentLoop  # noqa: E402
from agent.message import Message  # noqa: E402
from agent.run_config import AgentMode, AgentRunConfig  # noqa: E402
from agent.sandbox_events import (  # noqa: E402
    NoopSandboxSink,
    current_sandbox_sink,
    emit_sandbox_event,
)
from agent.subagent.manager import SubAgentManager  # noqa: E402
from agent.trace_recorder import TraceRecorder  # noqa: E402
from agent.tools.registry import ToolRegistry  # noqa: E402
from agent.workspace_policy import WorkspacePolicy  # noqa: E402


def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up to the checkout root.

    The archived #261 scripts hard-coded ``parents[4]``, which only resolves to
    the repo root while the change lives in ``openspec/changes/<id>/``; after
    archiving (one directory deeper) it silently points at ``openspec/``. They
    still ran because callers passed ``PYTHONPATH=.`` — a latent trap. Walk up
    to a real marker instead, so the script works active *and* archived.
    """
    for candidate in (start, *start.parents):
        if (candidate / "agent" / "loop.py").is_file():
            return candidate
    raise RuntimeError("repo root not found (no agent/loop.py above this file)")

LIVE_ROOT = "__SINK_LIVE_ROOT__"
CHILD_TASK = "__SINK_CHILD_HANG__"


def _last_user(messages) -> str:
    for m in reversed(messages):
        if getattr(m, "role", None) == "user":
            return getattr(m, "content", "") or ""
    return ""


class _ProbeLLM:
    """子 run（task 含 ``CHILD_TASK``）挂住；live 轮次观测 sink 并发事件。"""

    model = "sandbox-sink-probe"

    def __init__(self) -> None:
        self.mgr: SubAgentManager | None = None
        self.obs: dict = {}

    async def chat(self, messages, tools=None, model="gpt-4"):
        text = _last_user(messages)
        if CHILD_TASK in text:
            await asyncio.sleep(9999)              # 遗留子 run 在此挂起
        if LIVE_ROOT in text:
            before = current_sandbox_sink()
            gc.collect()                           # 在本 run 的 sink 窗口内终结遗留 task
            after = current_sandbox_sink()
            emit_sandbox_event("denied", command="rm -rf /", reason="live")
            self.obs = {
                "sink_before": type(before).__name__,
                "sink_after": type(after).__name__,
                "sink_clobbered": before is not after,
                "clobbered_to": type(after).__name__,
            }
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))


def _manager(tmp, llm) -> SubAgentManager:
    return SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp),
    )


def _root(manager, mode) -> AgentLoop:
    return AgentLoop(
        llm=manager.llm, tool_registry=ToolRegistry(), subagent_manager=manager,
        expose_subagent_tools=True, run_config=AgentRunConfig(mode=mode),
    )


def _plant(tmp) -> None:
    """直驱（无 recorder）派生会挂住的子 run，然后关闭其 loop。

    子 run 的 enqueue 上下文里 sink = 默认 `_NOOP`。`set_event_loop` 把 loop 保活到
    live 阶段，使遗留 task 的终结推迟到 live 上下文里发生。
    """
    llm = _ProbeLLM()
    manager = _manager(tmp, llm)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def plant():
        child = manager.create_subagent(name="abandoned", mode="build")
        await manager.run_subagent(
            subagent_id=child["subagent_id"], task=CHILD_TASK, wait=False
        )
        await asyncio.sleep(0.05)

    loop.run_until_complete(plant())
    loop.close()
    del loop, plant, manager, llm


def main() -> int:
    print(f"Python {sys.version.split()[0]}")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="sink261_"))
    _plant(tmp)
    # NOTE：此处**不得** GC——遗留 task 必须活到 live run 的 gc.collect() 才有污染。

    llm = _ProbeLLM()
    manager = _manager(tmp, llm)
    llm.mgr = manager
    live_rec = TraceRecorder(task_id="LIVE-recorder")
    asyncio.run(
        _root(manager, AgentMode.READ_ONLY).run(
            [Message(role="user", content=LIVE_ROOT)], on_event=None,
            trace_recorder=live_rec,
        )
    )
    obs = getattr(llm, "obs", {})
    live_steps = [s.data for s in live_rec.steps if s.type == "sandbox"]

    print()
    print("--- observed ---")
    for k in ("sink_before", "sink_after", "sink_clobbered", "clobbered_to"):
        print(f"  {k}: {obs.get(k)!r}")
    print(f"  LIVE trace 收到 sandbox 事件: {live_steps}")

    print()
    if not obs.get("sink_clobbered"):
        print(">>> 未复现：遗留 task 的收尾没有改变后续 run 的 sandbox sink。")
        return 0
    to = obs.get("clobbered_to")
    print(f">>> 复现：遗留 pending run 的跨上下文收尾覆盖了后续 run 的 sandbox sink"
          f"（-> {to}）")
    if to == NoopSandboxSink.__name__:
        print("    可观测性：覆盖为 _NOOP（默认值）——后续 run 之后发出的 sandbox 事件"
              "将**静默丢失**（不写进任何 trace）。")
    else:
        print("    可观测性：覆盖为**过期真 sink**——后续 run 的 sandbox 事件"
              "将**串写进别的 run 的 trace**。")
    print(f"    本 run 的事件是否落入自己的 trace：{bool(live_steps)}")
    return 1


sys.exit(main())

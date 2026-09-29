"""issue #264 复现（源自 #261 派生调查）（变体 B）：`set_sandbox_sink` 的污染能否把后续 run 的
sandbox 事件**串写进另一个 run 的 trace**？

构造（实测确定性，见下「复现要点」）：

1. 一个**带 recorder 的旧 root run**（OLD）在其轮次内派生一个会挂住的子 run；
   该子 run 的 enqueue 上下文经 `copy_context()` 携带 OLD recorder 的
   `TraceRecorderSandboxSink`（即「过期真 sink」）。关闭该 root run 的 event loop，
   并**删除 manager/root/loop 的引用**，使遗留子 run 变为可回收。
2. 一个**带自己 recorder 的 live root run**（LIVE）在自己的轮次里 `gc.collect()`
   终结那个遗留子 run —— 它的收尾 `set_sandbox_sink(previous)` 把 LIVE 的 sink
   覆盖成 **OLD 的过期 sink**。
3. 之后 LIVE run 发出 sandbox 事件 → 检查它落到了哪个 trace。

**复现要点（实测）**：plant 阶段结束后必须 `del mgr_old`（以及 root/loop）。若
manager 仍被引用，其 `_active_tasks` 会一直持有遗留 task，task 永不终结、也就不会
触发收尾污染。此脚本**不用** `asyncio.set_event_loop`（那会把旧 loop 保活到 live
阶段，反而把终结时机挪到无害的上下文）。

**对照（control）**：置 `PLANT_ABANDONED = False`（不派生遗留子 run）——实测 LIVE
事件正确落入 LIVE trace，证明「串写」确由遗留子 run 的收尾引起。

输出：LIVE / OLD 两个 trace 各自收到的 sandbox 事件。退出码 1 = 出现串写。
本脚本**只读**生产代码。
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
from agent.sandbox_events import emit_sandbox_event  # noqa: E402
from agent.subagent.manager import SubAgentManager  # noqa: E402
from agent.trace_recorder import TraceRecorder  # noqa: E402
from agent.tools.registry import ToolRegistry  # noqa: E402
from agent.workspace_policy import WorkspacePolicy  # noqa: E402

PLANT_ROOT = "__MISROUTE_PLANT__"
CHILD_TASK = "__MISROUTE_CHILD__"

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

LIVE_ROOT = "__MISROUTE_LIVE__"

#: 置 False 即变为对照：不派生遗留子 run。
PLANT_ABANDONED = True


def _last_user(messages) -> str:
    for m in reversed(messages):
        if getattr(m, "role", None) == "user":
            return getattr(m, "content", "") or ""
    return ""


class _LLM:
    model = "misroute-probe"

    def __init__(self) -> None:
        self.mgr: SubAgentManager | None = None

    async def chat(self, messages, tools=None, model="gpt-4"):
        text = _last_user(messages)
        if CHILD_TASK in text:
            await asyncio.sleep(9999)              # 遗留子 run 在此挂起
        if PLANT_ROOT in text and PLANT_ABANDONED and self.mgr is not None:
            child = self.mgr.create_subagent(name="abandoned", mode="build")
            await self.mgr.run_subagent(
                subagent_id=child["subagent_id"], task=CHILD_TASK, wait=False
            )
            await asyncio.sleep(0.05)
        if LIVE_ROOT in text:
            gc.collect()                           # 在 LIVE 的 sink 窗口内终结遗留 task
            emit_sandbox_event("denied", command="rm -rf /", reason="live")
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


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="misroute261_"))
    llm = _LLM()

    # --- 阶段一：带 recorder 的旧 root run（可选：派生会挂住的遗留子 run） ---
    mgr_old = _manager(tmp, llm)
    llm.mgr = mgr_old
    old_rec = TraceRecorder(task_id="OLD-recorder")
    root_old = _root(mgr_old, AgentMode.BUILD)
    loop_old = asyncio.new_event_loop()
    loop_old.run_until_complete(
        root_old.run([Message(role="user", content=PLANT_ROOT)], on_event=None,
                     trace_recorder=old_rec)
    )
    loop_old.close()
    # 删除引用：使遗留子 run 变为可回收（见模块 docstring 的「复现要点」）。
    del loop_old, root_old, mgr_old

    # --- 阶段二：带 recorder 的 live root run ---
    mgr_live = _manager(tmp, llm)
    llm.mgr = mgr_live
    live_rec = TraceRecorder(task_id="LIVE-recorder")
    root_live = _root(mgr_live, AgentMode.READ_ONLY)
    asyncio.run(
        root_live.run([Message(role="user", content=LIVE_ROOT)], on_event=None,
                      trace_recorder=live_rec)
    )

    live_steps = [s.data for s in live_rec.steps if s.type == "sandbox"]
    old_steps = [s.data for s in old_rec.steps if s.type == "sandbox"]
    print(f"Python {sys.version.split()[0]}  PLANT_ABANDONED={PLANT_ABANDONED}")
    print(f"  LIVE recorder sandbox steps : {live_steps}")
    print(f"  OLD  recorder sandbox steps : {old_steps}")

    misrouted = bool(old_steps) and not live_steps
    if misrouted:
        print(">>> 串写复现：LIVE run 的 sandbox 事件落进了 OLD recorder 的 trace。")
        return 1
    print(">>> 无串写：LIVE 事件落在 LIVE trace（对照或未触发）。")
    return 0


sys.exit(main())

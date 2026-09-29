"""issue #264 复现（形态 B 的确定性变体）：串写进旧 run 的 trace。

与同目录 `sandbox_sink_misroute.py`（#261 归档版本，路径适配）**只差一行**：
本脚本在 plant 阶段丢弃引用后追加一次 `gc.collect()`。这一行把
「遗留 task 何时被终结」从「取决于 CPython 分代回收时机」变成确定性事件，
使串写在本机 **5/5** 稳定复现；而归档原版在本机 **0/10**（见 change 的
`diagnosis.md` 的 `## Reproduction` 第 2 节）。

本脚本存在的意义是**证据**：证明归档脚本的不复现是**脚本的 GC 时机脆弱**，
不是缺陷本身变了——同一份生产代码，仅 GC 时机不同，串写就从隐到显。

对照（control）：`PLANT_ABANDONED = False`（不派生遗留子 run）——LIVE 事件
正确落入 LIVE trace，证明串写确由遗留子 run 的跨上下文收尾引起。

退出码：1 = 串写复现；0 = 未复现。
本脚本**只读**生产代码。
"""
from __future__ import annotations

import asyncio
import gc
import pathlib
import sys
import tempfile


def _find_repo_root(start: pathlib.Path) -> pathlib.Path:
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

PLANT_ROOT = "__MISROUTE_GCW_PLANT__"
CHILD_TASK = "__MISROUTE_GCW_CHILD__"
LIVE_ROOT = "__MISROUTE_GCW_LIVE__"

#: 置 False 即变为对照：不派生遗留子 run。
PLANT_ABANDONED = True


def _last_user(messages) -> str:
    for m in reversed(messages):
        if getattr(m, "role", None) == "user":
            return getattr(m, "content", "") or ""
    return ""


class _LLM:
    model = "misroute-gcwindow-probe"

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
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="misroute_gcw264_"))
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
    del loop_old, root_old, mgr_old
    # 本脚本相对归档原版的**唯一**差异：在这里强制一次回收，把遗留 task 的
    # 终结时机钉死，使 LIVE 窗口内的 gc.collect() 确定性地命中它。
    gc.collect()

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
        print("    即一条安全拒绝事件被记进了**错误的 trace**（审计证据污染）。")
        return 1
    print(">>> 无串写：LIVE 事件落在 LIVE trace（对照或未触发）。")
    return 0


sys.exit(main())

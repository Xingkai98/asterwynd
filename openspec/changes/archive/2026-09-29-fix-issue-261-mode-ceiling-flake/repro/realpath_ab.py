"""Deterministic A/B on the REAL production code path for issue #261.

Faithful to the CI failure:
  1. A subagent run is started (SubAgentManager.run_subagent, wait=False) on an
     event loop that is then closed WITHOUT cancelling it -- exactly the CI
     "Task was destroyed but it is pending!" population.
  2. A LATER, unrelated run (the failing test's read_only session) is started on
     a fresh loop and forced to GC at the scheduler dispatch point.
  3. If the abandoned run's mount-A `finally` is carried into the live context,
     the live node freezes as 'build' (static fallback) instead of 'read_only'.

Uses the real AgentLoop / SubAgentManager / WorkflowScheduler; no production edit.
Exit code 1 = polluted (reproduced), 0 = clean.
"""
import asyncio
import gc
import pathlib
import sys
import tempfile

sys.path.insert(0, "/home/happy/.paseo/worktrees/0frj3kg8/fix-issue-261-mode-ceiling-flake-2026-09-29")

from agent.config import AsterwyndConfig           # noqa: E402
from agent.llm import LLMResponse, Usage           # noqa: E402
from agent.loop import AgentLoop                   # noqa: E402
from agent.message import Message                  # noqa: E402
from agent.run_config import AgentMode, AgentRunConfig  # noqa: E402
from agent.subagent.bus import MessageBus          # noqa: E402
from agent.subagent.context import current_mode_ceiling  # noqa: E402
from agent.subagent.manager import SubAgentManager  # noqa: E402
from agent.subagent.scheduler import WorkflowScheduler  # noqa: E402
from agent.subagent.workflow import parse_workflow_spec  # noqa: E402
from agent.tools.registry import ToolRegistry      # noqa: E402
from agent.workspace_policy import WorkspacePolicy  # noqa: E402

ROOT = "READ_ONLY_SESSION"
CHILD = "CHILD_TASK"


class _HangLLM:
    """Root returns immediately; subagent runs hang forever (stay pending)."""

    model = "mode-ceiling-test"

    async def chat(self, messages, tools=None, model="gpt-4"):
        text = ""
        for m in reversed(messages):
            if getattr(m, "role", None) == "user":
                text = getattr(m, "content", "") or ""
                break
        if CHILD in text or ROOT not in text:
            await asyncio.sleep(9999)               # subagent run: never completes
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))


def _manager(tmp, llm):
    return SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp),
    )


def plant_abandoned_run(tmp):
    """Start a subagent run on its own loop, then close the loop with it pending."""
    llm = _HangLLM()
    mgr = _manager(tmp, llm)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def go():
        child = mgr.create_subagent(name="abandoned", mode="build")
        await mgr.run_subagent(subagent_id=child["subagent_id"], task=CHILD, wait=False)
        await asyncio.sleep(0.05)                   # let the run reach its LLM await

    loop.run_until_complete(go())
    loop.close()                                    # NOT cancelled -> pending forever
    del loop, go
    # mgr + llm still referenced by the coroutine frames; drop them too
    del mgr, llm
    return None


def live_test(tmp):
    """The real `test_next_run_after_switch_uses_new_mode` body, with the
    scheduler dispatch instrumented to gc.collect() at the vulnerable moment."""
    llm = _HangLLM()
    mgr = _manager(tmp, llm)
    loop = AgentLoop(
        llm=mgr.llm, tool_registry=ToolRegistry(), subagent_manager=mgr,
        expose_subagent_tools=True, run_config=AgentRunConfig(mode=AgentMode.READ_ONLY),
    )

    async def chat(messages, tools=None, model="gpt-4"):
        if ROOT in _last_user(messages):
            # dispatch a graph from inside the real run (mount A == read_only)
            sched = WorkflowScheduler(mgr, bus=MessageBus())
            mgr.register_workflow(sched)

            async def dispatch():
                gc.collect()                        # finalise the abandoned task HERE
                return await sched.run(parse_workflow_spec(_spec()))
            await dispatch()
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    mgr.llm.chat = chat
    asyncio.run(loop.run([Message(role="user", content=ROOT)], on_event=None))
    return {s["name"]: s["mode"] for s in mgr.list_subagents()}


def _last_user(messages):
    for m in reversed(messages):
        if getattr(m, "role", None) == "user":
            return getattr(m, "content", "") or ""
    return ""


def _spec():
    return {"goal": "g", "nodes": [{"id": "bw", "kind": "subagent", "task": "t", "mode": "build"}], "edges": []}


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="real261_"))
    plant_abandoned_run(tmp)
    modes = live_test(tmp)
    got = modes.get("bw")
    print(f"Python {sys.version.split()[0]}  node 'bw' frozen as: {got!r}  (expected 'read_only')")
    if got != "read_only":
        print(">>> REPRODUCED: live read_only ceiling clobbered by an abandoned run's restore")
        return 1
    print(">>> CLEAN: ceiling preserved")
    return 0


sys.exit(main())

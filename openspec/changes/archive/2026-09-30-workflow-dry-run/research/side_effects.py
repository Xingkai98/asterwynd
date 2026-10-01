"""#273 spike: measure the side-effect surface of a plain scheduler.run().

Answers:
  Q1. What lands on disk under workspace_root?
  Q2. Does graph_sink=None alone make it side-effect free?  (default is already None)
  Q3. What does the manager registry look like after run()?
  Q4. Can we observe received / delivered / input_seen from NodeState alone?
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/happy/my-agent/.claude/worktrees/workflow-dry-run")

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class EchoLLM:
    """Echoes what it received, tagged with the first line of the task.

    This is the prototype 'fake LLM' from the issue: the echo makes the data
    flow visible, but node identity has to come from the task text.
    """

    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.calls.append(text)
        first = (text.strip().splitlines() or ["<empty>"])[0]
        return LLMResponse(
            content=f"PRODUCED-BY<{first[:40]}>", stop_reason="end_turn", usage=Usage(5, 5)
        )


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "w1", "kind": "subagent", "task": "TASK-W1 write draft"},
        {"id": "w2", "kind": "subagent", "task": "TASK-W2 write draft"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        {"id": "gate", "kind": "route", "cases": [{"when": "GAPS: none", "to": "report"},
                                                  {"when": "GAPS", "to": "rework"}],
         "default": "report"},
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK redo"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT final"},
    ],
    "edges": [
        {"from": "w1", "to": "merge", "reducer": "concat"},
        {"from": "w2", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
    ],
    "terminal": ["report"],
}


def snapshot(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            try:
                out[str(p.relative_to(root))] = p.stat().st_size
            except OSError:
                pass
    return out


async def main():
    work = Path("/tmp/spike273/ws")
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=False)
    work.mkdir(parents=True, exist_ok=True)
    (work / "sentinel.txt").write_text("keep me\n")

    before = snapshot(work)

    llm = EchoLLM()
    mgr = SubAgentManager(
        llm=llm,
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=work),
    )
    print(f"[init] graph_sink default = {mgr.graph_sink!r}")
    print(f"[init] manager._workflows = {mgr._workflows}")
    print(f"[init] manager._workflow_stores = {getattr(mgr, '_workflow_stores', 'MISSING')}")

    sched = WorkflowScheduler(mgr)
    result = await sched.run(parse_workflow_spec(SPEC))

    after = snapshot(work)
    print("\n=== RESULT ===")
    print(f"status={result['status']} completed={result.get('completed')}")

    print("\n=== DISK DELTA under workspace_root ===")
    for k in sorted(set(after) - set(before)):
        print(f"  + {k}  ({after[k]}B)")
    if not (set(after) - set(before)):
        print("  (nothing new)")

    print("\n=== SENTINEL INTACT? ===")
    print("  sentinel.txt =", (work / "sentinel.txt").read_text().strip())

    print("\n=== MANAGER REGISTRY AFTER RUN ===")
    print(f"  _workflows = {list(mgr._workflows.keys())}")
    print(f"  _workflow_stores = {list(getattr(mgr, '_workflow_stores', {}).keys())}")
    print(f"  spawn buckets = {list(mgr._workflow_spawn_counts.keys())}")

    print("\n=== NODE STATE (what a dry-run report could show) ===")
    for nid, st in sched._states.items():
        print(f"  [{nid}] kind={st.node.kind} status={st.status} runs={st.runs}")
        print(f"        summary={st.summary[:70]!r}")
        if st.slots:
            print(f"        slots={ {k: v[:50] for k, v in st.slots.items()} }")
        if st.node.kind == "route":
            print(f"        verdict={st.verdict!r} raw={st.raw[:60]!r} targets={st.targets}")

    print("\n=== LLM CALLS (the thing dry-run must eliminate) ===")
    print(f"  total = {len(llm.calls)}")
    for i, c in enumerate(llm.calls):
        print(f"  --- call {i} ---")
        for line in c.strip().splitlines():
            print(f"      {line[:120]}")

    print("\n=== EVENTS WRITTEN ===")
    store = mgr.workflow_store(sched.workflow_id)
    ev = store.root / "events.jsonl"
    if ev.exists():
        print(f"  {ev} ({ev.stat().st_size}B, {len(ev.read_text().strip().splitlines())} lines)")
    else:
        print(f"  events.jsonl not found under {store.root}")


asyncio.run(main())

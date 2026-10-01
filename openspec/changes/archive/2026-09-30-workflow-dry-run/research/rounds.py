"""#273 spike 9: can a scripted dry run answer the LOOP probes?

Probe #3 from #248: "route 重新求值时看 LATEST 还是累积旧输出"
Probe #5: "回边是否携带上游文本"

Test: script the critic to say GAPS on call 1 and "GAPS: none" on call 2, and
watch whether the loop (a) actually iterates, (b) shows what the re-run node
receives on lap 2, (c) terminates.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/happy/my-agent/.claude/worktrees/workflow-dry-run")

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.context import current_node_id
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class SeqScriptedLLM:
    """Per-node SEQUENCE of outputs: the nth call to a node returns the nth item.

    This is what lets a model ask "what happens on lap 2 of the loop".
    """

    def __init__(self, script: dict[str, list[str]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.counts: dict[str, int] = {}
        self.seen: dict[str, list[str]] = {}

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id() or "?"
        n = self.counts.get(node, 0)
        self.counts[node] = n + 1
        received = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                received = c
        self.seen.setdefault(node, []).append(received)
        seq = self.script.get(node)
        if seq:
            out = seq[min(n, len(seq) - 1)]
        else:
            out = f"[{node} lap{n+1} auto]"
        return LLMResponse(content=out, stop_reason="end_turn", usage=Usage(0, 0))


class NullStore:
    def __init__(self, workflow_id="dry"):
        self.workflow_id = workflow_id
        self.root = Path("/dev/null")

    def ref(self, k):
        return f"artifact://workflow/{self.workflow_id}/{k}"

    def save_result(self, k, t):
        return self.ref(k)

    def save_summary(self, k, t):
        return self.ref(f"{k}.summary")

    def save_transcript(self, k, m):
        return self.ref(f"{k}.transcript")

    def save_attribution(self, k, p):
        return self.ref(f"{k}.attribution")

    def append_event(self, e):
        pass


SPEC = {
    "goal": "review",
    "nodes": [
        {"id": "producer", "kind": "subagent", "task": "write a proposal"},
        {"id": "reviewer", "kind": "subagent", "task": "review it"},
        {"id": "gate", "kind": "route", "max_routes": 5,
         "cases": [{"when": "APPROVED", "to": "done"}],
         "default": "producer"},
        {"id": "done", "kind": "subagent", "task": "finalize"},
    ],
    "edges": [
        {"from": "producer", "to": "reviewer"},
        {"from": "reviewer", "to": "gate"},
        {"from": "gate", "to": "done"},
        {"from": "gate", "to": "producer"},   # route back-edge
    ],
    "entry": ["producer"],
    "terminal": ["done"],
}


async def main():
    ws = Path("/tmp/spike273/roundsws")
    ws.mkdir(parents=True, exist_ok=True)
    llm = SeqScriptedLLM({
        "reviewer": ["CRITIQUE: needs more tests", "CRITIQUE: still gaps", "APPROVED"],
    })
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    result = await sched.run(parse_workflow_spec(SPEC))

    print(f"run_status={result['status']}")
    print("\n=== call counts per node (does the loop actually iterate?) ===")
    for n, c in llm.counts.items():
        print(f"  {n}: {c} calls")

    print("\n=== producer on lap 1 vs lap 2 (back-edge data flow) ===")
    for i, txt in enumerate(llm.seen.get("producer", [])):
        print(f"  --- producer lap {i+1} received ---")
        for line in txt.strip().splitlines():
            print(f"      | {line[:100]}")

    print("\n=== reviewer on lap 3 (upstream text on last lap) ===")
    seen = llm.seen.get("reviewer", [])
    if seen:
        for line in seen[-1].strip().splitlines():
            print(f"      | {line[:100]}")

    print("\n=== node states ===")
    for nid, st in sched._states.items():
        print(f"  [{nid:9}] {st.node.kind:9} {st.status:10} runs={st.runs}")
    g = sched._states["gate"]
    print(f"  gate: matched={g.verdict!r} targets={g.targets} raw={g.raw!r}")


asyncio.run(main())

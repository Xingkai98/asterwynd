"""#273 spike 5: WHAT does a route actually read?

Probe question from #248 verbatim: "route 读的是中间节点自身输出还是上游输入"

Build the minimal chain  a(subagent) -> mid(subagent) -> gate(route)  and print
every candidate value so the answer is unambiguous.
"""
import asyncio
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


class ScriptedLLM:
    def __init__(self, script):
        self.script = script

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id() or "?"
        out = self.script.get(node, f"[auto:{node}]")
        return LLMResponse(content=out, stop_reason="end_turn", usage=Usage(5, 5))


class NullStore:
    def __init__(self, workflow_id="dry"):
        self.workflow_id = workflow_id
        self.root = Path("/dev/null")

    def ref(self, key):
        return f"artifact://workflow/{self.workflow_id}/{key}"

    def save_result(self, key, text):
        return self.ref(key)

    def save_summary(self, key, text):
        return self.ref(f"{key}.summary")

    def save_transcript(self, key, messages):
        return self.ref(f"{key}.transcript")

    def save_attribution(self, key, payload):
        return self.ref(f"{key}.attribution")

    def append_event(self, event):
        pass


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "TASK-a"},
        {"id": "mid", "kind": "subagent", "task": "TASK-mid"},
        {"id": "gate", "kind": "route",
         "cases": [{"when": "MID-SAYS-A", "to": "yes"},
                   {"when": "UPSTREAM-SAYS-A", "to": "also_yes"}],
         "default": "no"},
        {"id": "yes", "kind": "subagent", "task": "TASK-yes"},
        {"id": "also_yes", "kind": "subagent", "task": "TASK-also_yes"},
        {"id": "no", "kind": "subagent", "task": "TASK-no"},
    ],
    "edges": [
        {"from": "a", "to": "mid"},
        {"from": "mid", "to": "gate"},
        {"from": "gate", "to": "yes"},
        {"from": "gate", "to": "also_yes"},
        {"from": "gate", "to": "no"},
    ],
    "terminal": ["yes", "also_yes", "no"],
}


async def main():
    ws = Path("/tmp/spike273/routews")
    ws.mkdir(parents=True, exist_ok=True)
    llm = ScriptedLLM({
        "a": "UPSTREAM-SAYS-A",       # what a produces
        "mid": "MID-SAYS-A",          # what mid produces
    })
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec(SPEC))

    print("=== candidate values ===")
    a = sched._states["a"]
    mid = sched._states["mid"]
    gate = sched._states["gate"]
    print(f"  a.summary       = {a.summary!r}")
    print(f"  a.slots         = {a.slots}")
    print(f"  mid.summary     = {mid.summary!r}")
    print(f"  mid.slots       = {mid.slots}")
    print(f"  gate.raw        = {gate.raw!r}   <-- what the route actually matched against")
    print(f"  gate.verdict    = {gate.verdict!r}")
    print(f"  gate.targets    = {gate.targets}")

    print("\n=== verdict ===")
    if gate.raw == "MID-SAYS-A":
        print("  route reads the DIRECT UPSTREAM NODE's own output (mid)")
    elif "UPSTREAM-SAYS-A" in (gate.raw or ""):
        print("  route reads a FURTHER-UP text (a's output) -- NOT mid's own output")
    else:
        print(f"  unexpected: {gate.raw!r}")

    print("\n=== node kinds & outputs default ===")
    for nid, st in sched._states.items():
        print(f"  [{nid:9}] kind={st.node.kind:9} outputs={st.node.outputs} status={st.status}")


asyncio.run(main())

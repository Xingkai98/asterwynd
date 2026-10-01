"""#273 spike 8: pin down EXACTLY what a route reads.

Observed in the prototype: with  merge(aggregate) -> critic(subagent) -> gate(route),
the gate's input_seen was MERGE's concatenated output, not critic's own output.

Is that real?  Compare three shapes side by side.
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
        return LLMResponse(content=self.script.get(node, f"[{node}]"),
                           stop_reason="end_turn", usage=Usage(0, 0))


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


async def probe(label, nodes, edges, entry, terminal, script):
    ws = Path(f"/tmp/spike273/cr-{label}")
    ws.mkdir(parents=True, exist_ok=True)
    mgr = SubAgentManager(
        llm=ScriptedLLM(script), config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec({
        "goal": "g", "nodes": nodes, "edges": edges,
        "entry": entry, "terminal": terminal,
    }))
    print(f"\n### {label}")
    for nid, st in sched._states.items():
        if st.node.kind == "route":
            print(f"  gate.input_seen = {st.raw!r}")
            print(f"  gate.matched    = {st.verdict!r} -> {st.targets}")
    return sched


async def main():
    # Shape 1: plain chain of subagents a -> mid -> gate
    await probe(
        "1. subagent -> subagent -> route   (no slots anywhere)",
        [{"id": "a", "kind": "subagent", "task": "ta"},
         {"id": "mid", "kind": "subagent", "task": "tm"},
         {"id": "gate", "kind": "route",
          "cases": [{"when": "FROM-MID", "to": "x"}, {"when": "FROM-A", "to": "y"}],
          "default": "z"},
         {"id": "x", "kind": "subagent", "task": "tx"},
         {"id": "y", "kind": "subagent", "task": "ty"},
         {"id": "z", "kind": "subagent", "task": "tz"}],
        [{"from": "a", "to": "mid"}, {"from": "mid", "to": "gate"},
         {"from": "gate", "to": "x"}, {"from": "gate", "to": "y"},
         {"from": "gate", "to": "z"}],
        ["a"], ["x", "y", "z"],
        {"a": "FROM-A", "mid": "FROM-MID"},
    )

    # Shape 2: aggregate -> subagent -> gate  (the prototype case)
    await probe(
        "2. aggregate -> subagent -> route  (aggregate carries slots)",
        [{"id": "leaf", "kind": "subagent", "task": "tl"},
         {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
         {"id": "critic", "kind": "subagent", "task": "tc"},
         {"id": "gate", "kind": "route",
          "cases": [{"when": "FROM-CRITIC", "to": "x"}, {"when": "FROM-LEAF", "to": "y"}],
          "default": "z"},
         {"id": "x", "kind": "subagent", "task": "tx"},
         {"id": "y", "kind": "subagent", "task": "ty"},
         {"id": "z", "kind": "subagent", "task": "tz"}],
        [{"from": "leaf", "to": "agg", "reducer": "concat"},
         {"from": "agg", "to": "critic"}, {"from": "critic", "to": "gate"},
         {"from": "gate", "to": "x"}, {"from": "gate", "to": "y"},
         {"from": "gate", "to": "z"}],
        ["leaf"], ["x", "y", "z"],
        {"leaf": "FROM-LEAF", "critic": "FROM-CRITIC"},
    )

    # Shape 3: same as 2, but the critic writes into its own slot
    await probe(
        "3. aggregate -> subagent(outputs=...) -> route",
        [{"id": "leaf", "kind": "subagent", "task": "tl"},
         {"id": "agg", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
         {"id": "critic", "kind": "subagent", "task": "tc", "outputs": ["verdict_slot"]},
         {"id": "gate", "kind": "route",
          "cases": [{"when": "FROM-CRITIC", "to": "x"}, {"when": "FROM-LEAF", "to": "y"}],
          "default": "z"},
         {"id": "x", "kind": "subagent", "task": "tx"},
         {"id": "y", "kind": "subagent", "task": "ty"},
         {"id": "z", "kind": "subagent", "task": "tz"}],
        [{"from": "leaf", "to": "agg", "reducer": "concat"},
         {"from": "agg", "to": "critic"}, {"from": "critic", "to": "gate"},
         {"from": "gate", "to": "x"}, {"from": "gate", "to": "y"},
         {"from": "gate", "to": "z"}],
        ["leaf"], ["x", "y", "z"],
        {"leaf": "FROM-LEAF", "critic": "FROM-CRITIC"},
    )


asyncio.run(main())

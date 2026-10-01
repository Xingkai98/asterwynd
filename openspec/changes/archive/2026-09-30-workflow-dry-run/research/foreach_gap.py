"""#273 spike 10: the foreach gap.

D3 keys `script` by node id.  But a foreach node expands into N items, each of
which is its own run.  Two questions:

  Q-A. Does current_node_id() differ per item?  (if not, script can't target them)
  Q-B. Does the naive "received keyed by node id" dict COLLIDE across items?
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
    def __init__(self, script=None):
        self.script = script or {}
        self.calls = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id() or "?"
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.calls.append((node, text))
        out = self.script.get(node, f"[{node} auto]")
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
    "goal": "g",
    "nodes": [
        {"id": "fan", "kind": "foreach", "items": ["alpha", "beta", "gamma"],
         "task": "propose {item}"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["m"]},
    ],
    "edges": [{"from": "fan", "to": "merge", "reducer": "concat"}],
    "terminal": ["merge"],
}


async def main():
    ws = Path("/tmp/spike273/fg")
    ws.mkdir(parents=True, exist_ok=True)

    llm = ScriptedLLM({"fan": "SCRIPTED-FOR-FAN"})
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec(SPEC))

    print("=== Q-A: what node id does each item's LLM call see? ===")
    for i, (node, text) in enumerate(llm.calls):
        first = text.strip().splitlines()[0] if text.strip() else ""
        print(f"  call {i}: node_id={node!r}  task_first_line={first!r}")

    print("\n=== Q-B: naive 'received keyed by node id' dict ===")
    received = {}
    for node, text in llm.calls:
        received[node] = text   # <-- last-wins collision
    print(f"  keys = {list(received)}")
    print(f"  fan.received = {received.get('fan','')[:80]!r}")
    print(f"  => 3 items collapsed into {len([n for n,_ in llm.calls if n=='fan'])} slot(s)")

    print("\n=== the 'fan' node state ===")
    st = sched._states["fan"]
    print(f"  items={st.items} runs={st.runs} status={st.status}")
    print(f"  summary={st.summary[:100]!r}")

    print("\n=== does script['fan'] hit ALL items identically? ===")
    print("  (all three items would get 'SCRIPTED-FOR-FAN' — no per-item control)")


asyncio.run(main())

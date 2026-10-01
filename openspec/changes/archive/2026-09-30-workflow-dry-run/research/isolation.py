"""#273 spike 2: test the candidate isolation architecture.

Architecture under test:
  - dedicated SubAgentManager (throwaway, never registered anywhere)
  - graph_sink stays None (default)
  - workspace_policy.workspace_root -> a throwaway tmp dir
  - a NullStore substituted for WorkflowStore  (the only writer)
  - a fake LLM whose reply echoes what it received

Measures: (a) disk delta on the REAL workspace, (b) whether the fake LLM's
prompt captures "what this node actually received", (c) whether a route's
data/control edge distinction shows up.
"""
import asyncio
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

REAL_WS = Path("/tmp/spike273/ws")


class NullStore:
    """Drop-in for WorkflowStore: every write is a no-op, returns a fake ref."""

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


class EchoLLM:
    """The prototype fake LLM: echo the received prompt, tagged by first line.

    Returns TEXT ONLY (no tool calls) so the scheduler's run pipeline finishes
    the way it would for any well-behaved subagent.
    """

    def __init__(self):
        self.prompts = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.prompts.append(text)
        first = (text.strip().splitlines() or ["<empty>"])[0][:30]
        return LLMResponse(
            content=f"[echo of {first}]", stop_reason="end_turn", usage=Usage(5, 5)
        )


# A spec whose second half exercises data edges directly (no route in between)
SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "w1", "kind": "subagent", "task": "TASK-W1"},
        {"id": "w2", "kind": "subagent", "task": "TASK-W2"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
        {"id": "gate", "kind": "route",
         "cases": [{"when": "GAPS: none", "to": "report"}, {"when": "GAPS", "to": "rework"}],
         "default": "report"},
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "recheck", "kind": "subagent", "task": "TASK-RECHECK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "w1", "to": "merge", "reducer": "concat"},
        {"from": "w2", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "critic"},
        {"from": "critic", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
        {"from": "rework", "to": "recheck"},
        {"from": "recheck", "to": "critic"},   # back-edge, data edge
    ],
    "entry": ["w1", "w2", "rework"],
    "terminal": ["report"],
}


def snapshot(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.stat().st_size
    return out


async def main():
    if REAL_WS.exists():
        subprocess.run(["rm", "-rf", str(REAL_WS)], check=False)
    REAL_WS.mkdir(parents=True, exist_ok=True)
    (REAL_WS / "sentinel.txt").write_text("keep me\n")
    before = snapshot(REAL_WS)

    sandbox_ws = Path("/tmp/spike273/dryws")
    if sandbox_ws.exists():
        subprocess.run(["rm", "-rf", str(sandbox_ws)], check=False)
    sandbox_ws.mkdir(parents=True, exist_ok=True)

    llm = EchoLLM()
    mgr = SubAgentManager(
        llm=llm,
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=sandbox_ws),
    )
    sched = WorkflowScheduler(mgr)
    # The isolation substitution:
    sched._store = NullStore(sched.workflow_id)

    result = await sched.run(parse_workflow_spec(SPEC))

    after = snapshot(REAL_WS)
    print(f"status={result['status']} completed={result.get('completed')}")
    print(f"\n=== REAL WORKSPACE DISK DELTA ===")
    new = set(after) - set(before)
    print(f"  new files: {sorted(new) if new else '(none)'}")
    print(f"  sentinel intact: {(REAL_WS/'sentinel.txt').read_text().strip()!r}")
    print(f"  sandbox dir files: {len(list(sandbox_ws.rglob('*')))}")

    print("\n=== WHAT EACH NODE ACTUALLY RECEIVED (from LLM prompts) ===")
    for i, p in enumerate(llm.prompts):
        print(f"  --- LLM call {i} ---")
        for line in p.strip().splitlines():
            print(f"      | {line[:110]}")

    print("\n=== ROUTE STATE ===")
    for nid, st in sched._states.items():
        if st.node.kind == "route":
            print(f"  [{nid}] verdict={st.verdict!r} targets={st.targets}")
            print(f"        raw (input_seen) = {st.raw!r}")

    print("\n=== REPORT NODE (reached via route control edge) ===")
    rp = sched._states["report"]
    print(f"  status={rp.status} summary={rp.summary!r} slots={rp.slots}")
    print(f"  => report received NO data from gate? check its LLM call above")


asyncio.run(main())

"""#273 spike 4: the candidate FINAL design — scripted fake LLM.

Hypothesis: the dry run is far more useful if the model can say
"pretend node X outputs Y" and then SEE where Y goes.  That turns the tool from
"happy-path sketch" into "answer any what-if about data flow", with zero tokens
and fully deterministic.

Also covers: foreach expansion, route via $ref slot, and a cost measurement on a
bigger graph.
"""
import asyncio
import sys
import time
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
    """Per-node scripted output.  Falls back to echoing what it received."""

    def __init__(self, script: dict[str, str] | None = None):
        self.script = script or {}
        self.prompts: dict[str, str] = {}

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id() or "?"
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.prompts[node] = text
        if node in self.script:
            out = self.script[node]
        else:
            first = (text.strip().splitlines() or ["<empty>"])[0]
            out = f"[auto:{first[:24]}]"
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
    "goal": "review the design",
    "nodes": [
        {"id": "fan", "kind": "foreach", "items": ["a", "b", "c"],
         "source_field": "task", "task": "propose for $item"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
        {"id": "gate", "kind": "route",
         "cases": [{"when": "GAPS: none", "to": "report"}, {"when": "GAPS", "to": "rework"}],
         "default": "report"},
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "fan", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "critic"},
        {"from": "critic", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
        {"from": "rework", "to": "critic"},   # back-edge
    ],
    "entry": ["fan", "rework"],
    "terminal": ["report"],
}


async def run_once(script, label):
    ws = Path(f"/tmp/spike273/dryws4-{label}")
    ws.mkdir(parents=True, exist_ok=True)
    llm = ScriptedLLM(script)
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    t0 = time.time()
    result = await sched.run(parse_workflow_spec(SPEC))
    dt = time.time() - t0
    return sched, result, llm, dt


async def main():
    print("########## SCENARIO A: critic says APPROVED (GAPS: none) ##########")
    sched, result, llm, dt = await run_once(
        {"critic": "GAPS: none\nlooks good"}, "a")
    print(f"status={result['status']} completed={result.get('completed')} elapsed={dt:.3f}s")
    print("  node statuses:")
    for nid, st in sched._states.items():
        print(f"    [{nid:8}] {st.node.kind:9} {st.status:10} runs={st.runs}")
    g = sched._states["gate"]
    print(f"  gate: matched={g.verdict!r} targets={g.targets}")
    print(f"  report LLM prompt had input? {'Input from' in llm.prompts.get('report','')}")

    print("\n########## SCENARIO B: critic says GAPS (needs rework) ##########")
    called = {"critic": 0}

    class CountingScripted(ScriptedLLM):
        async def chat(self, messages, tools=None, model="gpt-4"):
            n = current_node_id()
            if n == "critic":
                called["critic"] += 1
                out = "GAPS: missing tests" if called["critic"] == 1 else "GAPS: none"
            elif n == "rework":
                out = "reworked!"
            else:
                out = None
            if out is not None:
                text = ""
                for m in messages:
                    c = getattr(m, "content", None)
                    if isinstance(c, str) and c:
                        text = c
                self.prompts[n] = text
                return LLMResponse(content=out, stop_reason="end_turn", usage=Usage(5, 5))
            return await super().chat(messages, tools, model)

    ws = Path("/tmp/spike273/dryws4-b")
    ws.mkdir(parents=True, exist_ok=True)
    llm = CountingScripted({})
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    t0 = time.time()
    result = await sched.run(parse_workflow_spec(SPEC))
    dt = time.time() - t0
    print(f"status={result['status']} completed={result.get('completed')} elapsed={dt:.3f}s")
    for nid, st in sched._states.items():
        print(f"    [{nid:8}] {st.node.kind:9} {st.status:10} runs={st.runs}")
    g = sched._states["gate"]
    print(f"  gate: matched={g.verdict!r} targets={g.targets}")
    print(f"  critic called {called['critic']} times")
    print(f"  rework LLM prompt: {llm.prompts.get('rework','<none>')!r}")


asyncio.run(main())

"""#273 spike 3: the two design crux questions.

Q-A. Can the fake LLM know WHICH node it is serving?  (needed so dry-run output
     can say "node w1 produced X" rather than "something produced X")
Q-B. How can a model dry-run a graph that has a ROUTE, given that a blind echo
     will never say "GAPS" and hence always takes `default`?
"""
import asyncio
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

# Where do these live?
from agent.subagent.context import current_node_id, current_workflow_id  # noqa: E402


class NodeAwareLLM:
    """Reads the node-id contextvar and tags its reply with it."""

    def __init__(self):
        self.prompts = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id()
        wf = current_workflow_id()
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.prompts.append((node, text))
        return LLMResponse(
            content=f"[OUTPUT-OF-NODE:{node} workflow={wf}]",
            stop_reason="end_turn", usage=Usage(5, 5),
        )


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "w1", "kind": "subagent", "task": "TASK-W1"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
        {"id": "gate", "kind": "route",
         "cases": [{"when": "GAPS: none", "to": "report"}, {"when": "GAPS", "to": "rework"}],
         "default": "report"},
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "w1", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "critic"},
        {"from": "critic", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
    ],
    "entry": ["w1", "rework"],
    "terminal": ["report"],
}


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


async def main():
    ws = Path("/tmp/spike273/dryws3")
    ws.mkdir(parents=True, exist_ok=True)
    llm = NodeAwareLLM()
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    result = await sched.run(parse_workflow_spec(SPEC))

    print(f"status={result['status']} completed={result.get('completed')}")
    print("\n=== Q-A: does the fake LLM see the node id? ===")
    for node, text in llm.prompts:
        print(f"  node={node!r}  first_task_line={text.strip().splitlines()[0]!r}")

    print("\n=== Q-B: route decision with a blind-but-node-aware echo ===")
    for nid, st in sched._states.items():
        if st.node.kind == "route":
            print(f"  [{nid}] matched={st.verdict!r} targets={st.targets}")
            print(f"        input_seen(raw)={st.raw!r}")

    print("\n=== resulting statuses ===")
    for nid, st in sched._states.items():
        print(f"  [{nid:8}] kind={st.node.kind:9} status={st.status:10} runs={st.runs}")


asyncio.run(main())

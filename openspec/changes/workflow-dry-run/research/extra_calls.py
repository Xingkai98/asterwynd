"""#273 spike 12: account for EVERY LLM call in a run.

foreach-llm-agg-20 reported 23 calls but 20 items + 1 aggregate = 21 expected.
Find the 2 extras and check what current_node_id() they see.
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


class CountingLLM:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id()
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        # record the first 2 lines of the SYSTEM-ish prompt to identify the caller
        head = "\n".join(text.strip().splitlines()[:2])[:90]
        self.calls.append((node, head, len(text)))
        return LLMResponse(content="X" * 50, stop_reason="end_turn", usage=Usage(0, 0))


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


async def run(spec, label):
    ws = Path(f"/tmp/spike273/extra-{label}")
    ws.mkdir(parents=True, exist_ok=True)
    llm = CountingLLM()
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec(spec))
    print(f"\n### {label}: {len(llm.calls)} calls")
    from collections import Counter
    by_node = Counter(n for n, _, _ in llm.calls)
    print(f"  by node_id: {dict(by_node)}")
    for i, (node, head, ln) in enumerate(llm.calls):
        if node is None or node == "?":
            print(f"  >>> call {i}: node_id={node!r}  prompt_head={head!r}  len={ln}")


async def main():
    await run({
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "items": [f"i{k}" for k in range(20)],
             "task": "work {item}"},
            {"id": "agg", "kind": "aggregate", "strategy": "llm"},
        ],
        "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
        "terminal": ["agg"],
    }, "foreach-llm-agg-20")

    # Also: does a collect aggregate with LARGE contributions trigger the summarizer?
    await run({
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "items": [f"i{k}" for k in range(20)],
             "task": "work {item}"},
            {"id": "agg", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
        "terminal": ["agg"],
    }, "foreach-collect-20")


asyncio.run(main())

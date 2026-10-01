"""#273 spike 13: does the collect-aggregate summarizer pollute the report?

Grill's claim: `_merge_contributions_bounded` -> `_aggregator.merge` -> LLMSummarizer
-> manager.llm.  In a dry run that's the FAKE llm, so the aggregate's reported
slot/summary becomes the fake's placeholder instead of the concatenation, and a
bogus node-id=None entry appears in the call log.
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


class EchoLLM:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id()
        text = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                text = c
        self.calls.append((node, len(text)))
        return LLMResponse(content=f"[{node} auto]", stop_reason="end_turn",
                           usage=Usage(0, 0))


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


async def run(leaf_chars, label):
    ws = Path(f"/tmp/spike273/sp-{label}")
    ws.mkdir(parents=True, exist_ok=True)
    llm = EchoLLM()

    class BigLLM(EchoLLM):
        async def chat(self, messages, tools=None, model="gpt-4"):
            node = current_node_id()
            text = ""
            for m in messages:
                c = getattr(m, "content", None)
                if isinstance(c, str) and c:
                    text = c
            self.calls.append((node, len(text)))
            # each regular node returns a long output; summarizer returns small
            if node in (None, "?"):
                return LLMResponse(content="[SUMMARY-PLACEHOLDER]", stop_reason="end_turn",
                                   usage=Usage(0, 0))
            return LLMResponse(content="L" * leaf_chars, stop_reason="end_turn",
                               usage=Usage(0, 0))

    llm = BigLLM()
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec({
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "ta"},
            {"id": "b", "kind": "subagent", "task": "tb"},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "a", "to": "root", "reducer": "concat"},
                  {"from": "b", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }))
    print(f"\n### {label}: leaf_chars={leaf_chars}")
    print(f"  LLM calls: {llm.calls}")
    unattributed = [c for c in llm.calls if c[0] in (None, "?")]
    print(f"  unattributed (node_id None/'?'): {len(unattributed)}")
    root = sched._states["root"]
    print(f"  root.summary[:60] = {root.summary[:60]!r}")
    print(f"  root.slots = {{k: v[:40] for k,v in root.slots.items()}}")
    if "SUMMARY-PLACEHOLDER" in (root.summary or ""):
        print("  >>> POLLUTED: aggregate output is the summarizer placeholder, not the concat")


async def main():
    await run(50, "small")       # under budget -> no summarizer
    await run(9000, "big")       # over budget -> summarizer fires


asyncio.run(main())

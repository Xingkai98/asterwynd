"""#273 spike 6: cost of a dry run on big graphs + budget/limit interactions."""
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
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(content=f"[out:{current_node_id()}]", stop_reason="end_turn",
                           usage=Usage(5, 5))


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


def wide_spec(n):
    items = [f"item{i}" for i in range(n)]
    return {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "items": items, "task": "propose"},
            {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        ],
        "edges": [{"from": "fan", "to": "merge", "reducer": "concat"}],
        "terminal": ["merge"],
    }


def deep_spec(n):
    nodes = [{"id": "n0", "kind": "subagent", "task": "t0"}]
    edges = []
    for i in range(1, n):
        nodes.append({"id": f"n{i}", "kind": "subagent", "task": f"t{i}"})
        edges.append({"from": f"n{i-1}", "to": f"n{i}"})
    return {"goal": "g", "nodes": nodes, "edges": edges, "terminal": [f"n{n-1}"]}


async def timed(spec, label):
    ws = Path(f"/tmp/spike273/perf-{label}")
    ws.mkdir(parents=True, exist_ok=True)
    llm = ScriptedLLM()
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    t0 = time.time()
    result = await sched.run(parse_workflow_spec(spec))
    dt = time.time() - t0
    print(f"  {label:24} status={result['status']:22} llm_calls={llm.calls:4} "
          f"elapsed={dt:.3f}s")
    return dt


async def main():
    print("=== foreach width (fan-out expansion) ===")
    for n in (5, 20, 50):
        await timed(wide_spec(n), f"foreach-{n}")

    print("\n=== chain depth ===")
    for n in (10, 50):
        await timed(deep_spec(n), f"chain-{n}")

    print("\n=== many independent subagents via foreach of subagents ===")
    # foreach expanding into subagent work, then aggregate
    for n in (20,):
        spec = {
            "goal": "g",
            "nodes": [
                {"id": "fan", "kind": "foreach", "items": [f"i{k}" for k in range(n)],
                 "task": "work"},
                {"id": "agg", "kind": "aggregate", "strategy": "llm"},
            ],
            "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
            "terminal": ["agg"],
        }
        await timed(spec, f"foreach-llm-agg-{n}")


asyncio.run(main())

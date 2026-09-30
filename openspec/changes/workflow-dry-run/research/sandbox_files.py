"""#273 spike 11: what actually lands in the THROWAWAY sandbox dir?

Design says "零落盘" but isolation.py reported 22 files in the tmp ws.
Enumerate them and identify the writer, so D4's claim can be stated precisely.
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
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=f"[{current_node_id()}]", stop_reason="end_turn",
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


SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "ta"},
        {"id": "b", "kind": "subagent", "task": "tb"},
        {"id": "root", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [{"from": "a", "to": "root", "reducer": "concat"},
              {"from": "b", "to": "root", "reducer": "concat"}],
    "terminal": ["root"],
}


async def main():
    ws = Path("/tmp/spike273/sbfiles")
    if ws.exists():
        import shutil
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    llm = ScriptedLLM()
    mgr = SubAgentManager(
        llm=llm, config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=ws),
    )
    sched = WorkflowScheduler(mgr)
    sched._store = NullStore(sched.workflow_id)
    await sched.run(parse_workflow_spec(SPEC))

    files = sorted(p for p in ws.rglob("*") if p.is_file())
    print(f"total files in throwaway ws: {len(files)}")
    by_dir = {}
    for p in files:
        rel = p.relative_to(ws)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        by_dir.setdefault(top, []).append(str(rel))
    for top, items in sorted(by_dir.items()):
        print(f"\n  {top}/  ({len(items)} files)")
        for it in items[:6]:
            print(f"      {it}  ({Path(ws/it).stat().st_size}B)")
        if len(items) > 6:
            print(f"      ... +{len(items)-6} more")


asyncio.run(main())

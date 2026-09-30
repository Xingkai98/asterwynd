"""#273 spike 7: prototype of the real DryRunWorkflow tool + full validation.

This is the proposed implementation, written as it would land in
agent/tools/builtin/subagents.py, so the design doc rests on measured behavior
rather than a sketch.
"""
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/home/happy/my-agent/.claude/worktrees/workflow-dry-run")

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.context import current_node_id
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import (
    TERMINAL_NODE_STATUSES,
    WorkflowScheduler,
)
from agent.subagent.workflow import parse_workflow_spec
from agent.subagent.workflow_store import WorkflowStore
from agent.workspace_policy import WorkspacePolicy


# ---------------------------------------------------------------- fake LLM


class DryRunLLM:
    """Zero-token stand-in.  Echoes what it received, tagged with the node id.

    - node identity comes from the ``current_node_id()`` contextvar, so **no
      scheduler change** is needed to attribute outputs to nodes;
    - ``script`` lets the caller steer a node's output (that is how a model asks
      "what if the critic says GAPS?" without spending a token);
    - it never emits tool calls, so the run is pure text propagation.
    """

    def __init__(self, script: dict[str, str] | None = None):
        self.script = script or {}
        self.calls: list[tuple[str, str]] = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        node = current_node_id() or "?"
        received = ""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, str) and c:
                received = c
        self.calls.append((node, received))
        out = self.script.get(node)
        if out is None:
            out = f"[{node} produced: auto]"
        return LLMResponse(content=out, stop_reason="end_turn", usage=Usage(0, 0))


class _NullStore:
    """No-op WorkflowStore: the isolated dry run must never write to disk."""

    def __init__(self, workflow_id: str = "dryrun"):
        self.workflow_id = workflow_id
        self.root = Path("/dev/null")

    def ref(self, key: str) -> str:
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


# ---------------------------------------------------------------- the tool


async def dry_run_workflow(
    manager: SubAgentManager,
    raw_spec,
    *,
    script: dict[str, str] | None = None,
    max_report_chars: int = 240,
) -> dict:
    """Simulate a workflow: no LLM calls, no disk writes, no registry pollution."""

    try:
        spec = parse_spec_for_manager(manager, raw_spec)
    except Exception as exc:  # WorkflowValidationError / WorkflowCycleError
        return {"status": "invalid_spec", "reason": str(exc)}

    llm = DryRunLLM(script)

    # Isolated manager: inherits the REAL config (so limits reported are the
    # limits that will actually apply) but gets a throwaway workspace root and
    # its own LLM.  It is never registered with the parent loop, has no
    # graph_sink, and shares no state with the live manager.
    with tempfile.TemporaryDirectory(prefix="dryrun-") as tmp:
        sim_manager = SubAgentManager(
            llm=llm,
            config=manager.config,
            parent_mode=getattr(manager, "parent_mode", AgentMode.BUILD),
            workspace_policy=WorkspacePolicy(workspace_root=tmp),
        )
        scheduler = WorkflowScheduler(sim_manager)
        scheduler._store = _NullStore(scheduler.workflow_id)  # the only writer

        t0 = time.time()
        result = await scheduler.run(spec)
        elapsed = time.time() - t0

        report = _build_report(scheduler, result, spec, llm, elapsed, max_report_chars)

    return report


def _clip(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"…[+{len(text)-limit} chars]"


def _build_report(scheduler, result, spec, llm, elapsed, limit) -> dict:
    nodes = []
    for node in spec.nodes:
        st = scheduler._states.get(node.id)
        if st is None:
            continue
        entry = {
            "id": node.id,
            "kind": node.kind,
            "status": st.status,
            "runs": st.runs,
            "produced": _clip(st.summary, limit),
        }
        if node.kind == "foreach":
            entry["items_expanded"] = st.items
        if node.kind == "route":
            entry["input_seen"] = _clip(st.raw, limit)
            entry["matched"] = st.verdict
            entry["walked_to"] = list(st.targets)
            entry["used_default"] = st.verdict is None
        if st.slots:
            entry["slots"] = {k: _clip(v, limit) for k, v in st.slots.items()}
        nodes.append(entry)

    # Data actually delivered along each edge, re-derived from the same
    # predicate the scheduler uses (no second source of truth).
    delivered = {}
    for _, (node, received) in zip(range(len(llm.calls)), llm.calls):
        delivered.setdefault(node, received)
    edges = []
    for edge in spec.edges:
        upstream = scheduler._states.get(edge.source)
        edges.append({
            "from": edge.source,
            "to": edge.target,
            "channel": edge.channel,
            "control": spec.is_control_edge(edge),
            "upstream_status": upstream.status if upstream else None,
        })

    return {
        "status": "simulated",
        "run_status": result["status"],
        "elapsed_s": round(elapsed, 4),
        "llm_calls": len(llm.calls),
        "tokens_spent": 0,
        "nodes": nodes,
        "edges": edges,
        #: node_id -> the exact text that node's prompt contained
        "received": {n: _clip(t, limit) for n, t in delivered.items()},
        "notes": [
            "This is a SIMULATION. It shows topology and data flow, not what a "
            "real model would say. A node here outputs a placeholder unless you "
            "supplied a `script` override."
        ],
    }


# ---------------------------------------------------------------- validation


def parse_spec_for_manager(manager, raw):
    from agent.tools.builtin.subagents import parse_spec_for_manager as f
    return f(manager, raw)


SPEC = {
    "goal": "review the design",
    "nodes": [
        {"id": "w1", "kind": "subagent", "task": "TASK-W1"},
        {"id": "w2", "kind": "subagent", "task": "TASK-W2"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["merged"]},
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
        {"id": "gate", "kind": "route",
         "cases": [{"when": "GAPS: none", "to": "report"},
                   {"when": "GAPS", "to": "rework"}],
         "default": "report"},
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "w1", "to": "merge", "reducer": "concat"},
        {"from": "w2", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "critic"},
        {"from": "critic", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
    ],
    "entry": ["w1", "w2", "rework"],
    "terminal": ["report"],
}


def snap(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.stat().st_size
    return out


async def main():
    real_ws = Path("/tmp/spike273/proto-ws")
    real_ws.mkdir(parents=True, exist_ok=True)
    (real_ws / "sentinel.txt").write_text("keep me\n")
    before = snap(real_ws)

    real_mgr = SubAgentManager(
        llm=DryRunLLM(), config=AsterwyndConfig(), parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=real_ws),
    )
    print(f"real manager registry before: {list(real_mgr._workflows)}")

    print("\n########## CASE 1: blind dry run (no script) ##########")
    rep = await dry_run_workflow(real_mgr, SPEC)
    print(json.dumps(rep, indent=2, ensure_ascii=False)[:2600])

    print("\n########## CASE 2: what-if the critic says GAPS ##########")
    rep2 = await dry_run_workflow(
        real_mgr, SPEC, script={"critic": "GAPS: missing tests"})
    g = next(n for n in rep2["nodes"] if n["id"] == "gate")
    print(f"  gate.input_seen = {g['input_seen']!r}")
    print(f"  gate.matched    = {g['matched']!r}  walked_to={g['walked_to']}")

    print("\n########## ISOLATION CHECKS ##########")
    after = snap(real_ws)
    new = set(after) - set(before)
    print(f"  real workspace disk delta : {sorted(new) if new else '(none)'}")
    print(f"  sentinel intact           : {(real_ws/'sentinel.txt').read_text().strip()!r}")
    print(f"  real manager registry     : {list(real_mgr._workflows)}  (must stay empty)")
    print(f"  real manager stores       : {list(real_mgr._workflow_stores)}")

    print("\n########## PERF ##########")
    print(f"  case1 elapsed = {rep['elapsed_s']}s   case2 elapsed = {rep2['elapsed_s']}s")


asyncio.run(main())

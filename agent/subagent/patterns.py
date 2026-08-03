"""Orchestration pattern library for subagents (issue 79, decision D6).

``OrcPattern`` subclasses provide the deterministic skeleton — spawn N → wait →
collect — while the "split / select / review" intelligence inside a pattern is
carried by LLM subagents. Patterns run on top of ``SubAgentManager`` (no
separate control plane) and receive a per-run ``MessageBus`` via the contextvar,
so workers can exchange summaries under the bus's token budget.

Four patterns:

- orchestrator-worker: coordinator (the calling agent) fans out to N parallel
  workers, then aggregates. Workers do not talk to each other.
- peer-review: a producer creates output, a reviewer critiques, and the loop
  iterates until approval or ``max_rounds``.
- hierarchical: N manager subagents each run a sub-task and may themselves spawn
  (nested spawn, enabled by decision D4).
- bidding: N proposers each produce a solution independently, then a selector
  subagent picks the best. The selector reads compact proposal summaries (the
  design deliberately avoids the bus for proposals, whose drop-oldest could
  drop a key bid) and may Read full proposals from artifacts.

Worker failure is not fail-fast: the aggregate envelope reports each worker's
``{subagent_id, status, summary/result_ref, usage}`` plus pattern-level counts,
so benchmark completion/cost are comparable.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agent.subagent.bus import MessageBus
from agent.subagent.context import set_bus, reset_bus

if TYPE_CHECKING:
    from agent.subagent.manager import SubAgentManager


class OrcPattern:
    name = "base"

    def __init__(
        self,
        manager: "SubAgentManager",
        *,
        task: str,
        params: dict[str, Any] | None = None,
        bus: MessageBus | None = None,
    ) -> None:
        self.manager = manager
        self.task = task
        self.params = params or {}
        self.bus = bus

    async def run(self) -> dict:
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------

    def _spawn(self, name: str, description: str = "") -> str:
        return self.manager.create_subagent(name=name, description=description)[
            "subagent_id"
        ]

    async def _run_worker(self, subagent_id: str, task: str) -> dict:
        return await self.manager.run_subagent(
            subagent_id=subagent_id,
            task=task,
            wait=True,
            max_tokens=self.params.get("worker_max_tokens"),
            max_time_s=self.params.get("worker_max_time_s"),
        )

    def _aggregate(self, results: list[dict]) -> dict:
        completed = sum(1 for r in results if r["status"] == "completed")
        failed = sum(1 for r in results if r["status"] != "completed")
        workers = [
            {
                "subagent_id": r["subagent_id"],
                "status": r["status"],
                "summary": r.get("summary", ""),
                "reason": r.get("reason"),
                "usage": r.get("usage", {}),
            }
            for r in results
        ]
        parts = [
            f"[{r['subagent_id']}] {r.get('summary', r.get('reason', 'no output'))}"
            for r in results
        ]
        return {
            "pattern": self.name,
            "task": self.task,
            "completed": completed,
            "failed": failed,
            "workers": workers,
            "summary": "\n".join(parts),
        }


class OrchestratorWorkerPattern(OrcPattern):
    name = "orchestrator-worker"

    async def run(self) -> dict:
        worker_count = max(1, int(self.params.get("workers", 3)))
        worker_ids = [
            self._spawn(f"worker-{i}", "parallel worker") for i in range(worker_count)
        ]
        results = await asyncio.gather(
            *[self._run_worker(wid, self.task) for wid in worker_ids]
        )
        return self._aggregate(list(results))


class PeerReviewPattern(OrcPattern):
    name = "peer-review"

    async def run(self) -> dict:
        max_rounds = max(1, int(self.params.get("max_rounds", 3)))
        producer = self._spawn("producer", "produces the proposal")
        reviewer = self._spawn("reviewer", "critiques the proposal")

        last_produced: dict | None = None
        last_review: dict | None = None
        for _ in range(max_rounds):
            produced = await self._run_worker(producer, self.task)
            last_produced = produced
            if produced["status"] != "completed":
                return self._aggregate([produced])

            review = await self._run_worker(
                reviewer,
                "Review the following proposal. Reply with exactly one line "
                "starting with APPROVED if it is acceptable, or CRITIQUE followed "
                "by the specific issues if it needs revision.\n\n"
                f"PROPOSAL:\n{produced.get('summary', '')}",
            )
            last_review = review
            review_text = (review.get("summary", "") or "").upper()
            if review_text.startswith("APPROVED"):
                return self._aggregate([produced, review])
            # feed critique back to producer for the next round
            self.task = (
                f"{self.task}\n\nAddress the reviewer's critique:\n"
                f"{review.get('summary', '')}"
            )

        # max_rounds reached without approval — report the real final runs
        real_runs = [r for r in (last_produced, last_review) if r is not None]
        return self._aggregate(real_runs)


class HierarchicalPattern(OrcPattern):
    name = "hierarchical"

    async def run(self) -> dict:
        team_count = max(1, int(self.params.get("teams", 2)))
        manager_ids = [
            self._spawn(f"manager-{i}", "sub-team manager, may spawn its own workers")
            for i in range(team_count)
        ]
        results = await asyncio.gather(
            *[self._run_worker(mid, self.task) for mid in manager_ids]
        )
        return self._aggregate(list(results))


class BiddingPattern(OrcPattern):
    name = "bidding"

    async def run(self) -> dict:
        proposer_count = max(2, int(self.params.get("proposers", 3)))
        proposer_ids = [
            self._spawn(f"proposer-{i}", "independent proposer")
            for i in range(proposer_count)
        ]
        proposals = await asyncio.gather(
            *[self._run_worker(pid, self.task) for pid in proposer_ids]
        )
        # Selector input = compact proposal summaries (not the bus — drop-oldest
        # could lose a key bid). Full proposals may be read from artifacts.
        selector = self._spawn("selector", "evaluates and picks the best proposal")
        body = "\n\n".join(
            f"Proposal {i + 1} ({r['subagent_id']}):\n{r.get('summary', r.get('reason', ''))}"
            for i, r in enumerate(proposals)
        )
        selected = await self._run_worker(
            selector,
            "Evaluate the following proposals and select the best one. "
            "Reply with exactly one line starting with SELECTED <proposal number> "
            "followed by a one-sentence justification.\n\n"
            f"{body}",
        )
        aggregate = self._aggregate(list(proposals))
        aggregate["selected"] = selected.get("summary", "")
        aggregate["selector"] = {
            "subagent_id": selector,
            "status": selected["status"],
            "summary": selected.get("summary", ""),
        }
        return aggregate


PATTERNS: dict[str, type[OrcPattern]] = {
    "orchestrator-worker": OrchestratorWorkerPattern,
    "peer-review": PeerReviewPattern,
    "hierarchical": HierarchicalPattern,
    "bidding": BiddingPattern,
}


async def run_pattern(
    manager: "SubAgentManager",
    *,
    pattern: str,
    task: str,
    params: dict[str, Any] | None = None,
) -> dict:
    """Run an orchestration pattern with a fresh per-run message bus.

    The bus is installed into the current context so the calling agent and every
    spawned worker can publish/read summaries; it is reset when the pattern ends.
    """
    if pattern not in PATTERNS:
        raise KeyError(
            f"unknown pattern {pattern!r}; available: {sorted(PATTERNS)}"
        )
    bus = MessageBus()
    token = set_bus(bus)
    try:
        instance = PATTERNS[pattern](manager, task=task, params=params, bus=bus)
        result = await instance.run()
        result["bus"] = bus.snapshot_payload()
        return result
    finally:
        reset_bus(token)

from __future__ import annotations

from dataclasses import dataclass

from agent.message import Message
from workflow_control import (
    Actor,
    ActorKind,
    AdapterRunResult,
    EnforcementLevel,
    WorkResult,
    WorkflowOrchestrator,
    build_executor_prompt,
)


@dataclass(frozen=True)
class AsterwyndWorkflowExecutor:
    orchestrator: WorkflowOrchestrator
    agent: object
    actor: Actor = Actor(kind=ActorKind.AGENT, actor_id="asterwynd-agent")
    enforcement_level: EnforcementLevel = EnforcementLevel.STRICT_HOST

    async def run_once(
        self,
        workflow_id: str,
        *,
        user_message: str,
        session_id: str,
        run_id: str,
        resume_snapshot=None,
    ) -> AdapterRunResult:
        entered = self.orchestrator.enter(workflow_id, self.actor)
        if entered.waiting_for_human or entered.work_item is None:
            return AdapterRunResult(
                snapshot=entered.snapshot,
                enforcement_level=self.enforcement_level,
                summary="waiting",
                waiting_for_human=entered.waiting_for_human,
            )

        set_context = getattr(self.agent, "set_workflow_context", None)
        if callable(set_context):
            set_context(workflow_id, entered.snapshot.version, entered.work_item.work_item_id)

        prompt = build_executor_prompt(
            workflow_id=workflow_id,
            snapshot=entered.snapshot,
            work_item=entered.work_item,
            user_message=user_message,
        )
        result = await self.agent.run(
            [Message(role="user", content=prompt)],
            session_id=session_id,
            run_id=run_id,
            resume_snapshot=resume_snapshot,
        )
        reported = self.orchestrator.report(
            workflow_id=workflow_id,
            actor=self.actor,
            work_item_id=entered.work_item.work_item_id,
            result=WorkResult(
                summary=getattr(result, "content", "") or "",
                enforcement_level=self.enforcement_level,
            ),
            expected_version=entered.snapshot.version,
        )
        return AdapterRunResult(
            snapshot=reported.snapshot,
            enforcement_level=self.enforcement_level,
            summary=getattr(result, "content", "") or "",
        )

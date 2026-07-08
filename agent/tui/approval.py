"""Async approval handler for the TUI.

The handler follows ApprovalHandler request/response semantics without using
the blocking CLI stdin prompt.
"""

from __future__ import annotations

import asyncio

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalResponse,
)


class TUIApprovalHandler:
    """Approval handler that waits asynchronously for a TUI decision."""

    def __init__(self) -> None:
        self._pending: tuple[str, asyncio.Future[ApprovalResponse]] | None = None

    @property
    def pending_approval_id(self) -> str | None:
        """Return the pending approval id, if any."""
        if self._pending is None:
            return None
        return self._pending[0]

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Wait for a user decision for one approval request."""
        if self._pending is not None:
            return ApprovalResponse(
                approval_id=request.approval_id,
                status=ApprovalDecisionStatus.UNAVAILABLE,
                reason="another approval request is already pending",
            )
        future: asyncio.Future[ApprovalResponse] = asyncio.get_running_loop().create_future()
        self._pending = (request.approval_id, future)
        try:
            return await future
        finally:
            if self._pending is not None and self._pending[0] == request.approval_id:
                self._pending = None

    def submit_response(self, approval_id: str, decision: str) -> bool:
        """Submit the user's approval decision.

        Args:
            approval_id: Approval id to resolve.
            decision: Approved aliases resolve as approved; other values deny.

        Returns:
            True when a pending approval was resolved.
        """
        if self._pending is None or self._pending[0] != approval_id:
            return False
        future = self._pending[1]
        if future.done():
            return False
        normalized = decision.strip().lower()
        if normalized in {"approved", "approve", "allow", "yes", "y"}:
            status = ApprovalDecisionStatus.APPROVED
            reason = "approved by TUI user"
        else:
            status = ApprovalDecisionStatus.DENIED
            reason = "denied by TUI user"
        future.set_result(
            ApprovalResponse(
                approval_id=approval_id,
                status=status,
                reason=reason,
            )
        )
        return True

    def fail_pending(self, reason: str) -> None:
        """Resolve the current pending approval as unavailable."""
        if self._pending is None:
            return
        approval_id, future = self._pending
        if not future.done():
            future.set_result(
                ApprovalResponse(
                    approval_id=approval_id,
                    status=ApprovalDecisionStatus.UNAVAILABLE,
                    reason=reason,
                )
            )

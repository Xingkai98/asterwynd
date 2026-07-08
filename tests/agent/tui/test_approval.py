"""TUI approval handler 测试。

覆盖 approve、deny 和审批不可用/关闭时 fail closed 路径。
"""

import asyncio

import pytest

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalRequest,
    ApprovalResponse,
)
from agent.tui.approval import TUIApprovalHandler


def _approval_request(approval_id: str = "approval-1") -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=approval_id,
        tool_call_id="call-1",
        tool_name="Bash",
        mode="build",
        capability=["command_execute"],
        risk="high",
        origin="builtin",
        reason="test",
        profile_name="build_default",
        redacted_args={"cmd": "pytest"},
        args_summary='{"cmd": "pytest"}',
    )


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_resolves_with_approved():
    handler = TUIApprovalHandler()

    async def _approve_later():
        await asyncio.sleep(0.01)
        handler.submit_response("approval-1", "approved")

    task = asyncio.create_task(_approve_later())
    response = await handler.request_approval(_approval_request("approval-1"))
    await task

    assert response.status is ApprovalDecisionStatus.APPROVED
    assert response.approved is True
    assert response.approval_id == "approval-1"


# ---------------------------------------------------------------------------
# deny
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deny_resolves_with_denied():
    handler = TUIApprovalHandler()

    async def _deny_later():
        await asyncio.sleep(0.01)
        handler.submit_response("approval-1", "denied")

    task = asyncio.create_task(_deny_later())
    response = await handler.request_approval(_approval_request("approval-1"))
    await task

    assert response.status is ApprovalDecisionStatus.DENIED
    assert response.approved is False


# ---------------------------------------------------------------------------
# fail_pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fail_pending_resolves_with_unavailable():
    handler = TUIApprovalHandler()

    # 启动 request_approval 但不等待
    task = asyncio.create_task(handler.request_approval(_approval_request("fail-1")))

    # Let the coroutine start
    await asyncio.sleep(0.01)

    handler.fail_pending("session closed")

    # 等待 task 完成（request_approval 的 finally 块会清理 pending）
    response = await task
    assert response.status is ApprovalDecisionStatus.UNAVAILABLE
    assert handler.pending_approval_id is None


@pytest.mark.asyncio
async def test_fail_pending_returns_unavailable_status():
    handler = TUIApprovalHandler()

    async def _check():
        response = await handler.request_approval(_approval_request("fail-2"))
        return response

    task = asyncio.create_task(_check())
    await asyncio.sleep(0.01)  # Let request_approval start

    handler.fail_pending("session closed")

    response = await task
    assert response.status is ApprovalDecisionStatus.UNAVAILABLE
    assert not response.approved


# ---------------------------------------------------------------------------
# no pending (idle state)
# ---------------------------------------------------------------------------

def test_pending_approval_id_none_when_idle():
    handler = TUIApprovalHandler()
    assert handler.pending_approval_id is None


def test_submit_response_ignored_when_no_pending():
    handler = TUIApprovalHandler()
    result = handler.submit_response("nonexistent", "approved")
    assert result is False


# ---------------------------------------------------------------------------
# submit invalid decision
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_response_invalid_decision_defaults_to_denied():
    handler = TUIApprovalHandler()

    async def _submit():
        await asyncio.sleep(0.01)
        handler.submit_response("approval-x", "maybe")

    task = asyncio.create_task(_submit())
    response = await handler.request_approval(_approval_request("approval-x"))
    await task

    # "maybe" 不匹配任何 approved 关键词，默认 deny
    assert response.status is ApprovalDecisionStatus.DENIED


# ---------------------------------------------------------------------------
# multiple concurrent request (second one rejected)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_concurrent_request_rejected():
    handler = TUIApprovalHandler()

    async def _first():
        return await handler.request_approval(_approval_request("first"))

    task1 = asyncio.create_task(_first())
    await asyncio.sleep(0.01)  # Let first request start

    # Second request should be rejected immediately
    response2 = await handler.request_approval(_approval_request("second"))
    assert response2.status is ApprovalDecisionStatus.UNAVAILABLE
    assert "already pending" in response2.reason

    # Resolve first
    handler.submit_response("first", "approved")
    response1 = await task1
    assert response1.approved is True


# ---------------------------------------------------------------------------
# submit after future already resolved
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_response_after_already_resolved_is_ignored():
    handler = TUIApprovalHandler()

    async def _resolve():
        await asyncio.sleep(0.01)
        handler.submit_response("done-1", "approved")
        # Second submit should be ignored
        result = handler.submit_response("done-1", "denied")
        assert result is False

    task = asyncio.create_task(_resolve())
    response = await handler.request_approval(_approval_request("done-1"))
    await task

    assert response.approved is True


# ---------------------------------------------------------------------------
# submit with approve aliases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_with_approve_aliases():
    for alias in ("approve", "allow", "yes", "y"):
        handler = TUIApprovalHandler()

        async def _submit():
            await asyncio.sleep(0.005)
            handler.submit_response(f"test-{alias}", alias)

        task = asyncio.create_task(_submit())
        response = await handler.request_approval(
            _approval_request(f"test-{alias}")
        )
        await task
        assert response.approved is True, f"alias '{alias}' should approve"

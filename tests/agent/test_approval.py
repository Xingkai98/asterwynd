import json

import pytest

from agent.approval import (
    ARGUMENT_SUMMARY_LIMIT,
    ApprovalDecisionStatus,
    ApprovalRequest,
    CliApprovalHandler,
    redact_value,
    summarize_arguments,
)


def test_redact_value_masks_sensitive_keys_and_string_patterns():
    redacted = redact_value({
        "api_key": "sk-secret",
        "nested": {
            "Authorization": "Bearer abc",
            "command": "curl -H 'Authorization: Bearer sk-abc123456789' https://x",
            "url": "https://example.test?api_key=secret-value&x=1",
        },
        "items": [{"password": "pw"}],
    })

    encoded = json.dumps(redacted, ensure_ascii=False)
    assert "sk-secret" not in encoded
    assert "abc123456789" not in encoded
    assert "secret-value" not in encoded
    assert "pw" not in encoded
    assert encoded.count("[redacted]") >= 4


def test_summarize_arguments_caps_output_length():
    summary = summarize_arguments({"content": "x" * (ARGUMENT_SUMMARY_LIMIT + 100)})

    assert len(summary) <= ARGUMENT_SUMMARY_LIMIT
    assert summary.endswith("chars]")
    assert "truncated" in summary


@pytest.mark.asyncio
async def test_cli_approval_handler_accepts_yes(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    response = await CliApprovalHandler(interactive=True).request_approval(
        _approval_request()
    )

    assert response.status is ApprovalDecisionStatus.APPROVED


@pytest.mark.asyncio
async def test_cli_approval_handler_denies_empty_input(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    response = await CliApprovalHandler(interactive=True).request_approval(
        _approval_request()
    )

    assert response.status is ApprovalDecisionStatus.DENIED


def test_redact_value_replaces_image_blocks():
    """redacted_args 中 ImageBlock 替换为 [image: file_path] 引用"""
    from agent.message import ImageBlock, ImageUrl

    image_block = ImageBlock(
        image_url=ImageUrl(url="data:image/png;base64,VERYSECRETBASE64"),
        file_path="/tmp/sensitive.png",
    )
    redacted = redact_value({"image": image_block, "text": "plain"})

    encoded = json.dumps(redacted, ensure_ascii=False)
    assert "VERYSECRETBASE64" not in encoded
    assert "sensitive.png" in encoded or "plain" in encoded


def _approval_request() -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="approval-1",
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

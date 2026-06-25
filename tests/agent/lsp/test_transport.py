from __future__ import annotations

import json

import pytest

from agent.lsp.transport import (
    encode_message,
    read_message,
)


def test_encode_message_with_id():
    payload = encode_message(id=1, method="initialize", params={"x": 1})
    assert payload.startswith(b"Content-Length: ")
    assert b"\r\n\r\n" in payload
    header, _, body = payload.partition(b"\r\n\r\n")
    assert header == b"Content-Length: 47" or header.startswith(b"Content-Length: ")
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["jsonrpc"] == "2.0"
    assert parsed["id"] == 1
    assert parsed["method"] == "initialize"
    assert parsed["params"] == {"x": 1}


def test_encode_message_notification():
    payload = encode_message(id=None, method="exit", params=None)
    header, _, body = payload.partition(b"\r\n\r\n")
    parsed = json.loads(body.decode("utf-8"))
    assert "id" not in parsed
    assert parsed["method"] == "exit"
    assert "params" not in parsed


def test_read_message_complete():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "foo"}).encode("utf-8")
    frame = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    message, remaining = read_message(frame)
    assert message == {"jsonrpc": "2.0", "id": 1, "method": "foo"}
    assert remaining == b""


def test_read_message_partial_returns_none():
    body = json.dumps({"jsonrpc": "2.0", "id": 1}).encode("utf-8")
    frame = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body[:5]
    message, remaining = read_message(frame)
    assert message is None
    assert remaining == frame  # buffer unchanged


def test_read_message_handles_multiple_frames():
    body1 = json.dumps({"jsonrpc": "2.0", "id": 1}).encode("utf-8")
    body2 = json.dumps({"jsonrpc": "2.0", "id": 2}).encode("utf-8")
    frame = (
        b"Content-Length: " + str(len(body1)).encode() + b"\r\n\r\n" + body1
        + b"Content-Length: " + str(len(body2)).encode() + b"\r\n\r\n" + body2
    )
    msg1, frame = read_message(frame)
    msg2, frame = read_message(frame)
    assert msg1["id"] == 1
    assert msg2["id"] == 2
    assert frame == b""


def test_read_message_malformed_json_raises():
    body = b"{not json"
    frame = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    from agent.lsp.transport import LspTransportError

    with pytest.raises(LspTransportError, match="Invalid JSON-RPC"):
        read_message(frame)

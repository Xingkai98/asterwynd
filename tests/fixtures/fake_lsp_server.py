#!/usr/bin/env python3
"""A minimal stdio LSP server for integration tests.

Implements just enough of the LSP protocol for the agent's LspClient to
exercise real subprocess spawn, stdio framing, initialize handshake,
didOpen/didChange, and the six query methods used by the LSP tools.

Behavior is intentionally simple and deterministic:
- definition: returns the file itself at line 1:1
- references: returns the file itself at line 1:1
- hover: returns "hover: <method>"
- documentSymbol: returns one Function symbol named "foo" at 1:1
- workspace/symbol: returns one symbol matching the query
- textDocument/diagnostic: returns one error diagnostic

All responses use Content-Length framing. Reads are line-buffered on
stdin for simplicity (LSP messages are sent as single JSON objects per
write on the client side, so reading the framed body works).
"""
from __future__ import annotations

import json
import sys


def read_message() -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if b":" in line:
            key, _, value = line.partition(b":")
            headers[key.decode("ascii").strip().lower()] = value.decode("ascii").strip()
    length_str = headers.get("content-length")
    if length_str is None:
        return None
    try:
        length = int(length_str)
    except ValueError:
        return None
    body = sys.stdin.buffer.read(length)
    try:
        message = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return message


def send_message(message: dict) -> None:
    payload = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    params = msg.get("params") or {}
    msg_id = msg.get("id")
    if method == "initialize":
        return {
            "id": msg_id,
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,
                    "definitionProvider": True,
                    "referencesProvider": True,
                    "hoverProvider": True,
                    "documentSymbolProvider": True,
                    "workspaceSymbolProvider": True,
                    "diagnosticProvider": {"interFileDependencies": False, "workspaceDiagnostics": False},
                },
                "serverInfo": {"name": "fake-lsp", "version": "0.1.0"},
            },
        }
    if method == "shutdown":
        return {"id": msg_id, "result": None}
    if method == "textDocument/definition":
        return {
            "id": msg_id,
            "result": [
                {
                    "uri": params.get("textDocument", {}).get("uri", ""),
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
                }
            ],
        }
    if method == "textDocument/references":
        return {
            "id": msg_id,
            "result": [
                {
                    "uri": params.get("textDocument", {}).get("uri", ""),
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
                }
            ],
        }
    if method == "textDocument/hover":
        return {"id": msg_id, "result": {"contents": {"kind": "markdown", "value": f"hover: {method}"}}}
    if method == "textDocument/documentSymbol":
        uri = params.get("textDocument", {}).get("uri", "")
        return {
            "id": msg_id,
            "result": [
                {"name": "foo", "kind": 12, "location": {"uri": uri, "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}}}},
            ],
        }
    if method == "workspace/symbol":
        query = params.get("query", "")
        return {
            "id": msg_id,
            "result": [
                {"name": query or "match", "kind": 12, "location": {"uri": "file:///fake", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}}},
            ],
        }
    if method == "textDocument/diagnostic":
        return {
            "id": msg_id,
            "result": {
                "kind": "full",
                "items": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}},
                        "severity": 1,
                        "message": "fake diagnostic",
                    }
                ],
            },
        }
    # Unknown method - return null result
    return {"id": msg_id, "result": None}


def handle_notification(msg: dict) -> None:
    method = msg.get("method")
    if method == "textDocument/didOpen":
        # Push a publishDiagnostics notification back to client
        params = msg.get("params") or {}
        uri = params.get("textDocument", {}).get("uri", "")
        send_message({
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 3}},
                        "severity": 1,
                        "message": "fake published diagnostic",
                    }
                ],
            },
        })
    # didChange, initialized, exit: no response needed


def main() -> None:
    while True:
        msg = read_message()
        if msg is None:
            break
        if "id" in msg:
            response = handle_request(msg)
            if response is not None:
                send_message(response)
            if msg.get("method") == "shutdown":
                # Wait for exit notification then quit
                pass
        else:
            handle_notification(msg)
            if msg.get("method") == "exit":
                break


if __name__ == "__main__":
    main()

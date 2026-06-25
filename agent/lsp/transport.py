from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


class LspTransportError(Exception):
    """Raised when the LSP transport layer fails."""


class LspTransportClosed(LspTransportError):
    """Raised when the transport is closed while waiting for a response."""


class LspTransport(Protocol):
    """Abstract LSP transport.

    Implementations send JSON-RPC messages over stdio (real server) or
    short-circuit in-process (fake). The client uses send_request for
    request/response, send_notification for fire-and-forget, and
    register_notification_handler for server-pushed notifications such
    as textDocument/publishDiagnostics.
    """

    def send_request(
        self, method: str, params: Any | None, *, timeout_ms: int
    ) -> Awaitable[Any]:
        ...

    def send_notification(self, method: str, params: Any | None) -> Awaitable[None]:
        ...

    def register_notification_handler(
        self, method: str, handler: Callable[[Any], None]
    ) -> None:
        ...

    async def start(self) -> None:
        ...

    async def close(self) -> None:
        ...


def encode_message(*, id: int | None, method: str, params: Any | None) -> bytes:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        body["id"] = id
    if params is not None:
        body["params"] = params
    payload = json.dumps(body).encode("utf-8")
    return b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n" + payload


def read_message(buffer: bytes) -> tuple[dict[str, Any] | None, bytes]:
    """Parse one JSON-RPC message from the front of buffer.

    Returns (message, remaining_buffer). If the buffer does not yet
    contain a complete message, returns (None, buffer).
    """
    header_end = buffer.find(b"\r\n\r\n")
    if header_end == -1:
        return None, buffer
    header = buffer[:header_end].decode("ascii", errors="replace")
    content_length: int | None = None
    for line in header.split("\r\n"):
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                return None, buffer  # malformed; drop to avoid infinite loop
            break
    if content_length is None:
        return None, buffer
    body_start = header_end + 4
    if len(buffer) < body_start + content_length:
        return None, buffer
    body = buffer[body_start : body_start + content_length]
    remaining = buffer[body_start + content_length :]
    try:
        message = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise LspTransportError(f"Invalid JSON-RPC body: {exc}") from exc
    if not isinstance(message, dict):
        raise LspTransportError("JSON-RPC body must be an object")
    return message, remaining


@dataclass
class _PendingRequest:
    future: asyncio.Future
    method: str


class StdioLspTransport:
    """Real LSP transport over stdio to a spawned language server process."""

    def __init__(self, command: tuple[str, ...], args: tuple[str, ...] = ()):
        self._command = tuple(command) + tuple(args)
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, _PendingRequest] = {}
        self._notification_handlers: dict[str, Callable[[Any], None]] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._closed = False
        self._start_lock = asyncio.Lock()
        self._stderr_buffer = b""

    @property
    def closed(self) -> bool:
        return self._closed

    def register_notification_handler(
        self, method: str, handler: Callable[[Any], None]
    ) -> None:
        self._notification_handlers[method] = handler

    async def start(self) -> None:
        async with self._start_lock:
            if self._process is not None:
                return
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *self._command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            except FileNotFoundError as exc:
                raise LspTransportError(
                    f"Failed to start LSP server {self._command[0]}: {exc}"
                ) from exc
            self._reader_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._process
        if proc is not None and proc.stdin is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
        for pending in list(self._pending.values()):
            if not pending.future.done():
                pending.future.set_exception(LspTransportClosed("transport closed"))
        self._pending.clear()
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        if proc is not None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                except Exception:
                    pass
            except Exception:
                pass
        self._process = None

    async def send_request(
        self, method: str, params: Any | None, *, timeout_ms: int
    ) -> Any:
        if self._closed or self._process is None:
            raise LspTransportClosed("transport not started or closed")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = _PendingRequest(future=future, method=method)
        payload = encode_message(id=request_id, method=method, params=params)
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(payload)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            del self._pending[request_id]
            raise LspTransportError(f"Failed to send {method}: {exc}") from exc
        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise LspTransportError(
                f"LSP request {method} timed out after {timeout_ms}ms"
            )

    async def send_notification(self, method: str, params: Any | None) -> None:
        if self._closed or self._process is None:
            raise LspTransportClosed("transport not started or closed")
        payload = encode_message(id=None, method=method, params=params)
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(payload)
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise LspTransportError(f"Failed to send notification {method}: {exc}") from exc

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        buffer = b""
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    message, buffer = read_message(buffer)
                    if message is None:
                        break
                    self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Reader died; fail all pending requests.
            for pending in list(self._pending.values()):
                if not pending.future.done():
                    pending.future.set_exception(
                        LspTransportError("LSP stdout reader terminated")
                    )
            self._pending.clear()

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                chunk = await self._process.stderr.read(4096)
                if not chunk:
                    break
                self._stderr_buffer += chunk
                if len(self._stderr_buffer) > 8192:
                    self._stderr_buffer = self._stderr_buffer[-8192:]
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message:
            request_id = message["id"]
            pending = self._pending.pop(request_id, None)
            if pending is None:
                return
            if pending.future.done():
                return
            if "error" in message and message["error"] is not None:
                pending.future.set_exception(
                    LspTransportError(f"LSP error for {pending.method}: {message['error']}")
                )
            else:
                pending.future.set_result(message.get("result"))
        else:
            method = message.get("method")
            if method is None:
                return
            handler = self._notification_handlers.get(method)
            if handler is not None:
                handler(message.get("params"))

    @property
    def stderr_tail(self) -> str:
        return self._stderr_buffer.decode("utf-8", errors="replace")


@dataclass
class _FakeResponseRule:
    """A rule matching a method and returning a canned response.

    If `error` is set, the request fails with that error message.
    Otherwise `result` is returned. `handler` allows dynamic responses.
    """

    result: Any = None
    error: str | None = None
    handler: Callable[[str, Any | None], Any] | None = None
    recorded_calls: list[tuple[str, Any | None]] = field(default_factory=list)


@dataclass
class FakeLspTransport:
    """In-process transport for unit tests; no real subprocess.

    Tests register canned responses via `on(method, ...)` and inspect
    `notifications` and `calls` to verify protocol behavior.
    """

    started: bool = False
    closed: bool = False
    _rules: dict[str, _FakeResponseRule] = field(default_factory=dict)
    notifications: list[tuple[str, Any | None]] = field(default_factory=list)
    calls: list[tuple[str, Any | None, int]] = field(default_factory=list)
    _notification_handlers: dict[str, Callable[[Any], None]] = field(default_factory=dict)

    def on(
        self,
        method: str,
        *,
        result: Any = None,
        error: str | None = None,
        handler: Callable[[str, Any | None], Any] | None = None,
    ) -> _FakeResponseRule:
        rule = _FakeResponseRule(result=result, error=error, handler=handler)
        self._rules[method] = rule
        return rule

    def push_notification(self, method: str, params: Any | None) -> None:
        """Simulate a server-pushed notification to the client."""
        handler = self._notification_handlers.get(method)
        if handler is not None:
            handler(params)

    def register_notification_handler(
        self, method: str, handler: Callable[[Any], None]
    ) -> None:
        self._notification_handlers[method] = handler

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def send_request(
        self, method: str, params: Any | None, *, timeout_ms: int
    ) -> Any:
        self.calls.append((method, params, timeout_ms))
        rule = self._rules.get(method)
        rule_recorded = rule
        if rule is None:
            # Default sensible responses for protocol bootstrap.
            if method == "initialize":
                return {"capabilities": {}}
            return None
        rule.recorded_calls.append((method, params))
        if rule.error is not None:
            raise LspTransportError(rule.error)
        if rule.handler is not None:
            return rule.handler(method, params)
        return rule.result

    async def send_notification(self, method: str, params: Any | None) -> None:
        self.notifications.append((method, params))


# Re-export the protocol symbol for type hints in tests / clients.
__all__ = [
    "FakeLspTransport",
    "LspTransport",
    "LspTransportClosed",
    "LspTransportError",
    "StdioLspTransport",
    "encode_message",
    "read_message",
]

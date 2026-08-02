"""Unit + integration tests for MCP runtime health monitoring.

Covers tasks 6.1-6.3: failure-rate window, auto-degrade / auto-recover,
health-ping task, status snapshot fields, and registry visibility of degraded
servers' tools.
"""
from __future__ import annotations

import asyncio

import pytest

from agent.mcp.manager import McpManager
from agent.mcp.types import (
    DEFAULT_MCP_PERMISSION,
    McpServerStatus,
    McpToolMetadata,
)
from agent.run_config import ModePolicy
from agent.tools.factory import build_default_tool_registry


class _FakeSession:
    def __init__(self, *, ping_fails: bool = False, call_fails: bool = True):
        self.ping_fails = ping_fails
        self.call_fails = call_fails
        self.ping_count = 0

    async def send_ping(self) -> None:
        self.ping_count += 1
        if self.ping_fails:
            raise RuntimeError("ping failed")

    async def call_tool(self, *args, **kwargs):
        if self.call_fails:
            raise RuntimeError("call failed")
        return _FakeResult()


class _FakeResult:
    isError = False
    content = []


class _FakeServerConfig:
    def __init__(self, tool_timeout_seconds: float = 5.0):
        self.tool_timeout_seconds = tool_timeout_seconds


def _manager_with_alpha(**kwargs) -> McpManager:
    m = McpManager(**kwargs)
    m._sessions["alpha"] = _FakeSession(call_fails=True)
    m._server_configs["alpha"] = _FakeServerConfig()
    m._statuses["alpha"] = McpServerStatus(name="alpha", ready=True, tools=1)
    return m


class TestFailureWindow:
    @pytest.mark.asyncio
    async def test_failure_rate_from_call_outcomes(self) -> None:
        m = _manager_with_alpha(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=3,
        )
        for _ in range(4):
            await m.call_tool("alpha", "add", {})
        assert m.failure_rate("alpha") == 1.0
        assert m.is_degraded("alpha") is True

    @pytest.mark.asyncio
    async def test_auto_recovers_when_window_slides(self) -> None:
        m = _manager_with_alpha(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=3,
        )
        for _ in range(4):
            await m.call_tool("alpha", "add", {})
        assert m.is_degraded("alpha") is True

        m._sessions["alpha"] = _FakeSession(call_fails=False)
        for _ in range(6):
            await m.call_tool("alpha", "add", {})
        # Window: 4 failures + 6 successes → 0.4 < 0.5 → recovered.
        assert m.failure_rate("alpha") == pytest.approx(0.4)
        assert m.is_degraded("alpha") is False

    def test_is_tool_degraded_maps_callable_to_server(self) -> None:
        m = McpManager(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=1,
        )
        m._statuses["alpha"] = McpServerStatus(name="alpha", ready=True)
        m._tools["mcp__alpha__add"] = McpToolMetadata(
            server_name="alpha",
            tool_name="add",
            callable_name="mcp__alpha__add",
            description="add",
            input_schema={},
            permission=DEFAULT_MCP_PERMISSION,
        )
        m._record_call("alpha", False)
        assert m.is_tool_degraded("mcp__alpha__add") is True
        assert m.is_tool_degraded("Read") is False


class TestStatusSnapshot:
    def test_status_includes_runtime_health_fields(self) -> None:
        m = McpManager(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=3,
        )
        m._statuses["alpha"] = McpServerStatus(name="alpha", ready=True, tools=2)
        m._health_ok["alpha"] = True
        m._last_health_check["alpha"] = 123.0
        m._record_call("alpha", True)
        m._record_call("alpha", False)

        status = m.status()[0]
        assert status.health_ok is True
        assert status.last_health_check == 123.0
        assert status.calls == 2
        assert status.failures == 1
        assert status.failure_rate == pytest.approx(0.5)
        assert status.degraded is False


class TestHealthMonitor:
    @pytest.mark.asyncio
    async def test_health_ping_success_marks_healthy(self) -> None:
        m = McpManager(ping_timeout_s=1.0)
        session = _FakeSession(ping_fails=False)
        m._sessions["gamma"] = session
        m._statuses["gamma"] = McpServerStatus(name="gamma", ready=True)
        m.start_health_monitor(interval_s=0.02)
        try:
            await asyncio.sleep(0.08)
        finally:
            await m.aclose()
        assert session.ping_count >= 1
        assert m.status()[0].health_ok is True

    @pytest.mark.asyncio
    async def test_health_ping_failure_degrades_server(self) -> None:
        m = McpManager(ping_timeout_s=1.0)
        m._sessions["beta"] = _FakeSession(ping_fails=True)
        m._statuses["beta"] = McpServerStatus(name="beta", ready=True)
        m.start_health_monitor(interval_s=0.02)
        try:
            await asyncio.sleep(0.08)
        finally:
            await m.aclose()
        assert m.is_degraded("beta") is True
        assert m.status()[0].health_ok is False


class TestRegistryVisibility:
    def test_degraded_server_tools_hidden_from_schemas(self) -> None:
        m = McpManager(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=1,
        )
        m._statuses["alpha"] = McpServerStatus(name="alpha", ready=True, tools=1)
        m._tools["mcp__alpha__add"] = McpToolMetadata(
            server_name="alpha",
            tool_name="add",
            callable_name="mcp__alpha__add",
            description="add two numbers",
            input_schema={},
            permission=DEFAULT_MCP_PERMISSION,
        )
        m._record_call("alpha", False)

        registry = build_default_tool_registry(
            mode_policy=ModePolicy(),
            mcp_manager=m,
        )
        names = {s["function"]["name"] for s in registry.get_all_schemas()}
        assert "mcp__alpha__add" not in names

    def test_healthy_server_tools_visible(self) -> None:
        m = McpManager(
            failure_window_size=10,
            degrade_failure_threshold=0.5,
            degrade_min_calls=1,
        )
        m._statuses["alpha"] = McpServerStatus(name="alpha", ready=True, tools=1)
        m._tools["mcp__alpha__add"] = McpToolMetadata(
            server_name="alpha",
            tool_name="add",
            callable_name="mcp__alpha__add",
            description="add two numbers",
            input_schema={},
            permission=DEFAULT_MCP_PERMISSION,
        )
        m._record_call("alpha", True)

        registry = build_default_tool_registry(
            mode_policy=ModePolicy(),
            mcp_manager=m,
        )
        names = {s["function"]["name"] for s in registry.get_all_schemas()}
        assert "mcp__alpha__add" in names

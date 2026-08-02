"""Sandbox wiring tests (design.md Decision 7 — batch-1 gap fix).

Verifies the configured ExecutionBackend flows through the registry builders
into BashTool, that a pre-built tools list is backfilled, and that
``build_sandbox_from_config`` fails fast when the configured backend is
unavailable instead of silently falling back to ProcessBackend.
"""
from __future__ import annotations

import pytest

from agent.config import AsterwyndConfig, SandboxConfig
from agent.tools.builtin.bash import BashTool
from agent.tools.factory import (
    build_coding_tool_registry,
    build_default_tool_registry,
    build_sandbox_from_config,
)
from agent.tools.sandbox import DockerBackend, ProcessBackend
from agent.tools.sandbox.docker_backend import DockerBackend as DockerBackendCls


class FakeBackend:
    def is_available(self) -> bool:
        return True

    async def run(self, command: str, *, timeout=None, cwd=None):
        raise NotImplementedError

    async def run_background(self, command: str, *, cwd=None):
        raise NotImplementedError


def _bash_tool_from(registry):
    return registry.get_tool("Bash")


class TestRegistrySandboxWiring:
    def test_default_registry_passes_sandbox_to_bash(self):
        fake = FakeBackend()
        registry = build_default_tool_registry(sandbox=fake)
        assert _bash_tool_from(registry).sandbox is fake

    def test_coding_registry_passes_sandbox_to_bash(self):
        fake = FakeBackend()
        registry = build_coding_tool_registry(sandbox=fake)
        assert _bash_tool_from(registry).sandbox is fake

    def test_default_registry_builds_process_backend_when_no_sandbox(self):
        registry = build_default_tool_registry()
        assert isinstance(_bash_tool_from(registry).sandbox, ProcessBackend)

    def test_prebuilt_tools_list_is_backfilled_with_sandbox(self):
        fake = FakeBackend()
        tools = [BashTool()]
        registry = build_default_tool_registry(tools=tools, sandbox=fake)
        assert _bash_tool_from(registry).sandbox is fake

    def test_prebuilt_tools_list_without_sandbox_keeps_default(self):
        tools = [BashTool()]
        registry = build_default_tool_registry(tools=tools)
        assert isinstance(_bash_tool_from(registry).sandbox, ProcessBackend)


class TestBuildSandboxFromConfig:
    def test_process_backend(self):
        config = AsterwyndConfig(sandbox=SandboxConfig(backend="process"))
        assert isinstance(build_sandbox_from_config(config), ProcessBackend)

    def test_docker_backend(self):
        config = AsterwyndConfig(sandbox=SandboxConfig(backend="docker"))
        assert isinstance(build_sandbox_from_config(config), DockerBackend)

    def test_unavailable_backend_fails_fast(self, monkeypatch):
        config = AsterwyndConfig(sandbox=SandboxConfig(backend="docker"))
        monkeypatch.setattr(
            DockerBackendCls, "is_available", lambda self: False
        )
        with pytest.raises(RuntimeError, match="unavailable"):
            build_sandbox_from_config(config)


@pytest.mark.asyncio
async def test_background_manager_surfaces_docker_not_implemented():
    """backend=docker + run_in_background must give a clear error, not crash."""
    from agent.background import BackgroundTaskManager

    manager = BackgroundTaskManager(sandbox=DockerBackend())
    with pytest.raises(RuntimeError, match="background task execution is not supported"):
        await manager.start(cmd="echo hi", tool_call_id="t1", cwd="/tmp")

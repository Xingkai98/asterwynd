"""Execution backends for the sandbox boundary.

The command guard (``agent.tools.command_guard``) is the guardrail; the
execution backend is the boundary. ``ProcessBackend`` runs on the host,
``DockerBackend`` runs in an isolated container. ``SandboxExecutor`` was
removed in favor of these backends (design Q10: migrate callers to the factory,
no backward-compat alias).
"""
from __future__ import annotations

from agent.tools.sandbox.base import (
    BackgroundProcessHandle,
    ExecutionBackend,
    SandboxResult,
)
from agent.tools.sandbox.process_backend import ProcessBackend
from agent.tools.sandbox.docker_backend import DockerBackend
from agent.tools.sandbox.factory import build_execution_backend

__all__ = [
    "BackgroundProcessHandle",
    "ExecutionBackend",
    "SandboxResult",
    "ProcessBackend",
    "DockerBackend",
    "build_execution_backend",
]

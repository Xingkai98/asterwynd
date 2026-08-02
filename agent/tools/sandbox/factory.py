"""Execution backend factory — build a backend by name.

``build_execution_backend("process")`` → ProcessBackend (default)
``build_execution_backend("docker")`` → DockerBackend (container isolation)

This is the seam that lets config switch the sandbox strategy without touching
callers (design Q2/Q9).
"""
from __future__ import annotations

from agent.tools.sandbox.base import ExecutionBackend
from agent.tools.sandbox.process_backend import ProcessBackend
from agent.tools.sandbox.docker_backend import DockerBackend

_BACKENDS: dict[str, type[ExecutionBackend]] = {
    "process": ProcessBackend,
    "docker": DockerBackend,
}

# Backend-specific constructor kwargs (config passes a superset; filter per backend).
_BACKEND_KWARGS: dict[str, tuple[str, ...]] = {
    "process": ("timeout", "memory_mb", "cpus"),
    "docker": ("image", "memory_mb", "cpus", "timeout"),
}


def build_execution_backend(name: str, **kwargs) -> ExecutionBackend:
    """Build an ExecutionBackend by name.

    Only backend-specific kwargs are forwarded (config passes a superset).
    Raises ValueError for unknown backend names.
    """
    cls = _BACKENDS.get(name)
    if cls is None:
        raise ValueError(f"unknown execution backend: {name!r} (available: {sorted(_BACKENDS)})")
    accepted = _BACKEND_KWARGS.get(name, ())
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    return cls(**filtered)

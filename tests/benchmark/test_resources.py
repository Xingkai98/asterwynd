"""Tests for benchmarks/resources.py dynamic resource guardrails.

Covers the dynamic concurrency heuristic (suggest_parallel) and the Docker
daemon reachability probe (is_docker_available). See design.md Decision 7c:
concurrency is derived from the current environment, low-resource machines
degrade to a serial run (parallel == 1).
"""
import subprocess
from types import SimpleNamespace

import benchmarks.resources as resources
from benchmarks.resources import is_docker_available, suggest_parallel

GIB = 1024**3


# ---- suggest_parallel -----------------------------------------------------


def test_suggest_parallel_low_resource_returns_one():
    # 7.6 GiB / 4 cores (this machine's ballpark) must degrade to serial.
    assert suggest_parallel(int(7.6 * GIB), 4) == 1


def test_suggest_parallel_tiny_or_zero_memory_returns_one():
    assert suggest_parallel(GIB, 8) == 1
    assert suggest_parallel(0, 4) == 1


def test_suggest_parallel_bad_inputs_return_one():
    assert suggest_parallel(-1, 4) == 1
    assert suggest_parallel(64 * GIB, 0) == 1
    assert suggest_parallel(64 * GIB, -2) == 1
    assert suggest_parallel(64 * GIB, 4, per_task_bytes=0) == 1


def test_suggest_parallel_memory_rich_scales_with_cpu():
    assert suggest_parallel(64 * GIB, 16) == 16
    assert suggest_parallel(64 * GIB, 2) == 2


def test_suggest_parallel_memory_limited_below_cpu():
    assert suggest_parallel(16 * GIB, 16) == 4


def test_suggest_parallel_returns_int():
    result = suggest_parallel(20 * GIB, 6)
    assert isinstance(result, int)
    assert result >= 1


def test_suggest_parallel_respects_per_task_bytes():
    mem = 64 * GIB
    cpu = 16
    assert suggest_parallel(mem, cpu) == 16
    assert suggest_parallel(mem, cpu, per_task_bytes=2 * GIB) == 4


def test_suggest_parallel_defaults_use_machine_values(monkeypatch):
    monkeypatch.setattr(resources, "_mem_available_bytes", lambda: 64 * GIB)
    monkeypatch.setattr(resources, "_cpu_count", lambda: 16)
    assert suggest_parallel() == 16


def test_suggest_parallel_default_is_one_on_low_resource_machine(monkeypatch):
    # Simulate a low-resource machine (e.g. ~3.7 GiB available, 4 cores);
    # the dynamic guardrail must fall back to 1. Using monkeypatched machine
    # values keeps the test environment-independent (CI machines differ).
    monkeypatch.setattr(resources, "_mem_available_bytes", lambda: int(3.7 * GIB))
    monkeypatch.setattr(resources, "_cpu_count", lambda: 4)
    assert resources.suggest_parallel_default() == 1


# ---- is_docker_available --------------------------------------------------


def test_is_docker_available_true_when_info_succeeds(monkeypatch):
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    assert is_docker_available() is True


def test_is_docker_available_false_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="denied"),
    )
    assert is_docker_available() is False


def test_is_docker_available_false_when_docker_missing(monkeypatch):
    def raise_missing(*a, **kw):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(resources.subprocess, "run", raise_missing)
    assert is_docker_available() is False


def test_is_docker_available_false_on_timeout(monkeypatch):
    def raise_timeout(*a, **kw):
        raise subprocess.TimeoutExpired("docker info", 15)

    monkeypatch.setattr(resources.subprocess, "run", raise_timeout)
    assert is_docker_available() is False


def test_is_docker_available_invokes_docker_info(monkeypatch):
    captured = {}

    def fake_run(command, **kw):
        captured["command"] = command
        captured["timeout"] = kw.get("timeout")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(resources.subprocess, "run", fake_run)
    is_docker_available()
    assert captured["command"] == ["docker", "info"]
    assert captured["timeout"] == 15

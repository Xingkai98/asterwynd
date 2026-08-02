"""Contract tests for ExecutionBackend implementations (ProcessBackend/DockerBackend).

Covers design.md 第一/二轮：执行抽象为可插拔 ExecutionBackend，SandboxResult/
BackgroundProcessHandle 为统一返回类型；DockerBackend 用 docker run 容器隔离。
"""
from __future__ import annotations

import pytest

from agent.tools.sandbox.base import ExecutionBackend, SandboxResult
from agent.tools.sandbox.factory import build_execution_backend
from agent.tools.sandbox.process_backend import ProcessBackend
from agent.tools.sandbox.docker_backend import DockerBackend


class TestBackendSelection:
    def test_process_backend_available(self) -> None:
        backend = build_execution_backend("process")
        assert isinstance(backend, ProcessBackend)
        assert backend.is_available() is True

    def test_docker_backend_available(self) -> None:
        """Docker daemon 可用（当前用户属 docker 组，sg docker 访问）"""
        backend = build_execution_backend("docker")
        assert isinstance(backend, DockerBackend)
        # Docker daemon 应可用（本环境已确认）
        assert backend.is_available() is True

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError):
            build_execution_backend("gvisor")


# 参数化：对每个后端跑统一契约（Docker 需 daemon 可用）
@pytest.mark.parametrize(
    "backend",
    [
        pytest.param(ProcessBackend(), id="process"),
        pytest.param(
            DockerBackend(image="alpine:latest"),
            id="docker",
            marks=pytest.mark.skipif(
                not DockerBackend(image="alpine:latest").is_available(),
                reason="Docker daemon 不可用",
            ),
        ),
    ],
)
async def test_contract(backend: ExecutionBackend) -> None:
    """统一契约跑每个后端。"""
    # is_available
    assert isinstance(backend.is_available(), bool)
    # run echo
    result = await backend.run("echo contract-ok", timeout=10.0)
    assert result.exit_code == 0
    assert "contract-ok" in result.stdout
    # run exit code
    assert (await backend.run("exit 7", timeout=10.0)).exit_code == 7
    # run timeout
    timed = await backend.run("sleep 5", timeout=1.0)
    assert timed.timed_out is True

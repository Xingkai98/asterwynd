## Symptom

当前仓库的 `swebench-*` benchmark 任务并不是真正运行在 SWE-bench 官方 Docker harness 上，而是走“clone 外部仓库 + 本地 uv/venv 安装依赖”的半兼容路径。与此同时，当前开发环境位于容器内，默认 DinD 启动方式失败，导致这条能力一直没有真正验证清楚。

## Reproduction

1. 阅读 `benchmarks/runner.py` 中外部任务执行路径，可以看到当前逻辑会 clone 外部仓库，并在本地创建 `.venv` 安装依赖。
2. 运行外部 `swebench-*` task 时，如果本地没有安装 `swebench` Python 包，会出现 `ModuleNotFoundError: No module named 'swebench'`。
3. 在当前容器中直接执行 `docker version` / `docker info`，默认会失败；但手动启动 `containerd` 并让 `dockerd` 连接该 socket 后，`docker run --rm hello-world` 可以成功。

## Evidence

- `benchmarks/runner.py` 当前对外部任务使用 `_clone_external_repo(...)` 和 `_install_repo_deps(...)`，依赖 `swebench.harness.constants`，而不是直接走 Docker harness。
- `docs/testing-guide.md` 当前仍要求外部 SWE-bench 风格任务在本地临时安装 `swebench` 包。
- 当前环境的 PID 1 是 `/usr/local/bin/container-startup.sh`，不是 `systemd`；默认脚本虽然尝试后台启动 `dockerd`，但日志显示其 managed `containerd` 启动超时。
- 手工验证表明：
  - 单独启动 `containerd` 可以成功。
  - 使用 `dockerd --containerd=/run/containerd/containerd.sock --iptables=false --bridge=none --ip-forward=false --ip-masq=false` 可以成功拉起 Docker daemon。
  - `docker run --rm hello-world` 在该手工路径下成功。

## Root Cause

问题有两层：

- 产品层：外部 SWE-bench 任务最初只做到了“借用部分 swebench 常量模拟外部仓库依赖”，没有完成官方 Docker harness 接入。
- 环境层：当前开发环境是容器内开发环境，没有 `systemd`，默认 DinD 启动方式失败，掩盖了“应不应该接 Docker harness”和“如何在当前环境验证它”这两个问题。

## Recommended Direction

本 change 应把核心行为收敛为：

- `swebench-*` 外部任务改用 Docker-based evaluation harness。
- runner 在执行这类任务前做 Docker preflight。
- Docker 不可用时，以显式 `skipped` / `unsupported` artifact 结束，不回退到本地 venv 兼容路径。

当前容器内如何手工启动 Docker daemon 只作为开发辅助：

- 可以补开发文档；
- 可以补一个备用脚本；
- 但不应进入 benchmark 核心规格，更不应让 benchmark CLI 自动负责起 daemon。

## Regression Tests

- benchmark runner 测试覆盖 Docker preflight 成功 / 失败。
- 外部 Docker-based 任务在 Docker 不可用时写出 `skipped` / `unsupported` artifact 的测试。
- 本地 `myagent-*` 任务不受 Docker preflight 影响的混合任务集测试。
- 如环境允许，补一个最小 `swebench-*` Docker smoke；如环境不允许，用 mock/fake runner 覆盖并记录限制。

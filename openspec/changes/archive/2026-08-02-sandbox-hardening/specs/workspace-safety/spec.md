# Workspace Safety Spec

## ADDED Requirements

### Requirement: ExecutionBackend 可插拔沙箱

The sandbox SHALL abstract command execution behind an `ExecutionBackend` interface with pluggable backends: `ProcessBackend` (subprocess, default) and `DockerBackend` (container isolation via `docker run --rm --network none`). Backends SHALL return a unified `SandboxResult` and SHALL be selectable via config.

#### Scenario: Docker 隔离执行

- **GIVEN** a command executed via the docker backend
- **WHEN** the backend runs it in a container
- **THEN** the command runs with network disabled (`--network none`)
- **AND** only the workspace is mounted
- **AND** the container is removed after run

#### Scenario: 后端切换

- **GIVEN** config selects `backend: docker`
- **WHEN** the execution backend is built
- **THEN** a `DockerBackend` is used
- **AND** `backend: process` selects `ProcessBackend`

### Requirement: 命令护栏（轻量分词 + argv 语义校验）

The command guard SHALL validate shell commands via lightweight tokenization and argv semantic checks, SHALL deny dangerous command patterns (rm recursive+force targeting protected/outside paths, redirects to protected paths, pipes to a shell, arbitrary code execution interpreters, exfiltration of sensitive files), SHALL extend the denylist with bypass variants, and SHALL default-allow unknown commands (guardrail, not boundary).

#### Scenario: rm 目标越界拒绝

- **GIVEN** `rm -rf /` or `rm -fr /` or `rm -rf $HOME`
- **WHEN** the command guard checks it
- **THEN** it is denied (flag normalization catches reordering/splitting)

#### Scenario: 重定向到受保护路径拒绝

- **GIVEN** `echo x > /etc/passwd`
- **WHEN** the command guard checks it
- **THEN** it is denied

#### Scenario: 默认放行未知命令

- **GIVEN** an unknown command `my-custom-tool --flag`
- **WHEN** the command guard checks it
- **THEN** it is allowed (default-allow; the backend isolates)

### Requirement: 恶意命令攻击回归集

The sandbox SHALL maintain a data-driven attack suite (`benchmarks/attacks/attacks.json`) of 50+ malicious commands across categories (file-destroy, priv-esc, code-exec, exfil, resource, bypass, sensitive-read), and SHALL assert all guard-deny cases are blocked.

#### Scenario: 攻击集拦截

- **GIVEN** the attack suite cases
- **WHEN** each guard-deny case is checked by the command guard
- **THEN** all are denied

### Requirement: cgroup v2 资源限制

The sandbox SHALL enforce CPU/memory limits for the local `ProcessBackend` via cgroup v2 when configured (`sandbox.memory_mb`/`sandbox.cpus`), SHALL create a per-run ephemeral child cgroup with a unique name, SHALL detect OOM kills and mark the result (`oom_killed`), and SHALL degrade observably (`degraded` flag + `degraded` sandbox event) when the host cannot create a cgroup — never silently ignoring a requested limit.

#### Scenario: 内存限制生效

- **GIVEN** `sandbox.memory_mb` configured and cgroup v2 available
- **WHEN** a command runs via ProcessBackend
- **THEN** the command runs in its own ephemeral cgroup with `memory.max` set
- **AND** an OOM kill marks the result and emits an `oom` sandbox event

#### Scenario: 无 cgroup 环境降级

- **GIVEN** `sandbox.memory_mb` configured but the host cannot create a cgroup
- **WHEN** a command runs via ProcessBackend
- **THEN** the result is marked `degraded`
- **AND** a `degraded` sandbox event is emitted (at most once per backend instance)

### Requirement: 沙箱事件入 trace

The sandbox SHALL emit structured events (`denied`/`kill`/`oom`/`degraded`) into the active `TraceRecorder` through a contextvar sink, SHALL attach the calling `tool_call_id` and a truncated command, and SHALL be backward-compatible with the trace event schema (new `sandbox` step type; `schema_version` unchanged).

#### Scenario: 命令拒绝事件

- **GIVEN** a command denied by workspace policy or the command guard
- **WHEN** the Bash tool rejects it
- **THEN** a `sandbox` `denied` event with the rejection reason is recorded in the trace

#### Scenario: 超时 kill 事件

- **GIVEN** a command exceeding its timeout (foreground or background)
- **WHEN** the backend or background manager kills the process tree
- **THEN** a `sandbox` `kill` event is recorded

## MODIFIED Requirements

### Requirement: 命令执行抽象

`agent-runtime` 的命令执行 SHALL 使用 `ExecutionBackend`（可插拔沙箱），替代 `SandboxExecutor`；调用方（main/background/bash/__init__）SHALL 通过 `build_execution_backend(name)` 构建后端。`SandboxExecutor` SHALL 被移除（不留向后兼容别名）。config 的 `sandbox.backend` SHALL 生效于前台 Bash 工具（不仅是后台任务）：`main.py`/`web/session.py`/`benchmarks/agent_runner.py` 构建的后端 SHALL 透传进 BashTool，后端不可用 SHALL fail-fast（不静默回退到 process）。

#### Scenario: 迁移后无 SandboxExecutor

- **GIVEN** the codebase after migration
- **WHEN** searching for `SandboxExecutor`
- **THEN** no references remain (callers use the factory)

#### Scenario: config 后端对前台 Bash 生效

- **GIVEN** `sandbox.backend: docker` configured
- **WHEN** the agent registry is built
- **THEN** the Bash tool's execution backend is the configured DockerBackend

#### Scenario: 后端不可用 fail-fast

- **GIVEN** `sandbox.backend: docker` configured but the Docker daemon is unreachable
- **WHEN** the agent core is built
- **THEN** startup fails with a clear error (no silent fallback to process)

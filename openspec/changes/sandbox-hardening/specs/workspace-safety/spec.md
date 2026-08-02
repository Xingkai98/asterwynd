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

## MODIFIED Requirements

### Requirement: 命令执行抽象

`agent-runtime` 的命令执行 SHALL 使用 `ExecutionBackend`（可插拔沙箱），替代 `SandboxExecutor`；调用方（main/background/bash/__init__）SHALL 通过 `build_execution_backend(name)` 构建后端。`SandboxExecutor` SHALL 被移除（不留向后兼容别名）。

#### Scenario: 迁移后无 SandboxExecutor

- **GIVEN** the codebase after migration
- **WHEN** searching for `SandboxExecutor`
- **THEN** no references remain (callers use the factory)

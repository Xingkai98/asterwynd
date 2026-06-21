# workspace-safety 规格

## Purpose

定义 WorkspacePolicy 提供的路径、敏感文件、命令执行和 git diff 安全边界。当前实现位于 `agent/workspace_policy.py`；Write、Edit、ListFiles、Find、InspectGitDiff 和 benchmark MyAgentRunner 中的 Bash 使用该策略，Read 和 Grep 当前不依赖该策略。

## Requirements

### Requirement: WorkspacePolicy 路径必须限制在 workspace 内

WorkspacePolicy SHALL 解析路径并阻止越过 workspace root 的读写访问。

#### Scenario: 路径逃逸

- **GIVEN** 工具请求访问 workspace 外路径
- **WHEN** policy 校验路径
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

### Requirement: 敏感文件写入默认拒绝

WorkspacePolicy SHALL 在写入校验中拒绝匹配 denied patterns 的文件，例如本地环境变量、私密配置和生成目录。当前 `assert_read_allowed` 只校验路径位于 workspace 内，不校验 denied patterns。

#### Scenario: 写入 `.env`

- **GIVEN** 工具请求写入被 deny pattern 命中的路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 读取 denied pattern 路径

- **GIVEN** 调用方直接使用 `assert_read_allowed`
- **WHEN** 路径位于 workspace 内但命中 denied pattern
- **THEN** 当前 WorkspacePolicy SHALL 允许该读路径通过

### Requirement: 命令执行受 denylist 和 allowlist 控制

WorkspacePolicy SHALL 在 Bash 执行前检查命令；allowlist 命令可直接通过，denylist 命中的命令必须拒绝。

#### Scenario: 命令命中 denylist

- **GIVEN** Bash 请求执行危险命令
- **WHEN** `assert_command_allowed` 发现命中 denylist
- **THEN** 系统 SHALL 抛出权限错误

### Requirement: git diff 快照在 workspace root 执行

WorkspacePolicy SHALL 在 workspace root 下执行 git diff，并返回 diff 输出、diff stat 或无变更提示。

#### Scenario: 获取 diff stat

- **GIVEN** 调用方请求 stat 模式
- **WHEN** policy 执行 diff 快照
- **THEN** 系统 SHALL 运行 `git diff --stat`
- **AND** 返回标准输出或错误输出

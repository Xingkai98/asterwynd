# workspace-safety 规格

## Purpose

定义 WorkspacePolicy 提供的路径、敏感文件、命令执行和 git diff 安全边界。当前实现位于 `agent/workspace_policy.py`；Read、Write、Edit、Grep、ListFiles、Find、InspectGitDiff 和 Bash 均通过工具集合注入 workspace policy。
## Requirements
### Requirement: WorkspacePolicy 路径必须限制在 workspace 内

WorkspacePolicy SHALL 解析路径并阻止越过 workspace root 的读写访问。读权限和写权限校验 SHALL 都执行 workspace root 边界检查。

#### Scenario: 读路径逃逸

- **GIVEN** 工具请求读取 workspace 外路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

#### Scenario: 写路径逃逸

- **GIVEN** 工具请求写入 workspace 外路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

### Requirement: 敏感文件读写默认拒绝

WorkspacePolicy SHALL 在面向 agent tool 的读写校验中拒绝匹配 denied patterns 的路径，例如本地环境变量、私密配置、版本控制内部目录、虚拟环境、依赖目录和生成目录。

#### Scenario: 写入 `.env`

- **GIVEN** 工具请求写入被 denied pattern 命中的路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 读取 `.env`

- **GIVEN** 工具请求读取被 denied pattern 命中的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 普通 agent tool 不绕过 read policy

- **GIVEN** 普通 agent tool 请求读取 read policy 拒绝的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作
- **AND** SHALL NOT 为普通 agent tool 提供隐式绕过

### Requirement: 命令执行受 denylist 和 allowlist 控制

WorkspacePolicy SHALL 在 Bash 执行前检查命令。命令检查 SHALL 先应用 denylist，再应用 allowlist；命中 denylist 的命令 MUST 被拒绝，即使该命令同时匹配 allowlist。allowlist SHALL 只包含验证、只读查看和明确低风险的开发命令，不得用宽泛前缀放行任意脚本执行或敏感文件搬运。

#### Scenario: 命令命中 denylist

- **GIVEN** Bash 请求执行危险命令
- **WHEN** `assert_command_allowed` 发现命中 denylist
- **THEN** 系统 SHALL 抛出权限错误

#### Scenario: denylist 覆盖 allowlist

- **GIVEN** Bash 请求执行同时匹配 allowlist 前缀和 denylist 模式的命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

#### Scenario: 拒绝任意 Python 代码执行

- **GIVEN** Bash 请求执行 `python -c` 或 `python3 -c`
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

#### Scenario: 允许 Python pytest 验证命令

- **GIVEN** Bash 请求执行 `python -m pytest` 或 `python3 -m pytest`
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令

#### Scenario: 拒绝敏感文件搬运

- **GIVEN** Bash 请求通过 `cp` 或 `mv` 读取系统敏感路径或移动 workspace denied pattern 文件
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

### Requirement: 工作区策略支持配置扩展

WorkspacePolicy SHALL 保留内置 denied patterns 和 command denylist，并允许入口层通过统一配置追加项目级 command denylist。ListFiles 和 Find SHALL 保留内置 ignore rules，并允许入口层通过统一配置追加项目级 ignore patterns。

#### Scenario: YAML command denylist 扩展

- **GIVEN** 统一配置包含 `tools.command_denylist`
- **WHEN** Bash 工具校验命令
- **THEN** 系统 SHALL 同时应用内置 denylist 和配置扩展

#### Scenario: YAML ignore patterns 扩展

- **GIVEN** 统一配置包含 `tools.ignore_patterns`
- **WHEN** ListFiles 或 Find 枚举目录
- **THEN** 系统 SHALL 同时应用内置 ignore rules 和配置扩展

#### Scenario: 允许常规验证和只读查看命令

- **GIVEN** Bash 请求执行 `pytest`、`uv run pytest`、`git diff`、`rg`、`cat` 或 `ls` 等允许命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令

### Requirement: git diff 快照在 workspace root 执行

WorkspacePolicy SHALL 在 workspace root 下执行 git diff，并返回 diff 输出、diff stat 或无变更提示。

#### Scenario: 获取 diff stat

- **GIVEN** 调用方请求 stat 模式
- **WHEN** policy 执行 diff 快照
- **THEN** 系统 SHALL 运行 `git diff --stat`
- **AND** 返回标准输出或错误输出

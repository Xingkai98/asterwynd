## MODIFIED Requirements

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

#### Scenario: 允许常规验证和只读查看命令

- **GIVEN** Bash 请求执行 `pytest`、`uv run pytest`、`git diff`、`rg`、`cat` 或 `ls` 等允许命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令


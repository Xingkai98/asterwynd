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

#### Scenario: tree-sitter 不绕过 read policy

- **GIVEN** denied path 下存在已注册语言文件
- **WHEN** RepoMap 或 SymbolSearch 扫描 workspace
- **THEN** 系统 SHALL 跳过该文件
- **AND** SHALL NOT 通过 tree-sitter 读取或返回该文件中的符号

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

### Requirement: WorkspacePolicy remains an execution boundary

工具 capability 和 mode profile SHALL 决定 tool 是否对 LLM 可见以及是否允许执行；WorkspacePolicy SHALL 继续作为路径、敏感文件、命令和 workspace 边界的执行前强制校验，不得被 capability metadata 绕过。

#### Scenario: capability 允许但 workspace policy 拒绝

- **GIVEN** 当前 mode profile 允许某个 workspace read tool
- **AND** 该 tool 请求读取 denied path
- **WHEN** WorkspacePolicy 校验该路径
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: capability 允许但命令 policy 拒绝

- **GIVEN** 当前 mode profile 允许某个命令执行工具
- **AND** 该 tool 请求执行命中 command denylist 的命令
- **WHEN** WorkspacePolicy 校验该命令
- **THEN** 系统 SHALL 拒绝该操作

### Requirement: MCP actions 必须声明权限边界

MCP-backed tools、prompt 读取和 resource 读取 SHALL 声明 capability / risk / origin 权限元数据，并受 agent mode policy 约束。未显式配置的 MCP action SHALL 默认为 `origin=mcp`、`capabilities=[external_side_effect]`、`risk_level=high`；MCP server 自身 annotation SHALL NOT 作为最终权限判定依据。

#### Scenario: MCP tool 被 mode 禁止

- **GIVEN** 当前 mode 不允许 MCP action 所需 capability
- **WHEN** MCP server 暴露该 tool
- **THEN** 系统 SHALL 不向 LLM 暴露该工具
- **AND** 直接执行该工具 SHALL 返回权限错误

#### Scenario: MCP prompt/resource 读取需要审批

- **GIVEN** 当前 mode 对某个 MCP prompt/resource 读取要求审批
- **WHEN** 用户通过 slash command 读取该 prompt/resource 且未批准
- **THEN** 系统 SHALL 返回 approval required 文本
- **AND** SHALL NOT 调用远端 MCP server

#### Scenario: 本地配置降低 MCP 读取权限

- **GIVEN** 本地配置将某个 MCP server 的 resource 读取声明为 `network_read` + `low`
- **WHEN** 当前 mode 允许该 capability 和 risk
- **THEN** 系统 SHALL 允许读取该 resource

### Requirement: browser artifacts 存储受 workspace policy 约束

Browser screenshots、HTML snapshots 和日志 artifacts SHALL 保存到 workspace policy 允许的目录（`<workspace_root>/.asterwynd/browser-artifacts/`），写入前 SHALL 通过 `WorkspacePolicy.assert_write_allowed()` 校验。

#### Scenario: browser artifact 路径被拒绝

- **GIVEN** browser tool 请求保存 artifact 到 denied path
- **WHEN** WorkspacePolicy 校验写入路径
- **THEN** 系统 SHALL 拒绝保存

### Requirement: Workflow 绑定 Workspace 写权限

受 Workflow Control Plane 管理的 agent run SHALL 将写权限绑定到当前 WorkItem 指定的 workspace 和 workflow version。进入 design 后，业务代码和 change 文档写入 SHALL 只允许发生在绑定 worktree；处于 gate、blocked 或 stale state 时 SHALL fail closed。

#### Scenario: Requirements 阶段禁止业务代码写入

- **GIVEN** workflow 处于 exploring 或 requirements
- **WHEN** agent 尝试修改业务代码
- **THEN** workspace policy SHALL 拒绝写入
- **AND** SHALL 提示当前阶段只允许讨论和需求 artifact 操作

#### Scenario: Design 阶段写入绑定 Worktree

- **GIVEN** workflow 已绑定 worktree A
- **WHEN** agent 尝试在 canonical main repository 写入 design artifact
- **THEN** workspace policy SHALL 拒绝写入
- **AND** SHALL 指示使用 worktree A

#### Scenario: Gate 后拒绝写入

- **GIVEN** workflow 处于任一 `ready_for_review` gate
- **WHEN** agent 尝试写文件或运行产生修改的命令
- **THEN** workspace policy SHALL 拒绝操作

#### Scenario: Stale WorkItem 拒绝写入

- **GIVEN** agent 的 WorkItem version 低于控制面当前 version
- **WHEN** agent 尝试执行写操作
- **THEN** workspace policy SHALL 拒绝操作
- **AND** SHALL 要求重新 enter 获取当前 WorkItem

#### Scenario: 非隔离 Executor 降级

- **GIVEN** executor host 无法保护控制面数据库和 approval capability
- **WHEN** workflow 为该 executor 分配任务
- **THEN** 系统 SHALL 将 enforcement level 标记为 audit-only 或拒绝执行
- **AND** SHALL NOT 宣称该环境具备强制可信 Gate

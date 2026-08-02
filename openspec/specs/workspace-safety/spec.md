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

### Requirement: ExecutionBackend 可插拔沙箱

沙箱 SHALL 将命令执行抽象为 `ExecutionBackend` 接口，提供可插拔后端：`ProcessBackend`（subprocess，默认）与 `DockerBackend`（`docker run --rm --network none` 容器隔离）。后端 SHALL 返回统一 `SandboxResult`，SHALL 可通过 config 选择。

#### Scenario: Docker 隔离执行

- **GIVEN** 通过 docker 后端执行命令
- **WHEN** 后端在容器内运行
- **THEN** 命令 SHALL 在 `--network none` 下运行
- **AND** 只挂载 workspace
- **AND** 运行后容器 SHALL 被移除

#### Scenario: 后端切换

- **GIVEN** config 选择 `backend: docker`
- **WHEN** 构建执行后端
- **THEN** 使用 `DockerBackend`
- **AND** `backend: process` 选择 `ProcessBackend`

### Requirement: 命令护栏（轻量分词 + argv 语义校验）

命令护栏 SHALL 通过轻量分词与 argv 语义校验验证 shell 命令，SHALL 拒绝危险命令模式（rm 递归+强制目标越界、重定向到受保护路径、管道到 shell、任意代码执行解释器、敏感文件外传），SHALL 扩展 denylist 覆盖绕过变体，SHALL 默认放行未知命令（护栏不是边界）。

#### Scenario: rm 目标越界拒绝

- **GIVEN** `rm -rf /` 或 `rm -fr /` 或 `rm -rf $HOME`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（flag 归一化捕获重排/拆分）

#### Scenario: 重定向到受保护路径拒绝

- **GIVEN** `echo x > /etc/passwd`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝

#### Scenario: 默认放行未知命令

- **GIVEN** 未知命令 `my-custom-tool --flag`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（default-allow；后端负责隔离）

### Requirement: 恶意命令攻击回归集

沙箱 SHALL 维护数据驱动攻击集（`benchmarks/attacks/attacks.json`），包含 50+ 恶意命令（file-destroy/priv-esc/code-exec/exfil/resource/bypass/sensitive-read 分类），SHALL 断言所有 guard-deny case 被拦截。

#### Scenario: 攻击集拦截

- **GIVEN** 攻击集 cases
- **WHEN** 每个 guard-deny case 被命令护栏校验
- **THEN** 全部 SHALL 被拒绝

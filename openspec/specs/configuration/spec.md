# configuration 规格

## Purpose

定义 Asterwynd 的结构化配置文件、环境变量覆盖和入口层配置解析规则。当前实现位于 `agent/config.py`，入口层包括 CLI、Web 和 benchmark。
## Requirements
### Requirement: 支持结构化 YAML 配置

系统 SHALL 支持从 `asterwynd.yaml` 读取结构化非敏感配置。缺失配置文件时，系统 SHALL 使用环境变量和代码默认值继续启动；发现非法配置文件时，系统 SHALL fail fast 并返回可读错误。

#### Scenario: 未提供 YAML 配置

- **GIVEN** 当前工作区没有可发现的 `asterwynd.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用代码默认值和支持的环境变量
- **AND** SHALL NOT 因配置文件缺失而启动失败

#### Scenario: 环境变量使用正式前缀

- **GIVEN** 用户设置 `ASTERWYND_MODE` 或 `ASTERWYND_BENCHMARK_PARALLEL`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用 `ASTERWYND_*` 环境变量覆盖对应 YAML 配置
- **AND** 系统 SHALL NOT 接受旧 `MYAGENT_*` 前缀作为兼容入口

### Requirement: 配置优先级明确

系统 SHALL 使用 `CLI 显式参数 > 进程环境变量 > .env 加载值 > asterwynd.yaml > 默认值` 的优先级解析配置。CLI 入口 SHALL 用 `None` 表示用户未显式传参，避免默认 CLI 参数覆盖 YAML。

#### Scenario: CLI 参数覆盖 YAML

- **GIVEN** `asterwynd.yaml` 设置了默认 mode
- **AND** 用户显式传入 `--mode`
- **WHEN** CLI 构造运行配置
- **THEN** CLI 参数 SHALL 覆盖 YAML 默认 mode

#### Scenario: 环境变量覆盖 YAML

- **GIVEN** `asterwynd.yaml` 和支持的环境变量同时设置同一配置项
- **WHEN** 系统解析最终配置
- **THEN** 环境变量值 SHALL 覆盖 YAML 值

### Requirement: 配置文件发现受工作区边界约束

系统 SHALL 支持通过 `--config <path>` 显式指定配置文件；未显式指定时，系统 SHALL 从当前工作目录开始向上查找 `asterwynd.yaml`，并在 git repo 根目录停止。

#### Scenario: 子目录启动

- **GIVEN** 用户从仓库子目录启动 CLI
- **AND** 仓库根目录存在 `asterwynd.yaml`
- **WHEN** 系统发现配置文件
- **THEN** 系统 SHALL 读取仓库根目录的配置文件
- **AND** 系统 SHALL NOT 继续查找旧 `myagent.yaml`

### Requirement: 配置只在入口层解析

系统 SHALL 在 CLI、Web 和 benchmark 入口层解析配置，并将结果显式传入下层对象。底层 `AgentRunConfig()` SHALL NOT 隐式读取 YAML。

#### Scenario: 内部默认 run config

- **GIVEN** 当前工作区存在 `asterwynd.yaml`
- **WHEN** 内部代码直接构造默认 `AgentRunConfig`
- **THEN** 默认 mode SHALL 仍为代码默认值 `build`

#### Scenario: benchmark worktree 不重新发现配置

- **GIVEN** benchmark runner 为任务创建临时 worktree
- **WHEN** runner 构造 AgentLoop 和工具策略
- **THEN** 系统 SHALL 使用入口层已解析配置
- **AND** SHALL NOT 在任务 worktree 中重新发现 `asterwynd.yaml`

### Requirement: 工具策略支持 code intelligence 配置

系统 SHALL 支持在 `asterwynd.yaml` 的 `tools.code_intelligence` 下配置 code intelligence 工具策略。非法值 SHALL fail fast。

#### Scenario: 配置 tree-sitter 单文件解析上限

- **GIVEN** `asterwynd.yaml` 设置 `tools.code_intelligence.tree_sitter_max_file_bytes`
- **WHEN** CLI、Web 或 benchmark 入口构造工具集合
- **THEN** 系统 SHALL 将该值传入 RepoMap 和 SymbolSearch 使用的 code intelligence 配置
- **AND** 超过该大小的 tree-sitter 文件 SHALL 降级为文件级条目

### Requirement: 配置声明 skill roots

系统 SHALL 支持在 `asterwynd.yaml` 的 `skills.roots` 下配置本地 skill roots。入口层配置解析 SHALL 总是把配置文件所在目录的 repo-local `skills/` 作为第一 root；`skills.roots` 中的路径作为追加 roots，按声明顺序加载。缺失配置文件时，默认 root SHALL 为启动目录下的 `skills/`。

#### Scenario: Skill roots configured

- **GIVEN** `asterwynd.yaml` 包含 `skills.roots`
- **WHEN** 系统加载配置
- **THEN** 每个 root SHALL 被解析为文件系统路径
- **AND** `~` 和环境变量 SHALL 被展开
- **AND** 相对路径 SHALL 以配置文件所在目录为基准解析

#### Scenario: Skill roots omitted

- **GIVEN** 配置省略 `skills.roots`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用 repo-local `skills/` 作为 skill root

#### Scenario: Skill roots order

- **GIVEN** 配置声明了追加 skill roots
- **WHEN** skill runtime 加载 skills
- **THEN** repo-local `skills/` SHALL 先于追加 roots 加载
- **AND** 后续 roots 中的重复 skill name SHALL NOT 覆盖先加载的 skill

#### Scenario: Invalid skill roots config

- **GIVEN** `skills.roots` 不是字符串列表
- **WHEN** 系统加载配置
- **THEN** 配置加载 SHALL fail fast
- **AND** 返回可读错误

### Requirement: Permission profile configuration SHALL support bounded customization

系统 SHALL 支持在统一配置中为既有 Agent Mode 选择内置 permission profile，或定义自定义 permission profile。自定义 profile SHALL 只扩展权限判定参数，不得新增 Agent Mode 或改变 AgentLoop mode 语义。系统 SHALL fail fast 校验未知 capability、risk level、permission profile、tool name 和互相矛盾的 profile 配置。

#### Scenario: 使用内置 permission profile

- **GIVEN** 配置为某个 mode 选择内置 permission profile
- **WHEN** 系统构造 ModePolicy
- **THEN** ModePolicy SHALL 使用该 profile 判定工具权限

#### Scenario: 未知 permission profile

- **GIVEN** 配置引用未知 permission profile
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast 并返回可读配置错误

#### Scenario: 自定义 permission profile

- **GIVEN** 配置定义一个 permission profile
- **AND** 该 profile 声明 allowed capabilities、auto-approve risk threshold、approval-required risk threshold 和 denied tools
- **WHEN** 系统构造 ModePolicy
- **THEN** ModePolicy SHALL 使用该自定义 profile 判定工具权限

#### Scenario: 自定义 Agent Mode 不在本 change 范围

- **GIVEN** 配置尝试新增未知 Agent Mode
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast
- **AND** 错误信息 SHALL 说明本 change 只支持自定义 permission profile，不支持自定义 Agent Mode

### Requirement: 配置支持 MCP servers

系统 SHALL 支持在 `asterwynd.yaml` 顶层 `mcp.servers` 下声明 MCP server。MCP 配置 SHALL 与 `tools` 配置分离。非法 transport、缺失必需字段、非法 timeout、非法权限 capability 或 risk level SHALL fail fast 并返回可读配置错误。

#### Scenario: 配置 stdio MCP server

- **GIVEN** `asterwynd.yaml` 声明 `mcp.servers.local_math.type: stdio`
- **AND** 声明 `command`、可选 `args`、`cwd` 和 `env`
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 包含该 stdio server
- **AND** 相对 `cwd` SHALL 以配置文件所在目录为基准解析

#### Scenario: 配置 Streamable HTTP MCP server

- **GIVEN** `asterwynd.yaml` 声明 `mcp.servers.docs.type: streamable_http`
- **AND** 声明 `url` 和可选 headers
- **WHEN** 系统加载配置
- **THEN** 配置对象 SHALL 包含该 Streamable HTTP server

#### Scenario: 配置 MCP action 权限

- **GIVEN** `asterwynd.yaml` 为 MCP server 或单个 tool/prompt/resource 声明 capability 和 risk level
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 校验这些权限字段
- **AND** 在构造 MCP action 权限时使用本地配置覆盖默认保守权限

#### Scenario: MCP 配置不在 tools 下

- **GIVEN** `asterwynd.yaml` 将 MCP server 配置写入 `tools.mcp`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL fail fast
- **AND** 错误信息 SHALL 指向顶层 `mcp.servers`

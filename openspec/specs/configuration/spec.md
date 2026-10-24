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

### Requirement: 工具策略支持 allowed_write_paths 配置

系统 SHALL 支持在 `asterwynd.yaml` 的 `tools.allowed_write_paths` 下配置项目级**显式可写豁免**列表，形态与本仓既有的 `tools.command_denylist` / `tools.ignore_patterns` 同构。该字段的默认值 SHALL 为空列表——未配置时系统 SHALL 保持引入该能力前的路径拒绝行为，SHALL NOT 因新字段存在而改变任何默认判定。非法值 SHALL fail fast。

#### Scenario: 未配置该字段时行为不变

- **GIVEN** `asterwynd.yaml` 未包含 `tools.allowed_write_paths`
- **WHEN** CLI、Web 或 benchmark 入口构造工具策略
- **THEN** 豁免列表 SHALL 为空
- **AND** 所有路径拒绝判定 SHALL 与引入该能力前逐条一致

#### Scenario: 配置合法豁免列表

- **GIVEN** `asterwynd.yaml` 设置 `tools.allowed_write_paths: ['.env', 'config/.env']`
- **WHEN** 系统加载配置
- **THEN** 该列表 SHALL 被解析为元组并按声明顺序保留
- **AND** 三个入口层 SHALL 把该值传入 WorkspacePolicy

#### Scenario: 非法值 fail fast

- **GIVEN** `asterwynd.yaml` 的 `tools.allowed_write_paths` 含 glob 元字符、绝对路径、含 `..` 段的路径或以 `/` 结尾的目录形式
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 抛出配置错误并给出可读的逐条说明
- **AND** SHALL NOT 以宽容解析继续启动

### Requirement: 群聊讨论链安全阀可配置

系统 SHALL 允许通过 `asterwynd.yaml` 的 `team:` 配置节配置群聊讨论链的安全阀：`discussion_max_rounds`（正整数，缺省 200）、`discussion_max_turns`（正整数，缺省 600）、`discussion_max_seconds`（正数，缺省 6000）。缺失配置时 SHALL 使用缺省值；`0`、负数、非数值、以及 YAML 布尔值（`true`/`false`）SHALL 视为非法，在配置加载阶段 fail fast，抛出可读 `ConfigError` 并拒绝启动。这三个参数 SHALL 只作用于 `discussion_mode = unlimited` 的讨论链，SHALL NOT 改变 `discussion_mode = single` 模式的轮次预算（后者沿用既有 `extra_turns` / `admin_extra_turns` / `turns_each` / `admin_turns_each`）。配置在 Web 进程启动期一次性解析；编排器在 workspace 首次懒构造时注入并缓存。链启动时快照，运行中修改配置文件 SHALL NOT 影响已启动的链或未重启的进程。

#### Scenario: 缺省值

- **GIVEN** 当前工作区没有 `team:` 配置节
- **WHEN** Web 入口加载配置
- **THEN** 讨论链安全阀 SHALL 为 200 轮 / 600 成员回合 / 6000 秒

#### Scenario: 覆盖值生效

- **GIVEN** `asterwynd.yaml` 设置 `team.discussion_max_rounds: 3`
- **WHEN** Web 入口加载配置并新建讨论链
- **THEN** 该链的轮数安全阀 SHALL 为 3

#### Scenario: 非法值 fail fast

- **GIVEN** `asterwynd.yaml` 把 `team.discussion_max_rounds` 写成 `0`、`-1`、字符串或 `true`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 抛出可读 `ConfigError`
- **AND** SHALL NOT 以半解析状态启动 Web 服务

#### Scenario: 配置修改需重启生效

- **GIVEN** Web 进程已启动并加载了 `team.discussion_max_rounds: 3`
- **WHEN** 用户把 YAML 改为 `5` 但不重启进程
- **THEN** 新启动的讨论链 SHALL 仍使用 3
- **AND** 重启 Web 进程后新链 SHALL 使用 5

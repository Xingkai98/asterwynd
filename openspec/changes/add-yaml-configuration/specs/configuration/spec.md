## ADDED Requirements

### Requirement: 支持结构化 YAML 配置

系统 SHALL 支持从 `myagent.yaml` 读取结构化非敏感配置，并保留 `.env` 作为 secrets 和环境变量覆盖入口。

#### Scenario: 未提供 YAML 配置

- **GIVEN** 工作区没有 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用代码默认值和环境变量
- **AND** SHALL NOT 因配置文件缺失而启动失败

#### Scenario: 显式配置文件路径

- **GIVEN** CLI 入口传入 `--config <path>`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 只读取该显式配置文件
- **AND** 如果该文件不存在或非法，系统 SHALL 启动失败并显示可读配置错误

#### Scenario: 配置发现不进入 benchmark worktree

- **GIVEN** benchmark runner 为任务创建临时 worktree
- **WHEN** runner 构造 AgentLoop 和工具策略
- **THEN** 系统 SHALL 使用入口层已经解析的配置
- **AND** SHALL NOT 在任务 worktree 中重新发现 `myagent.yaml`

#### Scenario: 读取 YAML 配置

- **GIVEN** 工作区存在合法 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 返回 typed config 对象
- **AND** 支持 agent、modes、tools 和 benchmark 等结构化字段

#### Scenario: 非法 YAML 配置启动失败

- **GIVEN** 工作区存在非法 `myagent.yaml`
- **WHEN** CLI、Web 或 benchmark 入口加载配置
- **THEN** 系统 SHALL 启动失败并显示可读配置错误
- **AND** SHALL NOT 静默退回默认值

### Requirement: 配置优先级明确

系统 SHALL 使用 `CLI 显式参数 > 进程环境变量 > .env 加载值 > myagent.yaml > 默认值` 的优先级解析配置。

#### Scenario: 环境变量覆盖 YAML

- **GIVEN** `myagent.yaml` 和环境变量同时设置同一配置项
- **WHEN** 系统解析最终配置
- **THEN** 环境变量值 SHALL 覆盖 YAML 值

#### Scenario: CLI 参数覆盖环境变量

- **GIVEN** CLI 参数和环境变量同时设置同一配置项
- **WHEN** CLI 构造运行配置
- **THEN** CLI 参数值 SHALL 覆盖环境变量值

#### Scenario: 默认 mode 作用于入口层

- **GIVEN** `myagent.yaml` 配置了 `agent.default_mode`
- **AND** CLI、Web 或 benchmark 入口没有显式传入 mode
- **WHEN** 入口构造 AgentLoop 或 agent runner
- **THEN** 系统 SHALL 使用 `agent.default_mode` 作为最终 mode
- **AND** benchmark artifact SHALL 记录最终解析后的 mode

#### Scenario: 底层 run config 不隐式读取 YAML

- **GIVEN** 工作区存在 `myagent.yaml`
- **WHEN** 内部代码直接构造默认 `AgentRunConfig`
- **THEN** 默认 mode SHALL 仍为代码默认值 `build`

### Requirement: mode deny override 可配置

系统 SHALL 支持在结构化配置中为 agent mode 定义工具 deny override。

`deny_tools` SHALL 使用工具 schema 和 tool call 中暴露的工具公开名，并进行大小写敏感匹配。

#### Scenario: deny tool 不暴露 schema

- **GIVEN** `myagent.yaml` 为某个 mode 配置了 `deny_tools`
- **WHEN** 系统以该 mode 获取工具 schema
- **THEN** 被 deny 的工具 SHALL 不出现在 schema 中

#### Scenario: deny tool 执行拒绝

- **GIVEN** 工具调用命中当前 mode 的 `deny_tools`
- **WHEN** ToolRegistry 执行该调用
- **THEN** 系统 SHALL 返回可读权限错误作为 tool result

#### Scenario: 未知 deny tool 启动失败

- **GIVEN** `myagent.yaml` 的 `deny_tools` 包含未知工具名
- **WHEN** CLI、Web 或 benchmark 入口构造工具注册表
- **THEN** 系统 SHALL 启动失败并显示可读配置错误

### Requirement: 工具策略从 YAML 读取

系统 SHALL 从 `myagent.yaml` 读取工具 ignore patterns 和 command denylist 扩展，并将这些扩展追加到代码内置默认安全规则。

#### Scenario: YAML ignore patterns 追加到内置规则

- **GIVEN** `myagent.yaml` 配置了 `tools.ignore_patterns`
- **WHEN** ListFiles 或 Find 执行目录枚举
- **THEN** 系统 SHALL 同时应用内置 ignore 规则和 YAML ignore 扩展
- **AND** `MYAGENT_IGNORE_PATTERNS` SHALL NOT 作为工具策略配置入口

#### Scenario: YAML command denylist 追加到内置规则

- **GIVEN** `myagent.yaml` 配置了 `tools.command_denylist`
- **WHEN** Bash 工具校验命令
- **THEN** 系统 SHALL 同时应用内置 command denylist 和 YAML denylist 扩展
- **AND** `MYAGENT_COMMAND_DENYLIST` SHALL NOT 作为工具策略配置入口

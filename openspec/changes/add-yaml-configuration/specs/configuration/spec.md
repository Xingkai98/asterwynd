## ADDED Requirements

### Requirement: 支持结构化 YAML 配置

系统 SHALL 支持从 `myagent.yaml` 读取结构化非敏感配置，并保留 `.env` 作为 secrets 和环境变量覆盖入口。

#### Scenario: 未提供 YAML 配置

- **GIVEN** 工作区没有 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用代码默认值和环境变量
- **AND** SHALL NOT 因配置文件缺失而启动失败

#### Scenario: 读取 YAML 配置

- **GIVEN** 工作区存在合法 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 返回 typed config 对象
- **AND** 支持 agent、modes、tools 和 benchmark 等结构化字段

### Requirement: 配置优先级明确

系统 SHALL 使用 `CLI 参数 > 环境变量 > myagent.yaml > 默认值` 的优先级解析配置。

#### Scenario: 环境变量覆盖 YAML

- **GIVEN** `myagent.yaml` 和环境变量同时设置同一配置项
- **WHEN** 系统解析最终配置
- **THEN** 环境变量值 SHALL 覆盖 YAML 值

#### Scenario: CLI 参数覆盖环境变量

- **GIVEN** CLI 参数和环境变量同时设置同一配置项
- **WHEN** CLI 构造运行配置
- **THEN** CLI 参数值 SHALL 覆盖环境变量值

### Requirement: mode deny override 可配置

系统 SHALL 支持在结构化配置中为 agent mode 定义工具 deny override。

#### Scenario: deny tool 不暴露 schema

- **GIVEN** `myagent.yaml` 为某个 mode 配置了 `deny_tools`
- **WHEN** 系统以该 mode 获取工具 schema
- **THEN** 被 deny 的工具 SHALL 不出现在 schema 中

#### Scenario: deny tool 执行拒绝

- **GIVEN** 工具调用命中当前 mode 的 `deny_tools`
- **WHEN** ToolRegistry 执行该调用
- **THEN** 系统 SHALL 返回可读权限错误作为 tool result

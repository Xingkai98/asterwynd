# configuration 规格 delta

## ADDED Requirements

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

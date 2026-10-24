## ADDED Requirements

### Requirement: 群聊讨论链安全阀可配置

系统 SHALL 允许通过 `asterwynd.yaml` 的 `team:` 配置节配置群聊讨论链的安全阀：`discussion_max_rounds`（正整数，缺省 200）、`discussion_max_turns`（正整数，缺省 600）、`discussion_max_seconds`（正数，缺省 6000）。缺失配置时 SHALL 使用缺省值；非法值（非数值、非正数、布尔等）SHALL 在配置加载阶段 fail fast，抛出可读 `ConfigError` 并拒绝启动。这三个参数 SHALL 只作用于 `discussion_mode = unlimited` 的讨论链，SHALL NOT 改变 `discussion_mode = single` 模式的轮次预算（后者沿用既有 `extra_turns` / `admin_extra_turns` / `turns_each` / `admin_turns_each`）。

#### Scenario: 缺省值

- **GIVEN** 当前工作区没有 `team:` 配置节
- **WHEN** Web 入口加载配置
- **THEN** 讨论链安全阀 SHALL 为 200 轮 / 600 成员回合 / 6000 秒

#### Scenario: 覆盖值生效

- **GIVEN** `asterwynd.yaml` 设置 `team.discussion_max_rounds: 3`
- **WHEN** Web 入口加载配置
- **THEN** 讨论链的轮数安全阀 SHALL 为 3

#### Scenario: 非法值 fail fast

- **GIVEN** `asterwynd.yaml` 把 `team.discussion_max_rounds` 写成 `0` 或字符串
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 抛出可读 `ConfigError`
- **AND** SHALL NOT 以半解析状态启动 Web 服务

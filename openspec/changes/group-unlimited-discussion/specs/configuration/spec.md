## ADDED Requirements

### Requirement: 群聊讨论链安全阀可配置

系统 SHALL 允许通过 `asterwynd.yaml` 的 `team:` 配置节配置群聊讨论链的安全阀：`discussion_max_rounds`（正整数，缺省 200）、`discussion_max_turns`（正整数，缺省 600）、`discussion_max_seconds`（正数，缺省 6000）。缺失配置时 SHALL 使用缺省值；`0`、负数、非数值、以及 YAML 布尔值（`true`/`false`）SHALL 视为非法，在配置加载阶段 fail fast，抛出可读 `ConfigError` 并拒绝启动。这三个参数 SHALL 只作用于 `discussion_mode = unlimited` 的讨论链，SHALL NOT 改变 `discussion_mode = single` 模式的轮次预算（后者沿用既有 `extra_turns` / `admin_extra_turns` / `turns_each` / `admin_turns_each`）。配置在 Web 进程启动时一次性解析并注入编排器；链启动时快照，运行中修改配置文件 SHALL NOT 影响已启动的链或未重启的进程。

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

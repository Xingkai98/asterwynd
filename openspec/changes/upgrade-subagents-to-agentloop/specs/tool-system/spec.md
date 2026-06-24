## ADDED Requirements

### Requirement: 子 session 工具权限受 session mode 和父权限约束

子 session 暴露的工具 SHALL 受其 session mode 约束，且默认不得获得高于父 session 的工具权限。

#### Scenario: 父 session 为 read-only

- **GIVEN** 父 agent 以 `read_only` mode 运行
- **WHEN** 创建子 session
- **THEN** 子 session SHALL NOT 获得写入或 dangerous 工具权限

### Requirement: 子 transcript inspect 工具默认受限

父 agent 查看子 session transcript 的能力 SHALL 通过单独 inspect 接口提供，并默认限制返回范围，例如摘要或最近 `N` 条消息。

#### Scenario: 查看子 run 最近消息

- **GIVEN** 父 agent 需要检查某个子 run 最近的执行情况
- **WHEN** 调用 transcript inspect 接口且提供范围参数
- **THEN** 系统 SHALL 返回受限范围内的消息
- **AND** SHALL NOT 默认返回整份子 transcript

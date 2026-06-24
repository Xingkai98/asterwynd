## ADDED Requirements

### Requirement: 父 run 通过显式运行时接口管理子 session

父 AgentLoop SHALL 通过显式运行时接口创建、启动、查询、等待、取消和检查子 session / 子 run，而不是通过自动消息注入或伪造 tool result 把子结果并入父 messages。

#### Scenario: 父 run 查询子 run 结果

- **GIVEN** 一个已存在的子 session 和其最近一次子 run
- **WHEN** 父 agent 调用查询子 run 结果的运行时接口
- **THEN** 系统 SHALL 返回结构化结果
- **AND** SHALL NOT 直接修改父 run 的 messages transcript

### Requirement: 子 session mode 是 session 级状态

子 session SHALL 拥有独立的 session 级 mode。对子 session mode 的修改 SHALL 只影响后续 run，不影响当前已在运行的子 run。

#### Scenario: 运行中修改子 session mode

- **GIVEN** 一个子 session 当前正在以某个 mode 运行
- **WHEN** 父 agent 修改该子 session 的 mode
- **THEN** 当前子 run SHALL 继续沿用原 mode
- **AND** 后续新的子 run SHALL 使用更新后的 mode

### Requirement: 子 transcript inspect 不破坏父 tool-call 链

系统 MAY 提供查看子 transcript 摘要或最近消息的 inspect 接口，但这些接口 SHALL 以结构化结果返回，不得破坏父 AgentLoop 当前的 tool-call 消息链。

#### Scenario: 父 run 查看子 transcript 摘要

- **GIVEN** 父 agent 需要了解子 session 最近做了什么
- **WHEN** 父 agent 调用查看子 transcript 摘要接口
- **THEN** 系统 SHALL 返回结构化摘要或受限消息片段
- **AND** SHALL NOT 伪造新的 assistant/tool 历史写入父 transcript

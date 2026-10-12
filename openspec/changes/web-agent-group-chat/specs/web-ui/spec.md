## ADDED Requirements

### Requirement: 群聊视图

Web UI SHALL 提供一个群聊视图，展示某个群聊的消息流、成员列表与当前发言者；用户 SHALL 能在该视图中发送群消息，并以 `@<名称>` 点名成员。

#### Scenario: 打开群聊视图

- **GIVEN** 存在一个群聊
- **WHEN** 用户在 Web UI 打开该群聊
- **THEN** 视图 SHALL 展示该群聊的消息流与成员列表

#### Scenario: 在群聊视图中点名成员

- **GIVEN** 用户处于某群聊视图
- **WHEN** 用户输入以 `@<名称>` 开头的消息并发送
- **THEN** 系统 SHALL 将该消息作为群消息处理
- **AND** SHALL 让被点名的成员成为下一个发言者

### Requirement: 多 agent 消息按来源区分

群聊视图 SHALL 按发言人区分来自不同 agent 的消息，SHALL NOT 把不同 agent 的消息渲染为同一来源。

#### Scenario: 多个 agent 先后发言

- **GIVEN** 群聊轮次中两个不同 agent 先后发言
- **WHEN** 视图渲染这些消息
- **THEN** 两条消息 SHALL 可见地来自不同的 agent

### Requirement: 单聊视图与群聊视图共存

Web UI SHALL 同时支持人设单聊视图与群聊视图，用户在两者之间切换时 SHALL NOT 丢失任一视图的会话状态。

#### Scenario: 在单聊与群聊间切换

- **GIVEN** 用户先打开某个人设的单聊，再打开某个群聊
- **WHEN** 用户切回该人设的单聊
- **THEN** 该单聊 SHALL 保持其原有会话内容

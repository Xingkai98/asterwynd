## MODIFIED Requirements

### Requirement: Scope 隔离

长期记忆系统 SHALL 用 scope 标记记忆，SHALL 在**项目间**强制 scope 隔离，并 SHALL 在同一项目内**不同 agent 人设之间**强制 persona scope 隔离；同一人设的单聊会话与群聊会话 SHALL 共享同一 persona scope。

#### Scenario: 跨项目查询被阻止

- **GIVEN** 一条记忆标记为项目 A scope
- **WHEN** 项目 B 的查询尝试访问它
- **THEN** 访问 SHALL 被阻止
- **AND** 不发生跨项目数据泄露

#### Scenario: 跨人设查询被阻止

- **GIVEN** 同一项目下人设 A 保存了一条 persona scope 记忆
- **WHEN** 人设 B 查询记忆
- **THEN** 访问 SHALL 被阻止
- **AND** 人设 A 的记忆 SHALL NOT 出现在人设 B 的检索结果中

#### Scenario: 同一人设单聊与群聊共享记忆

- **GIVEN** 人设 P 在单聊中保存了一条 persona scope 记忆
- **WHEN** 人设 P 在群聊会话中查询记忆
- **THEN** 该记忆 SHALL 可被检索到

## MODIFIED Requirements

### Requirement: Scope 隔离

长期记忆系统 SHALL 用 scope（项目/repo，以及本 change 新增的 agent 人设 × 会话面）标记记忆，SHALL 在**项目间**强制 scope 隔离，并 SHALL 在同一项目内按 **agent 人设 × 会话面**强制 scope 隔离：不同人设之间、同一人设的单聊与各群之间、群与群之间 SHALL 互不可见。

#### Scenario: 跨项目查询被阻止

- **GIVEN** 一条记忆标记为项目 A scope
- **WHEN** 项目 B 的查询尝试访问它
- **THEN** 访问 SHALL 被阻止
- **AND** 不发生跨项目数据泄露

#### Scenario: 跨人设查询被阻止

- **GIVEN** 同一项目下人设 A 保存了一条记忆
- **WHEN** 人设 B 查询记忆
- **THEN** 访问 SHALL 被阻止
- **AND** 人设 A 的记忆 SHALL NOT 出现在人设 B 的检索结果中

#### Scenario: 同一人设的单聊与群聊互不可见

- **GIVEN** 人设 P 在其单聊中保存了一条记忆
- **WHEN** 人设 P 在某个群的会话中查询记忆
- **THEN** 该记忆 SHALL NOT 被检索到

#### Scenario: 同一人设的两个群互不可见

- **GIVEN** 人设 P 在群 A 的会话中保存了一条记忆
- **WHEN** 人设 P 在群 B 的会话中查询记忆
- **THEN** 该记忆 SHALL NOT 被检索到

## ADDED Requirements

### Requirement: 人设记忆的 review 触发与游标

人设记忆 SHALL 在对应会话的一个回合结束且该回合**实际产生了发言**时触发一次 review；`silent` / `timeout` / `failed` 出口 SHALL NOT 触发；静默成员 SHALL 在其 **review 游标**落后房间日志达到阈值（缺省 30 条）时被补齐一次 review；review SHALL 读取该 scope 自上次 review 游标之后的新增内容，SHALL 经既有 save 路径写回，SHALL 将 `remove` 映射到既有 `archive`（软删），并 SHALL 推进该 scope 的 review 游标；review 失败 SHALL NOT 中断轮次。

#### Scenario: 实际发言的回合结束后触发 review

- **GIVEN** 一个人设在某群的会话刚结束一个**实际产生发言**的回合
- **WHEN** 该回合结束
- **THEN** 系统 SHALL 为该 (人设, 群) scope 排一次记忆 review

#### Scenario: 静默回合不触发 review

- **GIVEN** 一个人设在某群的会话的一个回合以静默（`silent`）结束
- **WHEN** 该回合结束
- **THEN** 系统 SHALL NOT 为该 scope 排 review
- **AND** 该成员的记忆停滞 SHALL 由落后补齐兜底

#### Scenario: 单聊回合也触发 review

- **GIVEN** 一个人设在单聊中结束一个实际产生发言的回合
- **WHEN** 该回合结束
- **THEN** 系统 SHALL 为该人设的单聊 scope 排一次记忆 review

#### Scenario: 静默成员因 review 游标落后被补齐

- **GIVEN** 某成员在某房间的 review 游标落后房间日志达到阈值
- **WHEN** 房间发生新的发言回合
- **THEN** 系统 SHALL 为该成员的 (人设, 群) scope 排一次 review
- **AND** 该判定 SHALL 以 review 游标（而非注入用的 `seen` 游标）为基准

#### Scenario: remove 映射到既有 archive

- **GIVEN** 一次 review 决定移除一条记忆
- **WHEN** 写回该变更
- **THEN** 系统 SHALL 用既有 `archive` 软删该记忆（可 `restore`）
- **AND** SHALL NOT 引入新的记忆删除原语

#### Scenario: review 失败不中断轮次

- **GIVEN** 一次记忆 review 在执行中失败
- **WHEN** 该失败发生
- **THEN** 系统 SHALL 记录该失败
- **AND** 当前群聊轮次 SHALL NOT 被中断

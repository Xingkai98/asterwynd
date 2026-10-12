## ADDED Requirements

### Requirement: 长期 agent 人设

系统 SHALL 支持用户维护长期存在的 agent 人设；每个人设 SHALL 拥有稳定标识、显示名、角色标签、指令与模型绑定，并 SHALL 跨进程持久化。

#### Scenario: 创建人设

- **GIVEN** 用户创建一个人设并提供名称与指令
- **WHEN** 保存成功
- **THEN** 系统 SHALL 返回稳定的人设标识
- **AND** 该人设 SHALL 在进程重启后仍然存在

#### Scenario: 人设模型绑定持久化

- **GIVEN** 某个人设绑定了模型
- **WHEN** 该人设在后续会话中被再次使用时
- **THEN** 系统 SHALL 使用该人设绑定的模型

### Requirement: 单聊与群聊会话分离

每个人设 SHALL 拥有与用户的一对一会话；该人设在每个加入的群聊中 SHALL 拥有独立的群内会话；单聊内容 SHALL NOT 出现在群聊会话中，群聊内容 SHALL NOT 出现在单聊会话中。

#### Scenario: 群内发言不污染单聊

- **GIVEN** 某个人设已在某群聊中发言
- **WHEN** 用户打开该人设的单聊
- **THEN** 单聊会话 SHALL NOT 包含该群聊的内容

#### Scenario: 单聊内容不进入群聊

- **GIVEN** 用户与某个人设进行过单聊
- **WHEN** 该人设在同一群聊中发言
- **THEN** 其群内会话上下文 SHALL NOT 包含该单聊内容

### Requirement: 会话式群聊轮次编排

群聊 SHALL 由轮次编排器推进；同一时刻 SHALL 至多一个成员在发言，后发言的成员 SHALL 能看到本轮此前已发布的内容；用户消息 SHALL 默认由群管理员（Chief）应答，管理员 SHALL 能点名其他成员；用户 SHALL 能以 `@<名称>` 直接点名成员；成员没有新增内容时 SHALL 可以选择不发言（静默）。

#### Scenario: 用户以 @ 点名指定成员

- **GIVEN** 群聊中有成员 A 与成员 B
- **WHEN** 用户发送以 `@B` 开头的消息
- **THEN** B SHALL 成为本轮首先发言的成员

#### Scenario: 成员静默

- **GIVEN** 轮次轮到某个成员
- **WHEN** 该成员没有新增内容
- **THEN** 该成员 SHALL NOT 向群聊发布消息
- **AND** 轮次 SHALL 继续推进到下一个成员

#### Scenario: 发言次数上限

- **GIVEN** 一个群聊轮次正在进行
- **WHEN** 某成员的发言次数达到本轮上限
- **THEN** 系统 SHALL NOT 再为该成员追加发言

### Requirement: 人设级长期记忆

每个人设 SHALL 拥有独立的跨会话长期记忆；同一人设的单聊与群聊 SHALL 共享同一份记忆；不同人设的人设级记忆 SHALL NOT 互相检索到。

#### Scenario: 记忆按人设隔离

- **GIVEN** 人设 A 保存了一条人设级记忆
- **WHEN** 人设 B 检索其记忆
- **THEN** B SHALL NOT 检索到 A 的人设级记忆

#### Scenario: 单聊与群聊共享记忆

- **GIVEN** 人设在单聊中保存了一条人设级记忆
- **WHEN** 该人设在群聊中检索记忆
- **THEN** 该人设 SHALL 能检索到这条记忆

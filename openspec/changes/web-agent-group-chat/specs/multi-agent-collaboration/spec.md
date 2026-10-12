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

### Requirement: 房间日志

系统 SHALL 为每个群聊维护一条权威、有序的房间日志，记录用户消息与成员发言（含发言者与顺序）；群聊视图重连后 SHALL 能从房间日志还原有序群消息流。

#### Scenario: 重连还原有序时间线

- **GIVEN** 一次群聊轮次中多个成员先后发言
- **WHEN** 用户重连该群聊
- **THEN** 群消息 SHALL 按发言顺序还原

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

#### Scenario: @ 点名边界

- **GIVEN** 群聊成员为 A 与 B
- **WHEN** 某成员发言中点到不在成员列表中的名字、点到自己、或点到多个成员
- **THEN** 系统 SHALL 只把「属于本群成员且非自己」的被点名者排入后续发言
- **AND** 系统 SHALL NOT 因无效点名报错

### Requirement: 群聊轮次终止

一轮群聊 SHALL 在所有发言位走完或达到本轮上限时结束；用户再次发言 SHALL 开启新一轮；达到上限而结束的轮次 SHALL 在房间日志中记录其原因。

#### Scenario: 达到上限而结束

- **GIVEN** 一轮群聊达到本轮上限
- **WHEN** 编排器停止该轮
- **THEN** 房间日志 SHALL 记录一条「因达上限结束」
- **AND** 系统 SHALL NOT 在用户再次发言前自行开启新一轮

### Requirement: 跨人设共享面声明

系统 SHALL 显式声明哪些存储是跨人设共享的，SHALL NOT 默认假设所有存储都按人设隔离；workflow 资产库 SHALL 被声明为跨人设共享面。

#### Scenario: 资产库为共享面

- **GIVEN** 人设 A 保存了一个 workflow 资产
- **WHEN** 人设 B 的上下文注入资产索引
- **THEN** 该行为 SHALL 符合「资产库是跨人设共享面」的声明
- **AND** 该行为 SHALL NOT 被判定为人设隔离缺陷

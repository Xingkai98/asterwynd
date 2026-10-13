## MODIFIED Requirements

### Requirement: Orchestration Reuses Workflow Persistence Discipline

Subagent orchestration SHALL reuse the `agent/workflow/` persistence discipline (JSON serialization + schema_version + transition log style), SHALL NOT couple to the dev-workflow phase vocabulary, and SHALL NOT introduce a separate control plane. 本 Requirement 的主语是 **Subagent orchestration**：它 SHALL NOT 覆盖非 subagent 的交互式编排（例如本 change 新增的群聊轮次编排器——后者不复用 `SubAgentManager`，不属本 Requirement 的约束范畴）。

#### Scenario: orchestration state persists without dev-workflow coupling

- Given an orchestration pattern run
- When pattern state is persisted
- Then it follows the workflow JSON/transition-log discipline
- And it does not depend on dev-workflow phases

#### Scenario: 非 subagent 编排不受本 Requirement 约束

- **GIVEN** 一个不基于 `SubAgentManager` 的交互式编排（群聊轮次编排器）
- **WHEN** 它维护自己的房间日志与轮次状态
- **THEN** 该行为 SHALL NOT 被判定为「引入独立控制面」的违规

## ADDED Requirements

### Requirement: 长期 agent 人设与两级主持角色

系统 SHALL 支持用户维护长期存在的 agent 人设；每个人设 SHALL 拥有稳定标识、显示名、角色标签、指令与模型绑定，并 SHALL 跨进程持久化。主持角色 SHALL 分两级：**roster 级 `mainBotIds`（可多个，即 Chief）** 负责管理全部人设与房间，**房间级 `admin`（单个、可为空）** 决定该房间「用户消息默认由谁应答」。

#### Scenario: 创建人设

- **GIVEN** 用户创建一个人设并提供名称与指令
- **WHEN** 保存成功
- **THEN** 系统 SHALL 返回稳定的人设标识
- **AND** 该人设 SHALL 在进程重启后仍然存在

#### Scenario: 默认应答者取房间 admin，回落 Chief

- **GIVEN** 一个房间设定了 admin 人设
- **WHEN** 用户发送一条不含 `@` 的群消息
- **THEN** 该房间 admin SHALL 成为首先应答者
- **AND** 若该房间无 admin，则 roster 中第一个 `mainBot` SHALL 成为首先应答者

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

系统 SHALL 为每个群聊维护一条权威、有序的房间日志。每个条目 SHALL 含顺序号、发言者、类型、文本与时间戳；类型枚举 SHALL 为 `user`（用户消息）/ `post`（成员发言）/ `system`（系统条目，如轮次因达上限结束、成员运行失败），其中 `system` 条目的发言者 SHALL 为 `null`；群聊视图重连后 SHALL 能从房间日志还原有序群消息流。

#### Scenario: 重连还原有序时间线

- **GIVEN** 一次群聊轮次中多个成员先后发言
- **WHEN** 用户重连该群聊
- **THEN** 群消息 SHALL 按发言顺序还原

#### Scenario: 房间日志条目含发言者与顺序

- **GIVEN** 房间日志中先后有用户消息与两个成员的发言
- **WHEN** 读取房间日志
- **THEN** 每个条目 SHALL 带可区分的发言者与递增顺序号

### Requirement: 会话式群聊轮次编排

群聊 SHALL 由轮次编排器按明确的发言位（slot）序列推进；同一时刻 SHALL 至多一个成员在发言；每个成员 SHALL 只看到其**持久化游标之后**的新增内容（含本轮与往轮分层），且切片 SHALL 有界。在 `reply_mode = admin`（缺省）下，无 `@` 的用户消息 SHALL 默认由房间 admin（无则 roster 首个 mainBot）应答；在 `reply_mode = everyone` 下，无 `@` 的用户消息 SHALL 由全体成员按序各得一次发言机会（见「房间应答模式」）；用户消息**行首**的 `@<名称>` SHALL 指定首先发言者；成员发言**句中**的 `@<名称>` SHALL 把该成员追加到当前位次之后（去重、非本群成员或自己忽略且不报错）；成员没有新增内容时 SHALL 可以静默。

#### Scenario: 用户以 @ 点名指定成员

- **GIVEN** 群聊中有成员 A 与成员 B
- **WHEN** 用户发送以 `@B` 开头的消息
- **THEN** B SHALL 成为本轮首先发言的成员

#### Scenario: 成员静默

- **GIVEN** 轮次轮到某个成员
- **WHEN** 该成员没有新增内容
- **THEN** 该成员 SHALL NOT 向群聊发布消息
- **AND** 轮次 SHALL 继续推进到下一个成员

#### Scenario: 静默成员的切片游标仍推进

- **GIVEN** 某成员连续多轮静默
- **WHEN** 该成员再次被轮到
- **THEN** 它看到的 SHALL 仅为其上次回合之后的新增内容
- **AND** SHALL NOT 重复注入此前已注入过的内容

#### Scenario: @ 点名边界

- **GIVEN** 群聊成员为 A 与 B
- **WHEN** 某成员发言中点到不在成员列表中的名字、点到自己、或点到多个成员
- **THEN** 系统 SHALL 只把「属于本群成员且非自己」的被点名者排入后续发言
- **AND** 系统 SHALL NOT 因无效点名报错

#### Scenario: 发言次数上限

- **GIVEN** 一个群聊轮次正在进行
- **WHEN** 某成员的发言次数达到本轮上限
- **THEN** 系统 SHALL NOT 再为该成员追加发言

### Requirement: 房间级互斥与轮次终止

同一房间同一时刻 SHALL 至多存在一个进行中的轮次；用户在同一轮进行中发送的消息 SHALL 排队进入该轮（只追加进房间日志，其行首 `@` 追加为当前位次之后的发言位，且 SHALL NOT 改变本轮上限基数），SHALL NOT 并行开启第二轮。一轮 SHALL 在**三个出口**之一结束：所有发言位走完 / 达到本轮上限 / 所有剩余成员运行失败或超时；达到上限而结束的轮次 SHALL 在房间日志记录一条 `system` 条目（原因「因达上限结束」）；系统 SHALL NOT 在用户再次发言前自行开启新一轮。（首版不提供轮次取消出口。）

#### Scenario: 达到上限而结束

- **GIVEN** 一轮群聊达到本轮上限
- **WHEN** 编排器停止该轮
- **THEN** 房间日志 SHALL 记录一条 `system` 条目（原因「因达上限结束」）
- **AND** 系统 SHALL NOT 在用户再次发言前自行开启新一轮

#### Scenario: 成员运行失败不挂死整轮

- **GIVEN** 本轮某成员的运行失败或超时
- **WHEN** 编排器处理该成员的出口
- **THEN** 该失败 SHALL 以 `system` 条目记入房间日志
- **AND** 轮次 SHALL 继续推进，SHALL NOT 永久阻塞

#### Scenario: 并发消息进入同一轮

- **GIVEN** 一个房间已有一轮在进行中
- **WHEN** 用户再发一条消息
- **THEN** 该消息 SHALL 排队进入当前轮（追加进房间日志）
- **AND** 其行首 `@` SHALL 追加为当前位次之后的发言位
- **AND** 系统 SHALL NOT 并行开启第二个轮次

### Requirement: 跨人设共享面声明

系统 SHALL 显式声明哪些存储是跨人设共享的，SHALL NOT 默认假设所有存储都按人设隔离；workflow 资产库 SHALL 被声明为跨人设共享面。

#### Scenario: 资产库为共享面

- **GIVEN** 人设 A 保存了一个 workflow 资产
- **WHEN** 人设 B 的上下文注入资产索引
- **THEN** 该行为 SHALL 符合「资产库是跨人设共享面」的声明
- **AND** 该行为 SHALL NOT 被判定为人设隔离缺陷

### Requirement: 会话数上限与排队

系统 SHALL 对（人设 + 群）会话的数量施加可配置上限（默认 **50**）；达到上限时新建会话 SHALL **排队**等待执行槽释放，SHALL NOT 拒绝创建；会话 SHALL 懒构造（被首次使用时才建立其 AgentLoop）。

#### Scenario: 达到上限排队而非拒绝

- **GIVEN** 会话数已达配置上限
- **WHEN** 用户创建一个会新增人设/群会话的操作
- **THEN** 该新建 SHALL 排队等待，SHALL NOT 被拒绝
- **AND** 当有执行槽释放时 SHALL 按顺序建立

#### Scenario: 会话懒构造

- **GIVEN** 一个已定义但尚未被使用的会话面
- **WHEN** 尚未有人在其中运行
- **THEN** 其 AgentLoop SHALL NOT 被构造

### Requirement: 群共享 notice

房间 SHALL 支持一条群级共享指令（notice）；该指令 SHALL 在该房间每个成员发言前注入其群内会话，且 SHALL NOT 注入该成员的单聊会话。

#### Scenario: notice 注入群内会话

- **GIVEN** 某房间设置了 notice
- **WHEN** 该房间某成员发言
- **THEN** 其群内会话上下文 SHALL 包含该 notice

#### Scenario: notice 不影响单聊

- **GIVEN** 某房间设置了 notice
- **WHEN** 该房间某成员与其单聊会话交互
- **THEN** 该单聊会话上下文 SHALL NOT 包含该 notice

### Requirement: 人设运行模式

每个 agent 人设 SHALL 拥有可配置的运行模式（`build` / `read_only` / `plan` / `bypass`），缺省 SHALL 为 `bypass`；该人设的单聊会话与它在所有群里的群内会话 SHALL 以该模式运行。

#### Scenario: 人设按其模式构造会话

- **GIVEN** 一个人设的运行模式设为 `bypass`
- **WHEN** 为该人设构造单聊或群内会话
- **THEN** 该会话 SHALL 以 `bypass` 模式运行
- **AND** 其高风险工具调用 SHALL NOT 因需审批而被阻塞

#### Scenario: 模式变更持久化

- **GIVEN** 用户把某个人设的模式从 `build` 改为 `read_only`
- **WHEN** 保存成功
- **THEN** 该人设此后构造的会话 SHALL 使用 `read_only`

### Requirement: 房间应答模式

每个房间 SHALL 拥有应答模式 `reply_mode`，取值 `admin`（缺省）/ `everyone`。`admin` 模式下，无 `@` 的普通消息 SHALL 由房间 admin 应答（无 admin 则 roster 首个 `mainBot`）；`everyone` 模式下，无 `@` 的普通消息 SHALL 让全体成员按序各得一次发言机会（admin 先），每名成员自行决定发言或静默。两种模式均 SHALL 受每轮每成员发言上限约束。

#### Scenario: admin 模式仅管理员应答

- **GIVEN** 一个 `reply_mode = admin` 的房间，用户发送不含 `@` 的普通消息
- **THEN** 只有房间 admin SHALL 成为本轮初始发言者

#### Scenario: everyone 模式全员各得一次机会

- **GIVEN** 一个 `reply_mode = everyone` 的房间有 3 名成员，用户发送不含 `@` 的普通消息
- **THEN** 三名成员 SHALL 按序各得一次发言机会（admin 先）
- **AND** 没有新增内容的成员 SHALL 可以静默

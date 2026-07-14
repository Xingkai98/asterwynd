## ADDED Requirements

### Requirement: Managed Workspace Root 激活门禁

系统 SHALL 通过显式 Managed Workspace Root 路径列表决定是否启用 Workflow Control Plane。路径判定 SHALL 在模型调用和 workflow prompt 注入前由 host adapter 本地完成。未命中的 session SHALL 进入 Workflow Bypass，不创建或查询 workflow。

#### Scenario: 当前路径命中受管根目录

- **GIVEN** `/projects/asterwynd` 已加入 managed roots
- **WHEN** session cwd 位于 `/projects/asterwynd` 或其子目录
- **THEN** host adapter SHALL 启用 workflow preflight

#### Scenario: 当前路径属于受管项目 Worktree

- **GIVEN** canonical repository 已加入 managed roots
- **AND** session cwd 位于该 repository 的 sibling worktree
- **WHEN** host adapter 解析 Git common dir
- **THEN** SHALL 将该 session 识别为受管项目

#### Scenario: 当前路径未命中

- **GIVEN** session cwd 不属于任何 managed root 或其 worktree
- **WHEN** host adapter 执行 preflight
- **THEN** SHALL 进入 Workflow Bypass
- **AND** SHALL NOT 查询 workflow database
- **AND** SHALL NOT 注入 workflow 指令或调用模型进行分类

#### Scenario: Session 缓存旁路结果

- **GIVEN** session 已确认处于 Workflow Bypass
- **WHEN** 后续 run 执行或进程 cwd 发生变化
- **THEN** 当前 session SHALL 继续复用旁路结果
- **AND** SHALL NOT 静默启用 workflow

#### Scenario: 显式进入受管项目

- **GIVEN** 当前 session 处于 Workflow Bypass
- **WHEN** 用户显式执行 `workflow attach <managed-root>`
- **THEN** 系统 SHALL 验证目标属于 managed roots
- **AND** SHALL 建立新的受管 session binding 或要求启动新 session
- **AND** SHALL NOT 改写原旁路 session 的历史语义

#### Scenario: 管理路径列表

- **WHEN** 用户执行 manage add、remove 或 list 操作
- **THEN** 系统 SHALL 更新或展示 canonical managed roots
- **AND** agent capability SHALL NOT 隐式扩大 managed roots

### Requirement: 独立 Workflow Control Plane

系统 SHALL 提供独立于任何具体 coding agent 的 Workflow Control Plane，统一管理从探索性对话、需求确认、设计、开发、代码审查到合入完成的生命周期。控制面核心 SHALL NOT 依赖 Asterwynd AgentLoop；具体 agent 和人工执行者 SHALL 通过稳定的 executor/client 协议接入。

#### Scenario: 使用不同 executor 处理同一 workflow

- **GIVEN** 一个 workflow 的设计阶段由 Codex 执行
- **WHEN** 后续 building 阶段配置为 Asterwynd executor
- **THEN** 两个 executor SHALL 读取同一控制面状态和 artifact 引用
- **AND** phase 迁移语义 SHALL 不依赖任一 executor 的内部 session 格式

#### Scenario: 控制面不加载 AgentLoop

- **WHEN** 仅运行 workflow CLI 查询状态或批准 gate
- **THEN** 系统 SHALL NOT 要求初始化 Asterwynd AgentLoop 或 LLM provider

### Requirement: V1 提供强入口与 Prompt Adapter 降级入口

V1 SHALL 同时提供 `workflow chat --executor <adapter>` CLI Host Wrapper 和 `skill + AGENTS.md` Prompt Adapter。Host Wrapper SHALL 在调用 executor 前完成路径门禁、workflow 恢复、WorkItem 生成和用户消息 approval 检查，并可声明可信 gate enforcement。Prompt Adapter SHALL 通过宿主客户端已有 skill/prompt 机制调用 `workflow enter/report/status`，不得声明拥有可信 gate 或进程级写权限强制。

#### Scenario: 通过 Wrapper 启动 Codex

- **WHEN** 用户运行 `workflow chat --executor codex`
- **THEN** Wrapper SHALL 先执行 managed-root 和 workflow preflight
- **AND** SHALL 仅向 Codex executor 暴露受限 WorkItem/report 接口
- **AND** SHALL 标记 enforcement level 为 `strict_host`

#### Scenario: 通过 Happy Coder 使用 Prompt Adapter

- **WHEN** 用户在 Happy Coder 中打开受管项目 session
- **THEN** workflow skill 或 `AGENTS.md` 接入说明 SHALL 要求 agent 在回复前调用 `workflow enter`
- **AND** SHALL 要求 agent 结束时通过 `workflow report` 提交结构化结果
- **AND** SHALL 标记 enforcement level 为 `prompt_adapter`
- **AND** SHALL NOT 要求修改 Happy Coder server、daemon、app 或消息链

#### Scenario: 直接启动原生 Agent CLI

- **WHEN** 用户绕过 Wrapper 直接启动原生 agent CLI
- **THEN** 系统 SHALL NOT 将该 session 标记为具有可信 gate enforcement
- **AND** AGENTS 接入说明 SHALL 提示如需强约束受管开发应使用 Host Wrapper
- **AND** SHALL 允许该 unmanaged session 继续处理其他工作
- **AND** 控制面 SHALL NOT 接受该 session 自报的 human approval

#### Scenario: Unmanaged Session 位于主仓库

- **GIVEN** 用户直接启动原生 agent
- **AND** cwd 为 canonical main repository 或非 workflow 专属 worktree
- **WHEN** agent 执行其他临时工作
- **THEN** 控制面 SHALL 允许 unmanaged 行为
- **AND** SHALL NOT 将其记录为受管 workflow 进度

#### Scenario: Unmanaged Session 位于专属 Worktree

- **GIVEN** cwd 为 active workflow 的专属 worktree
- **AND** session 不持有匹配 workflow binding
- **WHEN** agent 尝试写入
- **THEN** 支持 enforcement 的 adapter SHALL 拒绝写入
- **AND** 不支持进程级 enforcement 的 adapter SHALL 标记 audit-only 并显示风险提示
- **AND** 该 session SHALL NOT 产生合法 workflow transition 或 approval

#### Scenario: Prompt Adapter 位于 Gate

- **GIVEN** Prompt Adapter session 调用 `workflow enter`
- **AND** workflow 处于 `design.ready_for_review`
- **WHEN** agent 准备继续执行
- **THEN** WorkItem SHALL 要求 agent 停止并展示 gate 状态
- **AND** SHALL 提示用户通过可信 CLI/client 批准或要求修改
- **AND** 默认可信批准命令 SHALL 为用户直接运行的 `workflow gate approve --workflow <id>`
- **AND** agent SHALL NOT 把聊天消息 `ok` 或等价自然语言转换为 approval event

### Requirement: 端到端生命周期

控制面 SHALL 支持 `exploring`、`requirements`、`design`、`building`、`code-review`、`closing`、`blocked` 和 `done` phase。除 `exploring`、`blocked` 和 `done` 外，每个可审阅 phase SHALL 具有 `ready_for_review` gate。

#### Scenario: 正常端到端流转

- **GIVEN** 用户从探索性对话形成一个需求事项
- **WHEN** requirements、design、building、code-review 和 closing 依次完成并通过所需 gate
- **THEN** workflow SHALL 到达 `done`
- **AND** 每次 phase 变化 SHALL 存在可重放事件和对应证据

#### Scenario: 闲聊不自动创建 worktree

- **GIVEN** workflow 处于 `exploring` 或 `requirements`
- **WHEN** 用户与 agent 继续讨论目标和边界
- **THEN** 系统 SHALL 使用 canonical main workspace
- **AND** SHALL NOT 因普通对话自动创建 branch 或 worktree

#### Scenario: Agent 自动申请进入 Requirements

- **GIVEN** workflow 处于 exploring
- **AND** 对话已形成可记录的 goal candidate 或问题定义
- **WHEN** agent report 提交 start_requirements proposal 和最低证据
- **THEN** Orchestrator MAY 自动进入 requirements 起始状态
- **AND** SHALL NOT 创建 branch 或 worktree
- **AND** SHALL NOT 将该转换视为需求已获人工批准

### Requirement: 受管 Session 自动创建 Exploration Workflow

在 Managed Workspace Root 中启动的新 session，如果没有显式恢复目标和可唯一恢复的 active workflow，系统 SHALL 自动创建轻量 Exploration Workflow。该 workflow SHALL 不创建 branch、worktree 或 OpenSpec change。

#### Scenario: 新受管 Session

- **GIVEN** session 位于 Managed Workspace Root
- **AND** 没有指定恢复 workflow
- **AND** 不存在可唯一自动恢复的 active workflow
- **WHEN** host adapter 完成 preflight
- **THEN** 系统 SHALL 创建并绑定 Exploration Workflow
- **AND** 初始 phase SHALL 为 exploring

#### Scenario: 存在唯一恢复目标

- **GIVEN** 项目存在一个与当前 session binding 规则匹配的 active workflow
- **WHEN** 新 session 调用 enter
- **THEN** 系统 SHALL 恢复该 workflow
- **AND** SHALL NOT 创建重复 exploration

### Requirement: Empty Exploration Aging

系统 SHALL 支持为每个 Managed Workspace Root 配置 exploration aging TTL，默认值 SHALL 为 24 小时。只有仍处于 exploring、没有 durable Workflow Output 且超过 TTL 的 workflow SHALL 自动 abandon。Draft 或 proposed output 不属于 durable output，不能阻止 empty-exploration aging。

#### Scenario: Lazy Aging Scan

- **GIVEN** V1 未运行常驻 daemon
- **WHEN** 用户执行 workflow chat、status、enter 或 manage
- **THEN** 控制面 SHALL 在主操作前扫描到期的 empty explorations
- **AND** SHALL 对符合条件的 workflow 追加幂等 abandon event

#### Scenario: 无调用时不准点执行

- **GIVEN** exploration 已超过 TTL
- **AND** 没有任何控制面命令运行
- **WHEN** 墙钟时间继续经过
- **THEN** 系统 MAY 保持原存储状态直到下一次 lazy aging scan

#### Scenario: 空 Exploration 老化

- **GIVEN** exploration 没有 durable Workflow Output
- **AND** phase 未进入 requirements
- **AND** 最后活动时间超过配置 TTL
- **WHEN** aging job 或下一次状态扫描执行
- **THEN** 系统 SHALL 追加 workflow_abandoned 事件
- **AND** SHALL 从 active workflow 列表移除该 exploration

#### Scenario: Exploration 已产生结构化产出

- **GIVEN** exploration 已记录 durable Workflow Output
- **WHEN** empty-exploration TTL 到期
- **THEN** 系统 SHALL NOT 因 empty-exploration aging 自动 abandon

#### Scenario: Draft Output 不阻止老化

- **GIVEN** exploration 只有 agent 生成的 draft 或 proposed output
- **AND** 尚未获得 Human Acceptance
- **WHEN** empty-exploration TTL 到期
- **THEN** 系统 SHALL 仍可自动 abandon

#### Scenario: Requirements Gate 接受 Output

- **GIVEN** requirements snapshot 引用了 proposed outputs
- **WHEN** 用户使用有效 Gate Approval Token 批准 snapshot
- **THEN** 控制面 SHALL 将被引用 outputs 标记为 durable

#### Scenario: Retain Mini-Gate

- **GIVEN** 用户要求保留 exploration 中的 proposed output
- **WHEN** host 展示 retain mini-gate 且用户输入严格原文 `ok`
- **THEN** 控制面 SHALL 记录 workflow_output_accepted
- **AND** output SHALL 变为 durable

#### Scenario: Agent 自报 Durable

- **WHEN** agent report 声明 output durability 为 durable
- **THEN** 控制面 SHALL 拒绝或降级为 proposed
- **AND** SHALL NOT 视为 Human Acceptance

#### Scenario: Workflow 已进入 Requirements

- **GIVEN** workflow phase 已进入 requirements
- **WHEN** exploration TTL 到期
- **THEN** 系统 SHALL NOT 应用 empty-exploration aging policy

#### Scenario: 普通消息不算产出

- **GIVEN** exploration 包含多轮聊天消息
- **AND** 未通过结构化 report 记录 Workflow Output
- **WHEN** 系统判断 aging 条件
- **THEN** 普通消息 SHALL NOT 阻止自动 abandon

### Requirement: 每轮 Agent Run 获取 WorkItem

每个受管理的 agent run 开始前 SHALL 调用控制面 `enter` 操作。控制面 SHALL 返回带状态版本的 `WorkItem`，包含 workflow、phase、sub-state、workspace、branch、允许操作、所需证据、gate 状态和下一步。

#### Scenario: 新 session 恢复当前进度

- **GIVEN** workflow 已在另一个 session 中进入 `design.researching_references`
- **WHEN** 新 agent session 从主仓库调用 `enter`
- **THEN** 控制面 SHALL 返回该 workflow 的当前 phase 和 sub-state
- **AND** SHALL 返回绑定 worktree 的绝对路径
- **AND** agent SHALL 不需要读取旧聊天记录推断进度

#### Scenario: Gate 状态进入

- **GIVEN** workflow 处于 `design.ready_for_review`
- **WHEN** agent 调用 `enter`
- **THEN** WorkItem SHALL 标记 `gate: waiting_for_human`
- **AND** SHALL NOT 分配可写执行任务

#### Scenario: 单一 User Session 贯穿多个 Phase

- **GIVEN** 用户在同一聊天 Session 中完成 requirements gate approval
- **WHEN** workflow 进入 design
- **THEN** host SHALL 在原 User Session 中继续自然语言交互
- **AND** MAY 创建新的 Run ID 和 WorkItem
- **AND** SHALL NOT 要求用户创建新聊天窗口

#### Scenario: 后台更换 Executor

- **GIVEN** 模板为某 phase 配置 fresh executor
- **WHEN** host 调度该 phase
- **THEN** executor 结果 SHALL 回传到原 User Session
- **AND** 用户 SHALL 不需要手工复制上下文或切换 Session

#### Scenario: Prompt Adapter Session 固定绑定 Workflow

- **GIVEN** Prompt Adapter User Session 已绑定 workflow A
- **WHEN** 该 Session 继续产生用户 turn
- **THEN** 所有受管 WorkItem 和 Gate Approval Token SHALL 仅关联 workflow A
- **AND** SHALL NOT 在该 Session 中切换到 workflow B

#### Scenario: Workflow 跨 Session 恢复

- **GIVEN** workflow A 在 Prompt Adapter Session 1 中推进后 Session 关闭
- **WHEN** Prompt Adapter Session 2 根据恢复规则选择 workflow A
- **THEN** SHALL 从控制面当前 version 恢复
- **AND** SHALL NOT 要求复制 Session 1 的聊天历史

#### Scenario: Done 后开始新事项

- **GIVEN** 当前 Session 绑定的 workflow 已 done
- **WHEN** 用户希望开始新的受管开发事项
- **THEN** 系统 SHALL 要求创建新的 User Session
- **AND** 原 Session MAY 继续查看或总结已完成 workflow

#### Scenario: Code Review 使用 Fresh Executor

- **GIVEN** workflow 从 building gate 进入 code-review
- **WHEN** 默认模板调度 reviewer
- **THEN** SHALL 使用 fresh executor run
- **AND** reviewer SHALL 接收 design、diff、tests、evidence 和必要 workflow context
- **AND** SHALL NOT 依赖实现 executor 的隐藏推理上下文
- **AND** review 结果 SHALL 回传原 User Session

#### Scenario: Review 要求修改

- **GIVEN** fresh reviewer 提交 changes requested
- **WHEN** Orchestrator 接受 review result
- **THEN** workflow SHALL 返回 building 的模板指定状态
- **AND** 修改 WorkItem SHALL 交回原 executor
- **AND** SHALL 继续使用原绑定 worktree

#### Scenario: Human Gate 前执行 Automated Review Lane

- **GIVEN** phase template 为 `design` 配置了 `automated_reviewers`
- **AND** design artifact 与机械检查已完成
- **WHEN** workflow 准备进入 `design.ready_for_review`
- **THEN** Orchestrator SHALL 先按配置生成 automated review WorkItem
- **AND** reviewer MAY 是 subagent、fresh Codex CLI、Claude Code runner、Asterwynd runner、inline checker 或命令 runner
- **AND** reviewer SHALL 只获得 artifact、diff、tests、evidence、workflow state 和必要项目约束
- **AND** reviewer SHALL NOT 继承执行 agent 的隐藏推理上下文

#### Scenario: Prompt Adapter 派发 Automated Review

- **GIVEN** 当前 session 通过 Prompt Adapter 接入
- **AND** Orchestrator 返回 automated review WorkItem
- **WHEN** agent 按 WorkItem 启动 fresh Codex CLI reviewer 或 subagent reviewer
- **THEN** reviewer result SHALL 通过 `workflow report` 上报
- **AND** 该 result SHALL 只能作为自动质量门证据
- **AND** SHALL NOT 产生 human gate approval

#### Scenario: Automated Review 不等于 Human Approval

- **GIVEN** automated reviewer 返回 `pass`
- **WHEN** Orchestrator 接受 review result
- **THEN** workflow MAY 进入 `ready_for_review`
- **AND** SHALL 继续等待可信 human gate approval
- **AND** reviewer SHALL NOT 产生 gate_approved 事件

#### Scenario: Automated Review 要求修改

- **GIVEN** automated reviewer 返回 `changes_requested`
- **WHEN** Orchestrator 接受 review result
- **THEN** workflow SHALL 返回模板定义的修复 sub-state
- **AND** SHALL NOT 进入 human `ready_for_review`
- **AND** findings SHALL 作为 evidence 回传原 User Session

### Requirement: Agent 通过 WorkResult 报告而非指定状态

Agent SHALL 通过 `report` 提交 `WorkResult`、artifact 引用、证据和 blocker。Agent SHALL NOT 直接指定任意目标 phase/sub-state；Orchestrator SHALL 根据当前状态、模板和证据决定合法结果。

#### Scenario: 合法完成当前任务

- **GIVEN** agent 持有匹配当前版本和 lease 的 WorkItem
- **WHEN** agent 报告当前 sub-state 已完成并提供全部必需证据
- **THEN** Orchestrator SHALL 接受 report
- **AND** SHALL 根据模板推进到唯一合法下一状态或 gate

#### Scenario: Agent 请求跳过多个状态

- **GIVEN** 当前状态为 `design.researching_references`
- **WHEN** agent report 声称应直接进入 `building.implementing`
- **THEN** Orchestrator SHALL 拒绝非法跳转
- **AND** 当前 workflow version 和状态 SHALL 保持不变

#### Scenario: 使用过期 WorkItem

- **GIVEN** workflow 已从 version 12 推进到 version 13
- **WHEN** agent 使用 version 12 的 WorkItem 提交 report
- **THEN** 系统 SHALL 返回 stale state 错误
- **AND** agent SHALL 重新调用 `enter`

### Requirement: Append-only Workflow Events

Workflow event log SHALL 是实时状态的权威来源。每个事件 SHALL 具有 workflow id、单调 version、event type、actor kind、actor id、session/correlation id、时间戳和 payload。Snapshot SHALL 由事件派生，并可通过重放验证。

#### Scenario: 从事件恢复 snapshot

- **GIVEN** 数据库中存在完整 workflow event sequence
- **WHEN** snapshot 缺失或被标记为需要重建
- **THEN** 系统 SHALL 按 version 顺序重放事件
- **AND** 生成与合法历史一致的当前状态

#### Scenario: Snapshot 与事件不一致

- **GIVEN** snapshot 显示 `building`，事件重放结果为 `design.ready_for_review`
- **WHEN** 系统执行一致性校验
- **THEN** 校验 SHALL 失败
- **AND** SHALL NOT 以 snapshot 覆盖事件历史

### Requirement: 可信 Human Gate

Gate approval SHALL 由可信用户客户端产生，并绑定 workflow id、gate id、phase、state version、decision 和 user identity。Agent capability SHALL NOT 包含批准 gate 的权限。

#### Scenario: V1 Host Wrapper 持有 Approval Capability

- **GIVEN** 用户通过受管 Host Wrapper 与 agent 交互
- **WHEN** host 启动 agent executor
- **THEN** event store 和 approval service SHALL 保留在 host 进程边界
- **AND** agent SHALL 只获得 enter、report 和 status 能力
- **AND** agent 环境 SHALL NOT 暴露 approval capability 或 approval secret

#### Scenario: 用户批准当前 Gate

- **GIVEN** workflow 处于 `requirements.ready_for_review` version 8
- **WHEN** 可信用户客户端批准 gate version 8
- **THEN** 系统 SHALL 记录 `gate_approved` 事件
- **AND** SHALL 执行进入 design 前的 worktree promotion

#### Scenario: Agent 伪造人工身份

- **GIVEN** agent 仅持有 enter/report capability
- **WHEN** agent 尝试提交 `approved_by: human` 或调用 approval API
- **THEN** 系统 SHALL 拒绝请求
- **AND** SHALL NOT 产生 gate approval 事件

#### Scenario: 过期批准

- **GIVEN** gate version 8 在用户操作前已变为 version 9
- **WHEN** 用户客户端提交绑定 version 8 的批准
- **THEN** 系统 SHALL 拒绝 stale approval

#### Scenario: Session 内自然语言批准

- **GIVEN** 当前 session 正在展示唯一的 pending gate
- **AND** 当前 session 由 Host Wrapper 或其他可信用户客户端管理
- **AND** Gate Approval Token 白名单包含 `ok`
- **WHEN** 用户发送完整消息 `ok`
- **THEN** host adapter SHALL 在消息进入 agent 前执行精确匹配
- **AND** SHALL 将 decision 绑定当前 gate id、state version 和原始 user message
- **AND** 控制面 SHALL 记录可信 gate_approved 事件
- **AND** host SHALL 消费该消息而不发送给 agent
- **AND** SHALL 在同一用户 turn 重新 enter 并自动调度下一阶段 WorkItem，默认复用当前 User Session

#### Scenario: Prompt Adapter 不消费 Approval Token

- **GIVEN** 当前 session 通过 Prompt Adapter 接入
- **AND** workflow 处于 pending gate
- **WHEN** 用户在宿主聊天中发送完整消息 `ok`
- **THEN** agent SHALL NOT 调用 approval capability
- **AND** 控制面 SHALL NOT 产生 gate_approved 事件
- **AND** agent SHALL 提示用户使用 `workflow gate approve --workflow <id>` 完成批准

#### Scenario: 批准后的自动推进失败

- **GIVEN** 用户输入精确 approval token
- **WHEN** phase transition、worktree promotion 或下一阶段 preflight 失败
- **THEN** 系统 SHALL NOT 启动下一阶段 agent
- **AND** workflow SHALL 进入 blocked 或保持可恢复状态
- **AND** 用户 SHALL 收到明确失败原因

#### Scenario: 不做模糊匹配

- **GIVEN** Gate Approval Token 白名单仅包含 `ok`
- **WHEN** 用户发送 `可以`、`继续`、`ok，继续` 或其他非精确消息
- **THEN** host adapter SHALL NOT 批准 gate
- **AND** workflow SHALL 保持 waiting_for_human

#### Scenario: Approval Token 不做文本归一化

- **GIVEN** Gate Approval Token 白名单仅包含 ASCII 原文 `ok`
- **WHEN** 用户发送 `OK`、`Ok`、` ok`、`ok `、带换行的 `ok` 或 Unicode 变体
- **THEN** host adapter SHALL NOT 执行 trim、lowercase 或 Unicode normalization
- **AND** SHALL NOT 批准 gate

#### Scenario: 未匹配消息作为反馈

- **GIVEN** workflow 处于 design gate
- **WHEN** 用户发送非白名单消息并提出修改要求
- **THEN** host adapter SHALL 保持 gate
- **AND** MAY 将消息交给 agent 作为审阅反馈
- **AND** agent SHALL NOT 将反馈升级为 approval

#### Scenario: Agent 转述用户批准

- **WHEN** agent 输出“用户已经同意，可以继续”
- **THEN** 该 assistant 消息 SHALL NOT 产生 approval event

#### Scenario: 配置 Approval Token 白名单

- **WHEN** 用户通过可信配置入口修改 Gate Approval Token 白名单
- **THEN** host adapter SHALL 使用更新后的完整字符串集合进行精确匹配
- **AND** agent capability SHALL NOT 修改该白名单

#### Scenario: 自然语言决定绑定错误版本

- **GIVEN** 用户消息针对已展示的 gate version 8
- **AND** 当前 workflow 已变为 version 9
- **WHEN** host adapter 尝试提交决定
- **THEN** 控制面 SHALL 拒绝该决定并重新展示当前 gate

### Requirement: Requirements Gate 创建专属 Worktree

Workflow 在 requirements gate 批准前 SHALL 不要求专属 worktree。requirements gate 批准后，控制面 SHALL 在进入 design 前原子创建 change branch 和专属 worktree，并将已批准需求 materialize 为 change artifacts。

#### Scenario: Gate 展示 Change ID

- **GIVEN** agent 已根据 requirements 提议合法 kebab-case change id
- **WHEN** requirements gate 展示给用户
- **THEN** summary SHALL 包含 change id、预计 branch、base branch 和已知 base commit
- **AND** 用户 MAY 在 approval 前通过自然语言修改 change id

#### Scenario: Approval 冻结 Change ID

- **GIVEN** requirements gate 展示 change id version N
- **WHEN** 用户输入有效 Gate Approval Token
- **THEN** approval SHALL 绑定并冻结 version N 的 change id
- **AND** promotion SHALL NOT 静默改名

#### Scenario: Change ID 冲突

- **GIVEN** change id 与 active/archive OpenSpec 目录、Git branch 或 worktree binding 冲突
- **WHEN** promotion preflight 执行
- **THEN** workflow SHALL 等待用户明确提供新名称或进入 blocked
- **AND** SHALL NOT 自动添加随机后缀

#### Scenario: Requirements 草稿不修改主仓库

- **GIVEN** workflow 处于 requirements
- **WHEN** goal、scope、acceptance criteria 或 test strategy 更新
- **THEN** 系统 SHALL 将版本化草稿保存到项目外 event store
- **AND** 结构化字段 SHALL 作为 gate、审计和 materialization 的 source of truth
- **AND** Markdown SHALL 作为可由结构化 snapshot 重新生成的人读 projection
- **AND** SHALL NOT 在 canonical main repository 创建未提交 OpenSpec change 文件

#### Scenario: Gate 冻结 Requirements Snapshot

- **GIVEN** workflow 处于 requirements.ready_for_review
- **WHEN** 用户输入有效 Gate Approval Token
- **THEN** 控制面 SHALL 记录被批准的 requirements snapshot version
- **AND** 后续 materialization SHALL 使用该版本
- **AND** 未被批准的并发或后续 draft SHALL NOT 混入产物

#### Scenario: 成功进入设计

- **GIVEN** requirements gate 已获得有效人工批准
- **AND** canonical main workspace 干净
- **AND** base branch 已与 remote tracking branch 同步或完成安全 fast-forward
- **WHEN** branch、worktree 和 change artifacts 均创建成功
- **THEN** workflow SHALL 绑定唯一 workspace 和 branch
- **AND** workspace binding SHALL 记录 base branch 和 base commit
- **AND** SHALL materialize proposal、spec delta 和去敏 workflow manifest
- **AND** SHALL NOT 将 design.md、ADR 或 tasks.md 标记为已完成
- **AND** SHALL 进入 design 的首个 sub-state

#### Scenario: Design Artifact 后续生成

- **GIVEN** requirements promotion 已创建 worktree 和需求类 artifact
- **WHEN** design executor 处理 design phase
- **THEN** design.md、所需 ADR 和 tasks.md SHALL 在绑定 worktree 中生成
- **AND** SHALL 经过 design gate 审阅后才能进入 building

#### Scenario: Worktree 创建失败

- **GIVEN** requirements gate 已批准
- **WHEN** Git 无法创建目标 branch 或 worktree
- **THEN** workflow SHALL 进入 `blocked`
- **AND** SHALL NOT 部分进入 design
- **AND** blocker SHALL 记录失败步骤和恢复建议

#### Scenario: Base Branch Diverged

- **GIVEN** 本地 base branch 与 remote tracking branch 已 diverged
- **WHEN** requirements promotion 执行 preflight
- **THEN** workflow SHALL 进入 blocked
- **AND** SHALL NOT 自动 reset、rebase 或选择任一侧

#### Scenario: Base Branch 可 Fast-forward

- **GIVEN** 本地 base branch 落后于 remote tracking branch
- **AND** 可以安全 fast-forward
- **WHEN** requirements promotion 执行 preflight
- **THEN** host SHALL 同步 base branch
- **AND** SHALL 从同步后的 commit 创建 worktree branch

#### Scenario: 离线使用本地基线

- **GIVEN** remote fetch 不可用
- **WHEN** 可信用户显式批准 local-base override
- **THEN** 系统 MAY 使用当前本地 base commit
- **AND** workflow event SHALL 记录 override reason、base branch、base commit 和 fetch failure

### Requirement: Design 到 Closing 复用同一 Worktree

进入 design 后，workflow SHALL 在 design、building、修改循环和 closing 全程复用已绑定 worktree。一个 active worktree SHALL 至多绑定一个 workflow。

#### Scenario: Building 复用设计 Worktree

- **GIVEN** design 在 worktree A 完成并通过 gate
- **WHEN** workflow 进入 building
- **THEN** building WorkItem SHALL 继续使用 worktree A
- **AND** SHALL NOT 创建新的 phase-specific worktree

#### Scenario: Worktree 绑定漂移

- **GIVEN** registry 绑定 branch A，但实际 worktree 已切换到 branch B
- **WHEN** agent 调用 `enter`
- **THEN** 系统 SHALL 阻止可写 WorkItem
- **AND** workflow SHALL 进入或保持 blocked 状态

#### Scenario: Merge 后清理

- **GIVEN** PR 已合入、change 已归档且 worktree 满足安全清理条件
- **WHEN** closing 完成 post-merge 确认
- **THEN** 控制面 SHALL 清理 worktree binding
- **AND** SHALL 将 workflow 标记为 done

### Requirement: Workflow Execution Lease

可执行 WorkItem SHALL 通过 lease 原子绑定 workflow version、session 和 actor，防止多个 session 同时推进同一状态。其他 session SHALL 仍可读取状态。

#### Scenario: 第二个 Session 尝试领取

- **GIVEN** session A 持有未过期 lease
- **WHEN** session B 对同一 workflow 调用 `enter`
- **THEN** session B SHALL 收到只读状态和 lease owner 摘要
- **AND** SHALL NOT 获得可执行 WorkItem

#### Scenario: Lease 超时恢复

- **GIVEN** lease owner 异常退出且 lease 已过期
- **WHEN** 新 session 调用 `enter`
- **THEN** 控制面 SHALL 记录 lease expiration
- **AND** MAY 向新 session 分配当前版本的新 lease

### Requirement: 统一 Workflow 状态发现

控制面 SHALL 从 canonical repository 识别项目 registry，并展示 exploring/requirements 项目、active workflows、worktree、branch、phase、sub-state、gate、lease、blocker 和 next action。

#### Scenario: 主仓库发现 Sibling Worktree

- **GIVEN** active workflow 位于 sibling worktree
- **WHEN** 用户在主仓库运行 `workflow status`
- **THEN** 系统 SHALL 展示该 workflow 及其 worktree 路径

#### Scenario: 多个 Active Workflow

- **GIVEN** 项目存在多个 active workflows
- **WHEN** 未指定 workflow 的 agent 调用 `enter`
- **THEN** 系统 SHALL 返回候选列表并要求选择
- **AND** SHALL NOT 猜测目标 workflow
- **AND** 列表 SHALL 提供创建新 Exploration 的选项

#### Scenario: 显式指定 Workflow

- **GIVEN** 启动参数或可信用户选择指定 workflow id
- **WHEN** session 执行 preflight
- **THEN** 系统 SHALL 优先恢复指定 workflow

#### Scenario: 从绑定 Worktree 启动

- **GIVEN** session cwd 位于 active workflow 的绑定 worktree
- **WHEN** session 执行 preflight
- **THEN** 系统 SHALL 恢复该 worktree 对应 workflow

#### Scenario: 主仓库只有一个 Active Workflow

- **GIVEN** session 从 canonical main repository 启动
- **AND** 项目只有一个 active workflow
- **WHEN** session 执行 preflight
- **THEN** 系统 SHALL 自动恢复该 workflow

#### Scenario: 没有 Active Workflow

- **GIVEN** session 位于 Managed Workspace Root
- **AND** 项目没有 active workflow
- **WHEN** session 执行 preflight
- **THEN** 系统 SHALL 创建新的 Exploration Workflow

### Requirement: 版本化项目流程模板

控制面 SHALL 使用版本化模板定义 phases、sub-states、gates、required evidence、workspace policy、branch pattern、checks 和 executor defaults。项目 `AGENTS.md` 和 workflow skill SHALL 只作为模板生成的 Prompt Adapter 接入说明，不得成为运行时状态 source of truth。

#### Scenario: Agent 读取短接入说明

- **WHEN** 项目完成控制面迁移
- **THEN** `AGENTS.md` SHALL 指示 agent 在每个 run 前调用 `workflow enter`
- **AND** SHALL 指示 agent 使用 `workflow report` 提交结果
- **AND** SHALL 指示需要可信 gate 或强写权限 enforcement 时使用 CLI Host Wrapper
- **AND** 实际状态 SHALL 由控制面执行

#### Scenario: 模板版本变化

- **GIVEN** workflow 创建时使用模板 version 1
- **WHEN** 项目默认模板升级到 version 2
- **THEN** active workflow SHALL 继续绑定 version 1，除非执行显式迁移

### Requirement: 签名 Workflow Receipt CI 审计

完整 workflow events SHALL 保留在项目外 event store。Closing SHALL 在 Host 完整重放验证通过后生成最小签名 `workflow-receipt.json`。CI SHALL 验证签名、Gate 摘要、artifact/evidence hash、base commit 和 change/PR 关联。

#### Scenario: Host History 验证失败

- **GIVEN** 本地 history 包含非法跳步、缺失 Gate Approval 或 snapshot 不一致
- **WHEN** Host 尝试生成 Receipt
- **THEN** Host SHALL 拒绝签名
- **AND** workflow SHALL NOT 进入 PR-ready 状态

#### Scenario: Receipt 签名无效

- **GIVEN** workflow-receipt.json 被 agent 或其他进程修改
- **WHEN** CI 使用仓库登记的 public key 验证
- **THEN** CI SHALL 失败

#### Scenario: 初始化专用 Workflow Key

- **GIVEN** Managed Workspace Root 尚无 trusted workflow signer
- **WHEN** 用户通过 Host 初始化签名能力
- **THEN** Host SHALL 生成专用 Ed25519 key pair
- **AND** private key SHALL 保存在 agent sandbox 和 Git 之外
- **AND** public key SHALL 以 key id 登记到项目 trusted signers
- **AND** SHALL NOT 复用用户现有 SSH private key

#### Scenario: Agent 无法读取 Private Key

- **WHEN** agent executor 运行
- **THEN** private key path、bytes 和 signing API SHALL NOT 暴露给 agent capability

#### Scenario: 多个 Trusted Signer

- **GIVEN** 项目配置了多个有效 public key
- **WHEN** CI 验证 Receipt
- **THEN** SHALL 根据 key id 选择对应 signer
- **AND** SHALL 支持后续 key rotation

#### Scenario: Retired Signer 保留历史验证

- **GIVEN** Receipt 使用状态为 `retired` 的 trusted signer 签发
- **WHEN** CI 验证已有 archived Receipt
- **THEN** CI SHALL 允许历史 Receipt 通过签名验证
- **AND** Host SHALL NOT 使用 retired signer 签发新的 Receipt

#### Scenario: Compromised Signer 使 Receipt 不可信

- **GIVEN** Receipt 使用状态为 `compromised` 的 trusted signer 签发
- **WHEN** CI 或 artifact checker 验证 Receipt
- **THEN** 验证 SHALL 失败
- **AND** 系统 SHALL 要求使用可信 Host 和非 compromised signer 重新签发

#### Scenario: Artifact Hash 不匹配

- **GIVEN** Receipt 签名有效
- **AND** PR 中 proposal、spec、design、tasks 或 evidence 内容与 Receipt hash 不同
- **WHEN** CI 验证 Receipt
- **THEN** CI SHALL 失败

#### Scenario: Receipt 最小化

- **WHEN** Host 生成 Receipt
- **THEN** SHALL NOT 包含聊天消息、完整 event log、用户输入原文、Session transcript、本地绝对路径或 approval secret
- **AND** SHALL 包含 event-chain root 和必需 Gate 摘要

#### Scenario: Archived Change 仍验证 Receipt

- **WHEN** change 被归档
- **THEN** CI 和 artifact checker SHALL 继续验证其 workflow-receipt.json

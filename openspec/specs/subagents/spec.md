# subagents 规格

## Purpose

定义子 agent 的子 session runtime 语义、子 run 生命周期、并发边界和 transcript inspect 能力。当前实现位于 `agent/subagent/`。
## Requirements
### Requirement: 子 agent 是完整子 session runtime

系统 SHALL 将子 agent 建模为不直接与用户交互的受限子 session。每个子 session SHALL 拥有独立 transcript、当前 mode、run 历史和可关联的 trace / usage / artifact 信息。

#### Scenario: 创建子 agent

- **GIVEN** 调用方提供创建子 agent 所需的名称、描述或 mode
- **WHEN** 调用 `CreateSubagent`
- **THEN** 系统 SHALL 创建一个新的 `subagent_id`
- **AND** SHALL 初始化该子 session 的 transcript、mode 和元数据

### Requirement: 子 session 支持多次 run

系统 SHALL 允许在同一个子 session 中发起多次 run。每次 run SHALL 拥有独立 `run_id` 和独立 trace 关联，但共享该子 session 的 transcript 与 session 级 mode。

#### Scenario: 在已有子 session 中再次运行

- **GIVEN** 一个已存在的子 session 且当前没有正在运行的子 run
- **WHEN** 调用 `RunSubagent`
- **THEN** 系统 SHALL 创建新的 `run_id`
- **AND** SHALL 复用当前子 session 的 mode 和 transcript 继续运行

### Requirement: 多个子 session 可并发，同一子 session 内 run 串行

系统 SHALL 支持多个子 session 同时存在并并发运行（并发受「跨子 session 并发队列化」约束）。同一个 `subagent_id` 任一时刻 SHALL 最多只有一个 active run；再次运行同一子 session 仍 SHALL 拒绝并等待或取消当前 run（不进入跨 session 队列）。

#### Scenario: 已有 active run 时再次运行同一子 session

- **GIVEN** 某个子 session 当前已有运行中的子 run
- **WHEN** 再次调用 `RunSubagent`
- **THEN** 系统 SHALL 拒绝该请求
- **AND** SHALL 要求先等待或取消当前 run

### Requirement: 跨子 session 并发队列化

系统 SHALL 支持多个子 session 并发运行，并对物理并发施加有界队列约束：同时执行 LLM/tool 的子 run 数 SHALL 不超过 `max_active`（默认 5）；超过 `max_active` 的 spawn SHALL 进入队列而非失败；排队中的 run 数 SHALL 不超过 `max_queued_runs`（默认 20），队列满时 SHALL 返回明确 `queue_full` 信号。

#### Scenario: 瞬时并发超限进入队列

- **GIVEN** 当前正在执行的子 run 数已达到 `max_active`
- **WHEN** 调用 `RunSubagent` 创建新的子 run
- **THEN** 系统 SHALL 将该 run 标记为 `queued` 并返回 `run_id`
- **AND** 当有执行槽释放时 SHALL 按队列顺序放行

#### Scenario: 队列满返回 queue_full

- **GIVEN** 排队中的 run 数已达到 `max_queued_runs`
- **WHEN** 再次调用 `RunSubagent`
- **THEN** 系统 SHALL 返回 `queue_full` 信号而非无限排队或失败

### Requirement: 并发许可绑定执行而非等待

系统的并发许可 SHALL 只绑定「实际 LLM/tool 执行」阶段，SHALL NOT 覆盖父 agent 阻塞等待子 agent 的等待区间。父 agent 等待子 run 时 SHALL NOT 占用执行许可。

#### Scenario: 父等待子不占用许可

- **GIVEN** 父 agent 已发起多个子 run 并阻塞等待全部完成
- **WHEN** 父 agent 处于等待状态
- **THEN** 父 agent SHALL NOT 占用并发许可
- **AND** 所有子 run 均能获得许可并完成（不自我饥饿）

### Requirement: 深度到限撤 spawn 工具

当子 session 的 spawn 深度达到 `max_depth` 时，系统 SHALL 从该子 agent 的工具注册中移除 spawn 类工具（`CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent` **以及 `StartWorkflow`/`RunWorkflow`**，后两者语义上等价于一次性拉起整张图），让子 agent 自行完成任务，而非返回错误。

#### Scenario: 深度到限子 agent 无 spawn 工具

- **GIVEN** 一个子 session 的 spawn 深度已达到 `max_depth`
- **WHEN** 构建该子 agent 的工具注册
- **THEN** 其工具集 SHALL NOT 包含 spawn 类工具（含 `StartWorkflow`/`RunWorkflow`）
- **AND** SHALL 保留其余工具（含只读的 `GetWorkflow`/`DeclareWorkflow`/`CancelWorkflow`）完成自身任务

### Requirement: 累计 spawn 计数上限

系统 SHALL 对累计 spawn 计数（create 与每次 run 各计一次）执行 `max_spawns`（默认 200）上限，超限时拒绝新的 spawn。计数的 orchestration 边界 SHALL 是 workflow run（桶键 = `workflow_id`）：一个 workflow run 的展开项共享一个桶，嵌套 workflow 各自独立成桶；无 workflow 的主 loop SHALL 沿用按 manager 生命周期的累计语义（每 turn 复位归后续 change）。

#### Scenario: 嵌套 workflow 各自独立成桶

- **GIVEN** workflow A 的某个节点内又声明并启动了 workflow B
- **WHEN** B 在其节点里 spawn 子 agent
- **THEN** 这些 spawn SHALL 计入 B 自己的桶
- **AND** SHALL NOT 因 A 的累计消耗而失败

### Requirement: 子 session 显式父子身份

`SubagentSessionRecord` SHALL 维护 `parent_run_id`/`workflow_id`/`node_id`/`depth` 显式字段，使延迟执行的子 run 仍能追溯其逻辑父子关系与归属。

#### Scenario: 排队延迟执行的子 run 保留身份

- **GIVEN** 一个子 run 在队列中延迟到父 run 结束后才执行
- **WHEN** 读取该子 run 的身份信息
- **THEN** 系统 SHALL 返回其正确的 `parent_run_id` 与 `depth`
- **AND** SHALL 返回其所属 `workflow_id`（若存在）

### Requirement: 子 session 默认使用 isolated 上下文

子 session 默认 SHALL 使用 `isolated` 上下文。子 session SHALL NOT 默认复制父 session 的 message transcript。

#### Scenario: 默认创建子 session

- **GIVEN** 调用方未显式请求 `fork parent transcript`
- **WHEN** 创建子 session
- **THEN** 子 session SHALL 仅接收显式传入的 task / context
- **AND** SHALL NOT 自动继承父 session 的完整消息历史

### Requirement: 子 transcript inspect 默认受限

系统 SHALL 通过专用 inspect 接口提供子 transcript 摘要或最近消息读取，但 SHALL 默认限制返回范围。

「限制返回范围」SHALL 同时覆盖**条数**与**单条内容长度**两个维度：任一条返回文本（消息 `content`、
摘要 `summary`、工具调用 `arguments`）SHALL 不超过一个固定上限，且该上限 SHALL 与 HTTP 出口
（workflow 节点 transcript 只读接口）的对应上限**同值**——同一份 inspect 结果在模型面与 HTTP 面
SHALL NOT 分叉。

被截断的字段 SHALL 伴随一个**布尔**截断标志（`content_truncated` / `summary_truncated` /
`arguments_truncated`），SHALL NOT 依赖调用方用长度比较自行推断。标志 SHALL 表达「本条是否发生过
截断」这一事实，跨层组合时 SHALL 取或（上游截过而下游预算更宽时 SHALL NOT 报未截断）。

全文 SHALL 通过显式引用（result_ref / summary_ref / ReadWorkflowResult）按需读取，SHALL NOT 要求
模型面出口默认返回全文。

#### Scenario: 查看最近消息

- **GIVEN** 父 agent 需要检查某个子 run 最近的执行情况
- **WHEN** 调用 `InspectSubagentTranscript`
- **THEN** 系统 SHALL 返回摘要或最近 `N` 条消息
- **AND** SHALL NOT 默认返回整份子 transcript

#### Scenario: 超长单条内容在模型面被截断

- **GIVEN** 子 run 的某条消息 content 远超单条上限（例如 30,000 字）
- **WHEN** 父 agent 调用 `InspectSubagentTranscript` 读取最近消息
- **THEN** 返回的该条 `content` SHALL 不超过单条上限
- **AND** 该条 SHALL 携带 `content_truncated` 为 `true`

#### Scenario: 超长摘要同样受限

- **GIVEN** 子 run 的 summary 远超单条上限
- **WHEN** 调用 `InspectSubagentTranscript` 且 `scope` 为 `summary`
- **THEN** 返回的 `summary` SHALL 不超过单条上限
- **AND** SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: 工具结果消息与普通消息同口径

- **GIVEN** 子 run 含一条超长的 tool 角色消息（工具结果全文）
- **WHEN** 调用方显式请求包含工具结果（`include_tool_results=true`）
- **THEN** 该条 `content` SHALL 与普通消息**适用同一个单条上限**
- **AND** SHALL 携带 `content_truncated` 为 `true`

#### Scenario: 模型面与 HTTP 面同值

- **GIVEN** 同一份 inspect 结果分别经模型面工具与 HTTP 路由出口返回
- **WHEN** 比较两侧对同一字段的上限
- **THEN** 两个上限 SHALL 相等
- **AND** 该相等关系 SHALL 有测试机械锁定（SHALL NOT 只靠注释约定）

### Requirement: message bus 模型面出口有界

编排 message bus（`agent/subagent/bus.py`）返回给**模型面**的消息 SHALL 在**单条**与**总量**两个维度上均 bounded：单条 `summary` SHALL 不超过一个**固定**的单条内容上限，返回的消息**总量** SHALL 不超过一个固定的输出上限。单条上限 SHALL 与模型面其它出口的单条内容上限（`TRANSCRIPT_ITEM_LIMIT`）**同值**，SHALL NOT 另立一套数字。

**总量**维是本 Requirement 的核心，SHALL NOT 只界住单条：`read()` 的 `max_tokens` / `limit` 两个参数由调用方（被检视的模型）给出，若不加钳制，单条截断后总量仍随调用方参数无限增长（实测 `max_tokens=10^9` 时返回 100 条 / 3,000,000 字符）——「界不可被被检视对象影响」。

单条上限 SHALL **独立于调用方传入的 `max_tokens`**：发布侧 `max_tokens` 是 summarize 的阈值，若它可无上界地高于单条上限，summarize 分支就不会触发、原文直入 bus。故发布侧阈值 SHALL 被钳到与单条上限等价的值，且 summarize 闸门 SHALL 在阈值**等于**上限时即触发（`>=`），使 summarize SHALL 必然触发（`estimate_tokens` 向下取整，严格大于会留缝）。

**发布侧的界由出口投影保证，不由阈值保证**：`_summarize` 的 LLM 分支是 advisory、**不保证**产出 ≤ 上限（见 `agent/context/summarizer.py`：「not a hard guarantee」，预算只拼进 prompt）。因此发布侧的**模型面输出**（`PublishBusMessage` 的回包，即第 5 条出口）SHALL 与消费侧同走出口投影——被截断的 SHALL 不超过单条上限并携带 `summary_truncated`。SHALL NOT 声称「阈值钳制使发布侧严格不超过上限」这种对 LLM 分支不成立的断言。

**队列不因出口投影而改变**：`publish()` 入队的内容 SHALL 保留原样（含 LLM 摘要超预算的情形）；bounded 化只发生在出口投影。

被截断的单条消息 SHALL 携带布尔标志（`summary_truncated`），SHALL NOT 依赖调用方用长度比较自行推断；被截断消息的 `token_count` SHALL 与截断后的文本一致（SHALL NOT 继续报告全文的记账值）。

截断 SHALL NOT 修改队列中保存的消息本身：bus 的会话恢复视图（`compact_summary()`）与 checkpoint 快照 SHALL 仍看到未截断的原文。

bus 消息**不落盘**，因此截断 SHALL NOT 声称「全文可从某个引用取得」——没有权威件可指时，任何 ref 字样都是一句假话。截断只如实回流标志本身。

#### Scenario: ReadBus 单条超长内容被截断

- **GIVEN** bus 中存在一条 `summary` 为 30,000 字的子 agent 消息
- **WHEN** 父 agent 调用 `ReadBus`
- **THEN** 返回的该条 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: ReadBus 总量不随调用方参数放大

- **GIVEN** bus 满载 100 条、每条 30,000 字
- **WHEN** 父 agent 调用 `ReadBus` 并传入一个极大的 `max_tokens`（例如 10^9）与极大的 `limit`
- **THEN** 返回的消息条数 SHALL 不超过固定的条数上限
- **AND** 返回的总字符量 SHALL 不超过与快照出口同界的固定上限
- **AND** 结果 SHALL NOT 随传入参数增大而无限增大

#### Scenario: 单条超窗时仍返回最新一条（截断后）

- **GIVEN** bus 中最新的那条消息其体量**单独就超过**消费侧 token 窗口
- **WHEN** 父 agent 以该窗口调用 `ReadBus`
- **THEN** 系统 SHALL 仍返回这条最新的消息（消费者 SHALL NOT 失明）
- **AND** 返回的 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: 截断不改动队列中的原文

- **GIVEN** bus 中存在一条超长消息
- **WHEN** 父 agent 经 `ReadBus` 读到该条的截断件
- **THEN** bus 队列中保存的该条 `summary` SHALL 仍为全文
- **AND** `compact_summary()` 的输出 SHALL NOT 因该次读取而变短

#### Scenario: 截断后 token_count 与文本一致

- **GIVEN** 一条 30,000 字的 bus 消息被截断后返回
- **WHEN** 调用方读取该条的 `token_count`
- **THEN** 该值 SHALL 与截断后的文本一致
- **AND** SHALL NOT 等于全文的记账值

#### Scenario: 截断上限与其它模型面出口同值

- **GIVEN** 同一份子 agent 撰写的文本经 bus 出口与经 run envelope 出口返回
- **WHEN** 比较两处对单条内容的上限
- **THEN** 两个上限 SHALL 相等
- **AND** 该相等关系 SHALL 有测试机械锁定（SHALL NOT 只靠注释约定）

#### Scenario: 发布侧阈值不放大单条出口

- **GIVEN** 父 agent 调 `PublishBusMessage` 时传入一个远超单条上限的 `max_tokens`（例如 10^9）
- **WHEN** 随后通过 `ReadBus` 读回该消息
- **THEN** 读回的 `summary` SHALL 仍不超过固定的单条内容上限
- **AND** 结果 SHALL NOT 随传入 `max_tokens` 的取值变化

#### Scenario: 发布回包不因摘要超预算而越界

- **GIVEN** summarize 的 LLM 分支返回了一个**超过**单条上限的摘要（advisory 预算，允许发生）
- **WHEN** `PublishBusMessage` 返回其回包
- **THEN** 回包的 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`
- **AND** bus 队列中保存的该条 SHALL 仍保留摘要的完整文本

#### Scenario: 截断标记不指向不存在的引用

- **GIVEN** 一条因超长而被截断的 bus 消息
- **WHEN** 该消息经模型面出口返回
- **THEN** 截断相关的文本 SHALL NOT 声称全文可从某个引用（`result_ref` / `summary_ref`）取得
- **AND** SHALL 仍然如实表达「该条已被截断」

### Requirement: 角色 Agent 类型注册

系统 SHALL 支持注册五种开发角色 agent 类型：Planner、Reviewer、Builder、CodeReviewer、Closer。每种角色 agent SHALL 作为子 session 运行，使用现有 subagent runtime。

#### Scenario: 注册 Planner agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `planner` 类型 SHALL 映射到 `planning` phase
- **AND** Planner agent SHALL 负责从 `exploring` 到 `ready_for_review` 的所有 `planning` sub_state

#### Scenario: 注册 Reviewer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `reviewer` 类型 SHALL 映射到 `reviewing` phase
- **AND** Reviewer agent SHALL 负责从 `reading_docs` 到 `ready_for_review` 的所有 `reviewing` sub_state
- **AND** Reviewer agent SHALL 对已完成 grill 自审的设计文档做独立评审，而非执行 batch-grill-me

#### Scenario: 注册 Builder agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `builder` 类型 SHALL 映射到 `building` phase
- **AND** Builder agent SHALL 负责从 `writing_tests` 到 `ready_for_review` 的所有 `building` sub_state

#### Scenario: 注册 Closer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `closer` 类型 SHALL 映射到 `closing` phase
- **AND** Closer agent SHALL 负责从 `syncing_specs` 到 `ready_for_review` 的所有 `closing` sub_state

#### Scenario: 注册 CodeReviewer agent

- **WHEN** 系统初始化角色 agent 注册表
- **THEN** `code-reviewer` 类型 SHALL 映射到 `code-review` phase
- **AND** CodeReviewer agent SHALL 负责从 `reading_diff` 到 `ready_for_review` 的所有 `code-review` sub_state

### Requirement: 角色 Agent 路由

系统 SHALL 根据 `handoff.json` 的当前 state 自动选择对应的角色 agent 类型。

#### Scenario: 根据 phase 路由 agent

- **GIVEN** 一个 change 的 `handoff.json` 中 `state.phase` 为 `planning`
- **WHEN** 启动角色 agent
- **THEN** 系统 SHALL 创建类型为 `planner` 的子 session

#### Scenario: human review gate 后路由

- **GIVEN** change 处于 `planning.ready_for_review`
- **WHEN** 人确认通过
- **THEN** 系统 SHALL 更新 state 到 `reviewing.reading_docs`
- **AND** 系统 SHALL 创建类型为 `reviewer` 的子 session

#### Scenario: 同一 agent 继续下一阶段

- **GIVEN** 当前 agent 完成了 `planning.ready_for_review`
- **WHEN** 人确认通过且选择不切换 agent
- **THEN** 系统 SHALL 允许同一 agent 进入 `reviewing` phase
- **AND** `handoff.json` 中 `current_agent.type` SHALL 更新为 `reviewer`


# multi-agent-collaboration spec delta: 内置模板归一（RunPattern 融合进 Workflow 入口）

## MODIFIED Requirements

### Requirement: Orchestration Pattern Library

The subagent system SHALL provide an orchestration pattern library: orchestrator-worker, peer-review, hierarchical, and bidding patterns, via a common OrcPattern interface. The four patterns SHALL be compiled to Workflow DSL templates through the code-owned registry (`compile_pattern`) and executed through the unified scheduler. The library SHALL be reachable through the unified Workflow entry (`RunWorkflow`)'s `template` input; a separate `RunPattern` tool and its `run_pattern()` adapter SHALL NOT exist.

#### Scenario: bidding pattern selects best proposal

- Given multiple subagents proposing solutions via the bidding pattern
- When the selector evaluates the proposals
- Then the best proposal is selected
- And the pattern is driven by the common OrcPattern interface, compiled to a WorkflowSpec template
- And the caller reaches it through `RunWorkflow(template="bidding", ...)`, not through a dedicated pattern tool

### Requirement: 内置编排模式降级为 DSL 模板

系统 SHALL 将 4 个内置编排模式（orchestrator-worker / peer-review / hierarchical / bidding）编译为 DSL 模板，并 SHALL 只经统一 Workflow 入口（`RunWorkflow` 的 `template` 入参）触达。系统 SHALL NOT 保留 `run_pattern()` 兼容 adapter，也 SHALL NOT 返回 pattern 专属的扁平结构（`pattern`/`completed`/`failed`/`workers`/`summary`/`selected`/`selector`/`bus`）。模板编译产出 SHALL 与 `compile_pattern` 的产出逐字一致，其度量字段（`workflow_id` / `spec_hash` / `critical_path_s` / `peak_active` / `total_cost`）SHALL 由统一入口的 bounded 投影承载（哈希字段对外命名为 `spec_hash`；历史 `RunPattern` 返回体的 `workflow_spec_hash` 命名随该返回体一并退役）。

#### Scenario: template 输入编译为 DSL 模板

- **GIVEN** 调用 `RunWorkflow(template="orchestrator-worker", task="research", params={"workers": 3})`
- **WHEN** 执行
- **THEN** 系统 SHALL 经既有模板编译器编译为 WorkflowSpec 并走统一调度器
- **AND** 编译出的 spec SHALL 与 `compile_pattern("orchestrator-worker", task="research", params={"workers": 3})` 逐字一致（`spec_hash` 相等）

### Requirement: 资产保存是显式的，且 spec 不穿过模型输出

系统 SHALL 提供显式保存动作：把**已声明或已运行过**的图按 `workflow_id` 沉淀为命名资产，`name`/`description` 由调用方给出，而 spec 正文 SHALL 由服务端从该 `workflow_id` 取出，SHALL NOT 要求模型重新输出 spec 正文。保存 SHALL 复用既有写盘纪律：原子写（tmp + `os.replace`）、路径段级白名单校验（拒绝 `.`/`..` 与越界字符）、写入目标路径上任一环节为 symlink 时 SHALL 拒绝穿透写入。slug SHALL 同时满足 `^[a-z0-9-]+$` 与既有路径段白名单的交集约束。系统 SHALL NOT 因「跑过一张图」而自动入库。

#### Scenario: 保存刚跑过的图不要求模型重述 spec

- **GIVEN** 模型刚通过统一 Workflow 入口（`RunWorkflow` 的 `spec` 或 `template` 入参）跑完一张图并拿到 `workflow_id`
- **WHEN** 调用保存动作并只给出 `workflow_id` + `name` + `description`
- **THEN** 系统 SHALL 从该 `workflow_id` 取出 spec 并落盘为资产
- **AND** 该调用 SHALL NOT 需要模型在参数中携带 spec 正文

#### Scenario: 非法 slug 与 symlink 写入被拒绝

- **GIVEN** 一个 `name` 为 `../escape`、`a/b`、`A-B`（含大写）或空串
- **WHEN** 调用保存动作
- **THEN** 系统 SHALL 拒绝该次写入
- **AND** 当目标路径上任一环节是 symlink 时，系统 SHALL 拒绝穿透写入而非跟随链接

#### Scenario: 未保存的图不入库

- **GIVEN** 一个会话跑了一张图但从未调用保存动作
- **WHEN** 在一次新会话中列出资产
- **THEN** 该图 SHALL NOT 出现

### Requirement: 资产的两类载体与参数化复用

资产 SHALL 支持两类载体，由图的**来源路径**决定：从内置编排模式（经统一 Workflow 入口的 `template` 入参触达）产出的图 SHALL 保存为**配方**（`{pattern, params, task}`），加载时经既有模板编译器重新编译；从 `DeclareWorkflow`/`RunWorkflow`（`spec` 入参）产出的图 SHALL 保存为 **spec 正文**（`WorkflowSpec.to_dict()` 的结果），因为该路径的输入已是展开后的 spec、不存在可还原的配方。DSL 资产 SHALL 允许保存者声明一个**覆盖面**（`overrides: {node_id: [field, ...]}`），其中的 `field` SHALL 限制在一个封闭子集内（`task` / `items` / `max_items` / `max_tokens` / `max_time_s`）；调用时对未声明的 `(node_id, field)` 组合 SHALL 拒绝。覆盖面 SHALL 以对既有 spec 字段的直接赋值实现，SHALL NOT 引入插值、表达式求值或 item 名模板等新方言。覆盖面 SHALL 在既有 `parse_workflow_spec` 校验**之前**应用，因此 reducer 冲突、环的可启动性、节点数与闸值上限等既有校验 SHALL 全部照常生效。

#### Scenario: pattern 资产保留参数化

- **GIVEN** 资产由 `RunWorkflow(template="orchestrator-worker", task=…, params={"workers": 3})` 跑出后保存
- **WHEN** 以 `params={"workers": 5}` 调用该资产
- **THEN** 系统 SHALL 经既有模板编译器重新编译，展开出 5 个 foreach 项
- **AND** SHALL NOT 需要保存者或调用者手改 spec 的 `items` 列表

#### Scenario: DSL 资产按声明的覆盖面参数化

- **GIVEN** 一份 DSL 资产声明 `overrides: {"workers": ["items"]}`
- **WHEN** 调用时给出 `overrides={"workers": {"items": [12 个项]}}`
- **THEN** 系统 SHALL 把覆盖应用到该节点的 `items` 字段后再走校验与调度
- **AND** 覆盖后的 spec SHALL 通过既有 `parse_workflow_spec` 的全部校验

#### Scenario: 未声明的覆盖面被拒绝

- **GIVEN** 一份 DSL 资产声明的覆盖面只有 `{"workers": ["items"]}`
- **WHEN** 调用时给出 `overrides={"workers": {"task": "改过的任务"}}`
- **THEN** 系统 SHALL 拒绝该次调用并报 `override_not_declared`
- **AND** SHALL NOT 静默忽略该覆盖后照常运行

#### Scenario: 覆盖破坏既有不变量时由既有校验拒绝

- **GIVEN** 一次覆盖把某节点的 `items` 置为空列表
- **WHEN** 加载该资产
- **THEN** 既有 `parse_workflow_spec` SHALL 拒绝该 spec 并给出自足的错误信息
- **AND** 系统 SHALL NOT 为资产加载引入第二套校验规则

## ADDED Requirements

### Requirement: 统一 Workflow 入口的模板输入

统一 Workflow 入口 `RunWorkflow` SHALL 接受 **exactly one of** `{spec, template}`：`spec` 为模型手写的 DAG spec，`template` 为内置模板名（封闭枚举：orchestrator-worker / peer-review / hierarchical / bidding）。`template` 路径 SHALL 要求 `task`（必填），SHALL 接受可选 `params`（封闭键集：`workers` / `teams` / `proposers` / `max_rounds` / `worker_max_tokens` / `worker_max_time_s`）。系统 SHALL 对非法组合**结构化拒绝**（返回自足的 `reason`，指明期望的入参形态）而 SHALL NOT 静默取其一或忽略多余入参。模板参数化 SHALL 只发生在 Python（`compile_pattern`），系统 SHALL NOT 引入 spec 内的模板字段、占位符插值、表达式求值或静态模板文件。

#### Scenario: template 与 spec 互斥

- **GIVEN** 同时给出 `spec` 与 `template`，或两者都不给
- **WHEN** 调用 `RunWorkflow`
- **THEN** 系统 SHALL 拒绝该次调用并报告期望「二选一」
- **AND** SHALL NOT 静默选用其中一条路径

#### Scenario: template 缺 task 或名字未知被拒绝

- **GIVEN** 给出 `template` 但缺 `task`，或 `template` 名不在枚举内
- **WHEN** 调用 `RunWorkflow`
- **THEN** 系统 SHALL 结构化拒绝并列出可用模板名
- **AND** SHALL NOT 用默认值补 `task` 后照常运行

#### Scenario: spec 路径不接受模板入参

- **GIVEN** 走 `spec` 路径却同时给出 `task` 或 `params`
- **WHEN** 调用 `RunWorkflow`
- **THEN** 系统 SHALL 拒绝该次调用
- **AND** SHALL NOT 忽略这些入参后照常运行（避免「以为 params 生效了」的假象）

#### Scenario: 模板参数化留在 Python

- **GIVEN** `template="peer-review"` 与 `params={"max_rounds": 4}`
- **WHEN** 系统编译该模板
- **THEN** 展开后的 `foreach.items` / route 的 `max_routes` 等 SHALL 由 Python 直接生成具体值
- **AND** 系统 SHALL NOT 要求模型在 spec 中书写占位符，也 SHALL NOT 为展开求值任何模型生成的文本

### Requirement: 编排入口返回单一的 bounded 投影

统一 Workflow 入口 SHALL 让父 agent 收到的结果形状**不随入参变化**：`template` 路径与 `spec` 路径 SHALL 返回同一种形状，即调度器的 `parent_envelope()` bounded 投影。该投影 SHALL NOT 包含 `bus`（非权威广播通道不进父上下文）；`bus` SHALL 仍在 run 内可经 `PublishBusMessage`/`ReadBus` 触达。内容 SHALL 经 `nodes[]` 的有界摘要与 `root_result_ref`（以及 `GetWorkflow(detail='nodes')` 的逐节点 `result_ref`）按需读回，SHALL NOT 在结果体内联随图规模线性增长的数组。系统 SHALL 为等待终态的调用与 `wait=false` 的启动回执保留显式判别子（回执的 `status` 为 `running`，与终态 status 集合不相交）。

#### Scenario: 两条路径返回同一形状

- **GIVEN** 一次 `RunWorkflow(spec=…)` 与一次等价的 `RunWorkflow(template=…)`
- **WHEN** 两次调用都等待终态
- **THEN** 两个返回体的键集 SHALL 相等
- **AND** 其中 SHALL NOT 出现 `pattern` / `workers` / `selected` / `selector` 这类 pattern 专属扁平字段

#### Scenario: bus 不进父上下文

- **GIVEN** 一次编排里多个 worker 发布了 bus 消息
- **WHEN** 父 agent 收到编排入口的返回体
- **THEN** 该返回体 SHALL NOT 含 `bus` 键
- **AND** 父 agent SHALL 仍能在 run 内通过 `ReadBus` 读到有界的 bus 摘要

#### Scenario: 明细经 refs 按需读回

- **GIVEN** 一个 foreach 节点展开了 N 个 worker
- **WHEN** 父 agent 需要某个 worker 的完整产出
- **THEN** 该 foreach 节点在结果投影里 SHALL 是一条 bounded 摘要（`subagent_ids` 等线性数组 SHALL NOT 出现）
- **AND** 系统 SHALL 经 `GetWorkflow(detail='nodes')` 提供逐节点 `result_ref`，供 `ReadWorkflowResult` 读回全文
- **AND** 对 `kind=="foreach"` 节点，系统 SHALL 经该出口的只读投影暴露**每个已成功展开项**的 `result_ref`（`item_runs` 已是权威身份源），使成功项的 per-worker 全文在统一出口下可达
- **AND** 失败 / 取消 / 预算超限的展开项 SHALL NOT 被承诺 `result_ref`（这些 run 不落盘，`result_ref` 恒为 `None`），其失败信号 SHALL 以 bounded `reason` 与状态呈现——与既有 `_worker_entry` 只对有 ref 的成功项注入 ref 同口径
- **AND** 该投影 SHALL 跳过未派发的空槽，且自带固定条数上限并显式报告被省略的项数——字段定义 SHALL 单一可测：`items_total = len(state.item_runs)`（= 本轮展开项数，含空槽），`item_refs_omitted = items_total - len(item_refs)`（涵盖**空槽**与**超固定上限**两类来源）。`item_refs` 的长度 SHALL 不超过一个固定常数上限（复用既有的 `_PARENT_NODES_LIMIT` = 200，不新增常数）；`params` 的计数键无上界，展开项数 SHALL NOT 让该只读出口重新退化为随规模线性的数组
- **AND** `item_refs` SHALL 只反映容器的**最后一轮**展开（route 回边重跑容器时 `item_runs` 被既有语义整体重置），SHALL NOT 声称覆盖历史各轮的累计展开

#### Scenario: 启动回执与终态结果有显式判别子

- **GIVEN** 一次 `RunWorkflow(template=…, wait=false)`
- **WHEN** 调用立即返回
- **THEN** 返回体的 `status` SHALL 为 `running`，且 SHALL 与终态 status 集合不相交
- **AND** 调用方 SHALL 能据此区分回执与结果，而无需猜测入参

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
- **THEN** 该 foreach 节点在投影里 SHALL 是一条 bounded 摘要（`subagent_ids` 等线性数组 SHALL NOT 出现）
- **AND** 系统 SHALL 经 `GetWorkflow(detail='nodes')` 提供逐节点 `result_ref`，供 `ReadWorkflowResult` 读回全文

#### Scenario: 启动回执与终态结果有显式判别子

- **GIVEN** 一次 `RunWorkflow(template=…, wait=false)`
- **WHEN** 调用立即返回
- **THEN** 返回体的 `status` SHALL 为 `running`，且 SHALL 与终态 status 集合不相交
- **AND** 调用方 SHALL 能据此区分回执与结果，而无需猜测入参

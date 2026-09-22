## REMOVED Requirements

### Requirement: 四阶段生命周期

**Reason**: 四阶段状态机（`wayfinding` / `planning` / `building` / `closing`）已停用（AGENTS.md 声明；本 change 退役其实现）。开发流程精简为「OpenSpec 主干 + 强制独立审阅闭环」，不再由 phase/sub_state 推进驱动，`flow approve` 等 gate 家族子命令一并删除。

**Migration**: 流程推进改由 OpenSpec 主干（proposal → grill → worktree → TDD → spec sync → PR）与 `/review-loop` 承担；状态查询用 `flow status`（读事件投影）。

### Requirement: Phase 内部 sub_state 定义

**Reason**: 随四阶段生命周期退役——`sub_state` 概念仅服务于已停用的 phase 推进，无活消费者。

**Migration**: 无。状态观测改用 `flow status` 输出的投影 state。

### Requirement: Human review gate

**Reason**: gate 停止机制属已停用仪式（AGENTS.md 明列）；`flow approve` / `awaiting_human_review` 等无生产调用方（实测）。

**Migration**: 人工介入改由 OpenSpec 主干中的人确认节点（如 grill 停轮确认）与 PR review 承担。

### Requirement: 阻塞状态

**Reason**: `flow block` / `flow confirm` 与三个 `awaiting_*` 等待态**只由 `flow block` 自己写入**，活流程无一处使用（实测）。

**Migration**: 需要等待人工输入时，用当前成熟的停轮机制（如 grill 的停轮确认、`AskUserQuestion`），不再写状态机等待态。

### Requirement: 角色 Agent 类型

**Reason**: `role_registry.py` 只被测试与 `dispatcher.py` 消费，二者均无生产调用方（实测）；角色分派依赖已停用的 phase。

**Migration**: 子 Agent 角色由调用方在 `RunSubagent` 的 task 中直接描述；本仓库的 grill / review-loop 已各自指定独立零记忆 reviewer，不依赖角色注册表。

### Requirement: 单 Agent 全流程兼容

**Reason**: 该 Requirement 描述的是「单 agent 走完四个 phase」的兼容语义，随四阶段退役消失。

**Migration**: 无。流程不再以「走完 phase」建模。

### Requirement: 路由配置

**Reason**: `routing` 是 `handoff.json` schema 的一部分（phase → executor 映射），随 handoff 与四阶段退役消失；无活消费者。

**Migration**: 无。执行者选择由调用方在 OpenSpec 主干各步骤直接决定。

## MODIFIED Requirements

### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。投影 SHALL 由事件日志 replay 生成 `workflow-state.json`。Agent 不 SHALL 直接编辑投影文件来声明状态变化；所有状态变化 SHALL 通过 CLI 追加事件并重新生成投影。

自本 change 起，受保护 artifact 的写入通道（`workflow_state.py` 的 `artifact-event` 与 `review-manifest`）SHALL 以 change 的合法性（change 目录存在且含 `proposal.md` 或 `handoff.json`）为前置。目标解析 SHALL 采用 active 目录优先、否则回退到 `openspec/changes/archive/<date>-<id>/`；解析结果 SHALL 与查询的 change id 一致。对已归档目标，写入 SHALL 落在归档目录内，且 SHALL NOT 触发投影刷新。对 active 目标，成功写入后 SHALL 重新生成投影。

`handoff.json` 作为投影载体 SHALL 退役：自愈 SHALL NOT 再产出该文件，其残留耦合（phase 协议层必填、未 gitignore）SHALL 一并消除。

#### Scenario: 事件日志是权威事实来源

- **WHEN** 需要确定一个 change 的开发流程状态
- **THEN** 系统 SHALL 由该 change 的 `workflow-events.jsonl` replay 生成 `workflow-state.json` 投影
- **AND** SHALL NOT 依赖 `handoff.json`

#### Scenario: 任意 change 可查询状态

- **WHEN** 对任一 change 运行 `flow status`
- **THEN** 系统 SHALL 输出该 change 的投影状态
- **AND** SHALL 容忍异构派生（不要求首事件为 `change_created`）

#### Scenario: 自愈不再产出 handoff.json

- **WHEN** 对一个当代 change 运行 `flow status`
- **THEN** 该 change 目录 SHALL NOT 新增 `handoff.json`

#### Scenario: 受保护写通道不要求 handoff.json

- **WHEN** 对一个无 `handoff.json` 的当代 change 运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 成功写入（exit 0）

#### Scenario: 受保护写通道支持已归档 change

- **GIVEN** 一个已归档 change（active 目录不存在）
- **WHEN** 以裸 change id 运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 成功写入且落在归档目录内
- **AND** SHALL NOT 在 active 路径新建目录，也 SHALL NOT 在归档目录产出投影文件

### Requirement: Workflow 总开关

`scripts/workflow_methods.json` SHALL 提供 `workflow.enabled` 布尔开关，默认值为 `true`。当其为 `false` 时，workflow automation SHALL 视为未启用：受保护写通道 SHALL 拒绝写入，PreToolUse 门禁 SHALL NOT 阻止写操作。

原口径中依赖 `discover` 与 `check_phase_done.py` 的表述 SHALL 移除——二者随本 change 退役。

#### Scenario: workflow 未启用时写通道拒绝

- **GIVEN** `workflow.enabled = false`
- **WHEN** 调用 `workflow_state.py artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 以明确错误拒绝

#### Scenario: workflow 未启用时门禁退化

- **GIVEN** `workflow.enabled = false`
- **WHEN** PreToolUse 门禁运行
- **THEN** 系统 SHALL NOT 阻止写操作

### Requirement: flow 命令与受保护路径

`workflow_state.py` 的 `flow` 子命令组 SHALL 仅保留 `flow status`（投影查询与等待态只读检查）。原 gate 家族子命令（`flow approve` / `flow advance` / `flow block` / `flow confirm`）SHALL 删除，因为四阶段状态机已停用且它们无生产调用方。

guard 的写通道豁免 SHALL 相应收窄为 `flow status`；已删除的子命令 SHALL NOT 再被豁免。

#### Scenario: flow 只保留 status

- **WHEN** 调用 `workflow_state.py flow status --change <id>`
- **THEN** 系统 SHALL 返回该 change 的投影状态

#### Scenario: 已删子命令不再存在

- **WHEN** 调用 `workflow_state.py flow approve`（或 advance / block / confirm）
- **THEN** CLI SHALL 以明确错误退出（未知子命令），SHALL NOT 静默成功

#### Scenario: guard 豁免收窄

- **WHEN** guard 扫描 Bash 命令中的 `workflow_state.py` 调用
- **THEN** 仅 SHALL 豁免 `flow status` 与 `artifact-event` / `review-manifest` / `policy-*`
- **AND** SHALL NOT 再豁免 `flow approve` / `advance` / `block` / `confirm`

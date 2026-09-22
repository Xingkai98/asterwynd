# Design — retire-4phase-state-machine

## Context

见 `proposal.md`。关键事实（主 session 2026-09-22 盘点实测）：

- **活路径**：`flow status`（投影查询）、`artifact-event` / `review-manifest`（受保护写通道）、`policy-*`（策略源）；事件投影核心 `agent/workflow/event_log.py` 被 `check_openspec_artifacts.py` 使用。
- **死路径**：`discover` / `current` / `validate` / `spawn`（4 legacy 子命令）、`flow approve` / `advance` / `block` / `confirm`（gate 家族）、`check_phase_done.py`、`doc_artifact_protocol*.py`、`dispatcher.py`、`role_registry.py`。
- **边界约束**：`event_log.py`（活）从 `state_machine.py` 导入 `StateMachineError` / `compute_next_hints` / `validate_transition` → **`state_machine.py` 不能整删**，须按符号切分。

## Goals / Non-Goals

**Goals**

- 死路径清零：CLI 子命令、实现文件、测试、文档规则、guard 白名单同步收口。
- `handoff.json` 三层耦合全消（#228）。
- 活路径零回归（`flow status` / 写通道 / 投影）。

**Non-Goals**

- 不动 `event_log.py`、`flow status`、受保护写通道、`check_openspec_artifacts.py` 的活逻辑。
- 不新增能力（`discover` 的 `path`/`next_action` 输出迁移记为可选 follow-up）。

## Decisions

### D1: 删除面清单（实测调用方为零）

| 目标 | 证据 |
|------|------|
| `workflow_state.py`：`discover` / `current` / `validate` / `spawn` | 无生产调用方；`discover` 输出的 `approve_command`/`spawn_command` 是悬空指针 |
| `workflow_state.py`：`flow approve` / `advance` / `block` / `confirm` | 无生产调用方；`flow approve` 在当代 change 实测必报错；三个 `awaiting_*` 仅由 `flow block` 自写 |
| `scripts/check_phase_done.py`（591 行） | 唯一调用方是 `flow approve`；CI 无引用 |
| `agent/workflow/doc_artifact_protocol.py` + `doc_artifact_protocol_openspec.py`（845 行） | 唯一调用方是 `check_phase_done`；#228 层 2 的唯一来源 |
| `agent/workflow/dispatcher.py`（243 行） | 只有测试 |
| `agent/workflow/role_registry.py`（154 行） | 只有测试（`dispatcher` 消费） |

**保留**：`flow status`、`artifact-event`、`review-manifest`、`policy-show/validate/set`、`resume-audit`。

### D2: `flow/` 声明式引擎的存废（**待 grill 裁定**）

`flow/statechart.json` 声明 30 个状态（`wayfinding.*` → `closing.*`），`flow/engine.py`（stdlib 薄引擎）与之 parity。实测：

- `flow/engine.py` 的**唯一消费者是测试**（`tests/test_declarative_flow_engine.py`）；
- 但该测试是 **parity 测试**：`test_declarative_flow_engine.py:30` 从 `agent.workflow.state_machine` 导入 `validate_transition` 做交叉校验，断言「statechart 声明的合法转移」与「Python `validate_transition`」等价；
- `state_machine.py` 的 `validate_transition` 是**活符号**（`event_log.py` 依赖）。

**张力**：若删 `flow/` 引擎，则删掉一条**已被 CI 强制**的 parity 链（statechart ↔ `validate_transition`）；若保留，则保留一套描述四阶段状态的声明。三种可能：
- (a) 全删 `flow/`（`engine.py` + `statechart.json` + 测试）——简单，但失去 parity 保障，且 `validate_transition` 若无其他消费者是否也可删需连带判断；
- (b) 保留引擎，仅删四阶段专属状态——但 engine 的用途就是描述这套状态，形同虚设；
- (c) 保留现状不动——但 `statechart.json` 描述的是已停用流程，属"文档与事实不符"的同类问题。

> **grill 必答**：裁定 (a)/(b)/(c)，并给出 `validate_transition` 的存废判断（它被活 `event_log.py` 依赖，删引擎不等于能删它）。

### D3: benchmark 任务 `asterwynd-b03-awaiting-grill-state` 的处置（**待 grill 裁定**）

`benchmarks/tasks/asterwynd-b03-awaiting-grill-state/task.json`：

- `track: B`、`difficulty: hard`、`scenario: refactor`；
- `base_commit: 597d121`（master 祖先，距 HEAD 213 提交）；
- `test_command` 指向 `tests/test_declarative_flow_engine.py::TestE2eDemoIntegration::test_awaiting_grill_confirmation_wired_end_to_end` ——**该函数现已不存在**（0 命中）。

即该任务在**本次删除之前就已失效**（其目标测试早已移除）。

> **grill 必答**：该任务应 (a) 随子系统删除（并核算任务集数量/覆盖矩阵影响）、(b) 改写指向替代测试、还是 (c) 标记作废但保留文件。注意 B-track 任务数是 `docs/openspec-change-backlog.md` 与评测叙事引用过的数字。

### D4: `workflow_methods.json` 的 phase/sub_state 段（**待 grill 确认**）

实测：`review_protocol` 节与 `reviewing_impl.review_dimensions` **无代码读者**（唯一读取点 `_method_review_dims` 只被 `_build_path` 与 `discover` 调，均在删除面内）。`/review-loop` 命令是**在文档里手抄**了那 8 条维度，非运行时读取。

但有两个显式约束需要一并处理：
- `AGENTS.md:213` 明写「`workflow_methods.json`…**不删 phase/sub_state 段**」；
- `tests/test_declarative_flow_engine.py:352-373` 有兼容测试**断言这些段必须存在**。

> **grill 确认**：删 phase 段（并同步改 `AGENTS.md` 规则 + 兼容测试）vs 保留（作为历史文档）。倾向删除（无读者 + 与"退役"目标一致），但需确认 `AGENTS.md` 那条规则的**原始意图**是否还有别的约束对象。

### D5: `state_machine.py` 的符号级切分（**边界，必须精确**）

`state_machine.py`（459 行）不可整删。按符号分：

| 符号 | 处置 | 依据 |
|------|------|------|
| `StateMachineError` | **保留** | `event_log.py:9-13` 导入 |
| `validate_transition` | **保留** | `event_log.py` 导入；且 `flow/` parity 测试对照它（见 D2） |
| `compute_next_hints` | **保留** | `event_log.py` 导入 |
| `init_handoff_json` / `load_handoff_json` / `save_handoff_json` | **评估** | `init_handoff_json` 被两条测试用（`test_workflow_state_cli` / `test_workflow_protected_write_channel`）；`save_handoff_json` 被 `dispatcher` 测试用（随 dispatcher 删） |
| `_validate_handoff_json_structure` / `apply_transition` / `enter_blocked` / `resolve_blocked` | **待评** | 服务 gate 家族，疑似可删 |
| `get_recommended_role` / `RoleAgentType` | **评估** | `role_registry` 删除后是否还有消费者 |

> **grill 必答**：给出逐符号的保留/删除清单，特别是 `init_handoff_json`（两条活测试依赖它造 gen-1 种子）——删它会连带改那两条测试的构造方式。

### D6: `handoff.json` 三层解耦的落地（#228）

- 层 1：`_refresh_workflow_state`（`workflow_state.py`）不再映射写 `handoff.json`。**前置**：gate 家族删除后，`check_phase_done` / `doc_artifact_protocol` 的 `FileRequirement(handoff.json)` 消失，无人再要求该文件。
- 层 2：随 `check_phase_done` / `doc_artifact_protocol*` 删除**自然消失**（它们是该耦合的唯一来源）。
- 层 3：`handoff.json` / `workflow-state.json` 落 `.gitignore`。

> **grill 确认**：层 1 改动后，`test_workflow_protected_write_channel.py` 的冷状态断言（"调用前断言无 `handoff.json`"）与 `test_openspec_artifact_checker.py` 的"`flow status` 会同步映射写 `handoff.json`"用例会失效，需同步改写——确认改法。

### D7: guard 白名单与 flow-policy 同步

`scripts/flow-policy.json` 的写通道豁免含 `flow (status|confirm|approve|block|advance)`（`workflow_guard.py:271` 同源）。子命令删除后须收窄为 `flow status`。

**约束**：`flow-policy.json` 是受保护路径（`governance=cli_written`），只能用 `python scripts/workflow_state.py policy-set` 修改，不能手改。

### D8: spec delta 面

`dev-workflow-state-machine/spec.md`（756 行、22 条 Requirement）中，四阶段专属的约 12 条需 REMOVED 或 MODIFIED：

- 移除候选：`四阶段生命周期` / `Phase 内部 sub_state 定义` / `Human review gate` / `Agent 间 handoff` / `handoff.json schema` / `合法流转表` / `流程状态机声明化` / `状态机声明与执行方法分工` / `角色 Agent 类型` / `单 Agent 全流程兼容` / `路由配置` / `阻塞状态`。
- 保留并可能 MODIFIED：`工作流事件日志与 handoff.json projection`（去 handoff 映射）/ `Protected artifact 变更解释` / `Review evidence manifest` / `Workflow 总开关` / `flow 命令与受保护路径`（收窄子命令列表）/ `开发流程精简为 OpenSpec 主干` / `开发流程策略单一源` / `guard 写操作门禁顺序` / `内容门槛阶段感知` / `阶段执行者 agent schema 定义`（评估）。

按 #199/#232 教训：`openspec archive` 是**整段替换 Requirement**，REMOVED 段必须列全、MODIFIED 段必须给变更后完整正文。

> **grill 必答**：逐条给出 REMOVED / MODIFIED / 保留 的清单与理由，特别是 `Workflow 总开关`（它引用了 `discover`）与 `阶段执行者 agent schema 定义`（`role_registry` 删除后是否还有对象）。

## Pre-Implementation Review

架构级 change（删 ~1800 行实现 + ~850 行测试 + 动受保护 spec 与 AGENTS.md 显式规则 + 可能作废 benchmark 任务）。进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

**本 change 的 grill 负担显著高于前几个**：D2/D3/D4/D5/D6/D8 六项待裁定，其中 D2（parity 链）与 D5（符号级切分）是本 change 最容易出错的边界。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 误删活符号（`state_machine.py` 边界） | D5 逐符号清单 + 保留 `event_log.py` 的三个导入；`flow status` / 写通道回归测试 |
| 删除后 CLI 静默成功（比"命令消失"更坏） | 新增负向回归：已删子命令 → 明确错误退出 |
| 受保护 spec 漏改 | D8 逐条清单 + `openspec archive` 段替换前核对 Requirement 数 |
| guard 白名单未同步 → 合法调用被拦 | D7 用 `policy-set` CLI 改，跑 `test_workflow_guard.py` |
| benchmark 任务数字漂移未记录 | D3 裁定后核算任务集数量影响并记入 change 文档 |
| `handoff.json` 层 1 改动打红既有冷状态测试 | D6 同步改写，且**不得**弱化"冷状态"判别力（#199 教训） |
| AGENTS.md 显式规则被违反 | D4 同步改规则文本，不悄悄绕过 |

## Testing Strategy

- **删除**：`test_check_phase_done.py`(487) / `test_dispatcher.py`(254) / `test_role_registry.py`(112) 整删；`test_workflow_state_cli.py`（18 条中涉及 legacy 的部分）与 `test_declarative_flow_engine.py`（视 D2 裁定）改写。
- **新增负向回归**：每个已删子命令调用 → argparse 未知子命令错误、非零退出、不产生副作用。
- **活路径回归**：`flow status` / `artifact-event` / `review-manifest` / `policy-*`；`test_workflow_protected_write_channel.py`(14)、`test_openspec_artifact_checker.py`、`test_flow_policy.py`、`test_workflow_guard.py`。
- **`handoff.json` 解耦断言**：`flow status` 后 change 目录**无** `handoff.json`（D6 层 1 判别性）。
- 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`。

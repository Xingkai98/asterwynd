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
- `test_command` 指向 `tests/test_declarative_flow_engine.py::TestE2eDemoIntegration::test_awaiting_grill_confirmation_wired_end_to_end`。

**⚠ 本节原前提已被 grill 实测推翻（2026-09-22）**：原文称「该函数现已不存在（0 命中）→ 该任务在本次删除之前就已失效」，**这是错的**。该函数由**该任务自己的 `test.patch` 新增**（`test.patch` 内 `+    def test_awaiting_...`）——SWE-bench 式任务的定义就是「`test.patch` 在 `base_commit` 上先失败、`gold.patch` 后通过」，故它在 HEAD 0 命中是**设计使然**。grill 已在 `597d121` 上实跑完整生命周期：`test.patch` → 1 failed（AssertionError）→ `+gold.patch` → 31 passed，且两个 patch 均能干净 `git apply --check`。

**修正后的删除理由**：该任务的目标能力面（statechart 新增 awaiting 态 + 引擎驱动 flow 生命周期 + `flow block`/`flow confirm` 恢复默认值表）**正是本 change 要退役的对象**；任务本身仍可自洽复现，但退役后**已无教学/评测意义**。

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

### D7: guard 白名单同步（**机制已由 grill 更正**）

**⚠ 原文机制描述错误**：原文称白名单在 `scripts/flow-policy.json`、须用 `policy-set` CLI 收窄。**实际不是**——

- 白名单是 `scripts/workflow_guard.py:266-274` 的 `_is_privileged_cli` **硬编码正则**（`(?:\b|_)flow\s+(?:status|confirm|approve|block|advance)`），实测 `flow-policy.json` 全文**无** `flow`/子命令字样；
- `policy-set` CLI（`workflow_state.py:1238-1285`）只写 `protected_paths` 数组，**改不到该正则**；
- 故 **`flow-policy.json` 本次无需任何改动**，tasks.md 里「用 policy-set 收窄」那条是**错的方向**，须改。

**正确改法**：直接改 `workflow_guard.py` 的正则为 `flow\s+status`（该文件**不在**受保护路径，agent 可直改）+ 改 `tests/test_workflow_guard.py:552-566`（现断言 4 条命令被豁免，收窄后其中 3 条应转为「拒绝豁免」断言）。

### D8: spec delta 面

`dev-workflow-state-machine/spec.md`（756 行、22 条 Requirement）中，四阶段专属的约 12 条需 REMOVED 或 MODIFIED：

- 移除候选：`四阶段生命周期` / `Phase 内部 sub_state 定义` / `Human review gate` / `Agent 间 handoff` / `handoff.json schema` / `合法流转表` / `流程状态机声明化` / `状态机声明与执行方法分工` / `角色 Agent 类型` / `单 Agent 全流程兼容` / `路由配置` / `阻塞状态`。
- 保留并可能 MODIFIED：`工作流事件日志与 handoff.json projection`（去 handoff 映射）/ `Protected artifact 变更解释` / `Review evidence manifest` / `Workflow 总开关` / `flow 命令与受保护路径`（收窄子命令列表）/ `开发流程精简为 OpenSpec 主干` / `开发流程策略单一源` / `guard 写操作门禁顺序` / `内容门槛阶段感知` / `阶段执行者 agent schema 定义`（评估）。

按 #199/#232 教训：`openspec archive` 是**整段替换 Requirement**，REMOVED 段必须列全、MODIFIED 段必须给变更后完整正文。

> **grill 必答**：逐条给出 REMOVED / MODIFIED / 保留 的清单与理由，特别是 `Workflow 总开关`（它引用了 `discover`）与 `阶段执行者 agent schema 定义`（`role_registry` 删除后是否还有对象）。

### D9: 退役的净损失——完成度门禁与 TODO 残留扫描（关联 issue #235）

`check_phase_done.py` 承担两项在新机制中**没有等价替代**的职责：

1. **「100% 要求全勾」**：其 docstring 与 `workflow_methods.json` 均记载「Checkbox 只是
   Agent 的『声称做完』声明（由 `check_phase_done` 100% 要求）」。删除后完成度检查只剩
   `check_openspec_artifacts` 里由 `_tasks_all_complete` 驱动的 `requires_building_review`
   ——后者是「**全勾才查**」的触发器（不勾即绕开），比「100% 要求」**薄**。
2. **TODO 残留扫描**：`_find_todo_residuals` / `_load_known_debt`（对 `docs/known-debt.md`
   比对）。`check_openspec_artifacts` 只查 `SELF_ADMITTED_INCOMPLETE_PHRASES`，是其**子集**。

**这是能力面净损失，不是替代**，须显式记录而非静默消失。且本退役**放大**了 issue #235
的缺口：退役前是「旧机制兜底 + 新机制更薄」，退役后是「**只剩薄的那层**」。
（主 session 已在 #235 加评论交叉引用本退役。）

处置待 grill 裁定：
- 是否把这两项**迁入** `check_openspec_artifacts`（重建）？
- 还是**显式接受其消失**，在 `docs/known-debt.md` 记为已知边界？

> **grill 必答**：本退役应连带补上这两项，还是显式接受其消失并记债？
> 注意与 D1「零生产调用方」的张力：`check_phase_done` 确实无调用方，
> 但它承载的**能力**是否也该无替代地消失，是另一个问题。

## Grill 裁定整合（2026-09-22，run id `grill-zero-memory`）

零记忆独立 subagent 逐项实测复核，完整报告见 `reviews/grill-design.md`。核心裁定与**对本文档的更正**：

### 对 D1 删除面的补充（原文漏列）

| 补充目标 | 依据 |
|---|---|
| **`agent/workflow/__init__.py` 的导出行**（:1 `dispatcher`、:2 `manager`、:26-38 `role_registry`/`routing` 死亡部分、:45-52 `state_machine` 死亡部分、`__all__`） | **【高】它是包的 `__init__`**：checker 的 `from agent.workflow.event_log import verify_projection`（`check_openspec_artifacts.py:959`）与 guard 的 `from agent.workflow.event_log import ...`（`workflow_guard.py:552`）**都会先执行它**。删文件不删导出 = `ModuleNotFoundError`，直接打崩 CI 与 PreToolUse 门禁 |
| **`agent/workflow/handoff_note.py`（103 行）** | 全仓 import **0 处**；属四阶段 handoff 机制（与 `Agent 间 handoff` Requirement 同源）。不删则留下新的一文件死代码 |
| **`agent/workflow/manager.py`（372 行）** | `WorkflowManager` 的生产消费者只有 `dispatcher.py`（同删）+ `workflow_state.py:45` 的**死导入**；活消费者全在测试里（`test_workflow_guard.py:32` 等） |
| **`WORKTREE_REQUIRED_PHASES` 导入**（`workflow_state.py:42`） | 唯一使用点 :416 在 `_cmd_discover_json`（删除面内）→ 成为未用导入 |

### D2 裁定：`flow/` 全删 (a)

删 `flow/engine.py` + `flow/statechart.json` + `tests/test_declarative_flow_engine.py`。`validate_transition` **保留**（活：`event_log.py:12→:540 _validate_transition_dict`），其**传递闭包**（`get_legal_targets` / `get_recommended_role` / `_is_gate` / `WITHIN_PHASE_ADJACENT` / `CROSS_PHASE_FORWARD` / `_phase_index` / `_validate_sub_state`）一并保留。
**关键认识**：删 statechart 失去的只是「声明与 Python 常量必须同步」这一条**冗余声明约束**，**不是**四阶段模型本身——四阶段转移表全量留在 `state_machine.py`，由 `tests/agent/workflow/test_state_machine.py`（459 行符号级单测）继续 pin 住。

### D4 裁定：删 phase 段（并连带清理其读者）

`AGENTS.md:213` 那条规则的**原始意图**（`declarative-flow-engine` grill Q3，2026-08-16）就是「`_method_hint`/`_build_path` 直接索引会 KeyError」——而这两个函数正在删除面内，意图已自然兑现。
**连带删除**：`_method_hint` / `_method_review_dims` / `_ticket_tracker_label` / `_build_path` / `_next_action` + 3 条相关活测试。
**必须保留**：`workflow` 节（`is_workflow_enabled`）、`doc_artifact` 节（`_resolve_changes_root`、guard 的 `change_dir_template`）、`ticket_tracker` 视 `_ticket_tracker_label` 去留而定。

### D5 更正：`get_recommended_role` / `get_legal_targets` 必须**保留**

原文标为「评估」是**错的**。活链：`event_log.py:286` → `compute_next_hints:449-453` → `get_recommended_role` + `get_legal_targets` → `_is_gate` + `WITHIN_PHASE_ADJACENT`/`CROSS_PHASE_FORWARD`。该链在当前仓库**实测 0 触发**（全仓无 `transition_applied` 事件），但 checker 的 `_check_archived_projectable`（`check_openspec_artifacts.py:1057`）对**每个**归档 change 跑投影——任何 gen-1 change 一旦含该事件即 AttributeError。**这是「0 命中 ≠ 死代码」的典型陷阱。** 逐符号完整表见 `reviews/grill-design.md`。

### D6 限定：层 1 只去 **gen-2 映射**

改点是 `_refresh_workflow_state`（`workflow_state.py:977-992`）尾部 6 行。**不要动** `_flow_refresh_after_event` 的 **gen-1 分支**（:968-972）——那写的是 gen-1 的**唯一**投影，不是「映射写」。
`_require_change_target` 的 `or handoff.json` 分支**保留**（零成本保护历史 gen-1 可写性，且有活测试依赖）；仅把 docstring 里「`cmd_spawn` 生成的子 change」的举例改为「历史 spawn 子 change」。

### D8 裁定：delta **不能按现状归档**

10 条 Requirement 名与正式 spec **逐字全匹配**（「阻塞状态」本次**正确**，历史误写未复现）。但：

1. **MODIFIED 段静默删除 22 条仍活 Scenario**（详见 `reviews/grill-design.md` 的逐 Scenario 比对）——`openspec archive` 是整段替换，未列出的 Scenario 会被删掉，而活测试仍在断言它们；
2. **漏列 5 条应 REMOVED**：`Agent 间 handoff` / `handoff.json schema` / `合法流转表` / `流程状态机声明化` / `状态机声明与执行方法分工`；
3. **漏列 1 条 MODIFIED**：`guard 写操作门禁顺序与路径归一化`（其正文含子命令白名单，须随 D7 收窄）；
4. `阻塞状态` 整条 REMOVED 前**必须先迁出 2 条活 Scenario**（`checker 派生物一致性`、`guard 读投影执法`——后者有 10 条活测试专测）；
5. `阶段执行者 agent schema 定义` 裁定**保留不动**：它挂在 `flow-policy.json` 的 `phases.<phase>.agent` schema，不挂 `role_registry.py`。

### D9 裁定：(b) 显式接受 + 记 `docs/known-debt.md`

两项「无等价替代」断言**实测均成立**（100% 全勾的实现实为 `doc_artifact_protocol_openspec.py:123-125` + `:356-375`，归因较原文略修正但删除面不变）。**反对迁入 checker**：`_find_todo_residuals` 依赖 `git diff origin/master`，而 checker 走 `--base-ref`（CI 传 PR base sha），直接搬运会产生语义漂移——正确移植属**新增能力面**而非退役配套。

### 新增风险（grill 发现，原文未列）

| 风险 | 缓解 |
|---|---|
| **【高】awaiting 死锁面**：`flow block`/`flow confirm` 删除后 `blocked_entered`/`blocked_resolved` **无任何写入者**，而 guard 的 awaiting 硬拦截保留且不可经 Bash 绕过 | 合入前检查全仓 awaiting 状态（grill 实测当前为 **0**），并在 change 文档声明「awaiting 执法保留但无 CLI 解除通道」；或保留 `flow confirm` 作为纯恢复命令 |
| **【中】SPAWN 悬空指针对称问题**：`cmd_spawn` 删除后 `_require_change_target` docstring 仍以「`cmd_spawn` 生成的子 change」举例 | 改举例措辞（见 D6 限定） |
| **【低】`docs/benchmark-run-protocol.md:22`** 声明「B 轨 12–16」，删 b03 后为 **11**（低于下界） | 属**协议目标口径**非现状，**不必改**，但在 change 文档记录该偏差 |
| **【低】`docs/benchmark-plan.md:22`「27 个本地任务」** 是**既有漂移**（现状 34） | 与本次数字更新**分开**记录，不同一改动混改 |
| **【中】`test_workflow_guard.py:32` `_seed_active_change` 依赖 `WorkflowManager(...).init()`** | 删 `manager.py` 会打断**活路径回归核心测试**；按 `_seed_gen1_change` 的等价字面量改写。原文 tasks.md **未列**此项 |

### 任务集数量影响（D3，grill 实测）

本地任务 34 → **33**（A 轨 22 不变，B 轨 12 → **11**）；Verified 38 不变；总数 72 → **71**；`benchmarks/tasks/manifest.json` 的 `coverage` 段 34 → 33 条。

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
| **退役移除 `check_phase_done` 的 100% 全勾要求与 TODO 残留扫描，且无等价替代（放大 issue #235）** | D9 显式记录：either 迁入 `check_openspec_artifacts`，or 记入 `docs/known-debt.md` 为已知边界——不得静默消失 |

## Testing Strategy

- **删除**：`test_check_phase_done.py`(487) / `test_dispatcher.py`(254) / `test_role_registry.py`(112) 整删；`test_workflow_state_cli.py`（18 条中涉及 legacy 的部分）与 `test_declarative_flow_engine.py`（视 D2 裁定）改写。
- **新增负向回归**：每个已删子命令调用 → argparse 未知子命令错误、非零退出、不产生副作用。
- **活路径回归**：`flow status` / `artifact-event` / `review-manifest` / `policy-*`；`test_workflow_protected_write_channel.py`(14)、`test_openspec_artifact_checker.py`、`test_flow_policy.py`、`test_workflow_guard.py`。
- **`handoff.json` 解耦断言**：`flow status` 后 change 目录**无** `handoff.json`（D6 层 1 判别性）。
- 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`。

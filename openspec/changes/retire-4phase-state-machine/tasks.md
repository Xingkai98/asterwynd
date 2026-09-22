# Tasks — retire-4phase-state-machine

## 0. 设计追问（实现前门禁）

- [ ] 跑 `batch-grill-me`（或等价设计追问，`/grill`；独立零记忆 subagent）审视 design.md D1–D8，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）
- [ ] **grill 必答项**：D2（`flow/` 引擎存废 + `validate_transition` 存废）、D3（benchmark 任务处置 + 任务集数量影响）、D4（`workflow_methods.json` phase 段 + AGENTS.md 规则）、D5（`state_machine.py` 逐符号保留/删除清单）、D6（层 1 改动后既有测试改法）、D8（逐 Requirement REMOVED/MODIFIED 清单）

## 实现

- [ ] `scripts/workflow_state.py`：删 4 个 legacy 子命令（`discover` / `current` / `validate` / `spawn`）及其 parser 注册、`_cmd_discover_*`、模块 docstring 引用
- [ ] `scripts/workflow_state.py`：删 4 个 gate 家族子命令（`flow approve` / `advance` / `block` / `confirm`），保留 `flow status`
- [ ] 删除 `scripts/check_phase_done.py`
- [ ] 删除 `agent/workflow/doc_artifact_protocol.py` + `doc_artifact_protocol_openspec.py`
- [ ] 删除 `agent/workflow/dispatcher.py` + `role_registry.py` + `manager.py`（`WorkflowManager` 生产消费者仅 `dispatcher` + `workflow_state.py:45` 死导入）+ `handoff_note.py`（103 行，全仓 0 import，grill 补列）
- [ ] **`agent/workflow/__init__.py`：删 `dispatcher`/`manager`/`role_registry`/死亡 `routing`·`state_machine` 导出与 `__all__` 对应项**（【高】包 `__init__` 先于子模块执行，漏改直接打崩 checker/guard）
- [ ] `agent/workflow/state_machine.py`：按 D5 清单逐符号删除（**必须保留** `event_log.py` 导入的 `StateMachineError` / `compute_next_hints` / `validate_transition`，以及其传递闭包 `get_legal_targets` / `get_recommended_role` / `_is_gate` / `WITHIN_PHASE_ADJACENT` / `CROSS_PHASE_FORWARD` / `_phase_index` / `_validate_sub_state`——grill 更正）
- [ ] `workflow_state.py`：`_refresh_workflow_state` 不再映射写 `handoff.json`（D6 层 1，**仅 gen-2 映射**；不得动 `_flow_refresh_after_event` 的 gen-1 分支）
- [ ] `.gitignore`：加 `handoff.json` / `workflow-state.json`（注意 5 个归档 `handoff.json` 已被 git 跟踪，glob 需排除归档面）
- [ ] **`scripts/workflow_guard.py:266-274`：`_is_privileged_cli` 正则收窄为 `flow\s+status`**（D7 更正——白名单在 guard 硬编码正则里，**不在** `flow-policy.json`；`policy-set` 改不到它，`flow-policy.json` 本次无需改动）+ 改 `tests/test_workflow_guard.py:552-566`
- [ ] D2 裁定：全删 `flow/`（`engine.py` + `statechart.json` + `tests/test_declarative_flow_engine.py`）
- [ ] D4 裁定：删 `workflow_methods.json` phase/sub_state 段 + 连带删 `_method_hint`/`_method_review_dims`/`_ticket_tracker_label`/`_build_path`/`_next_action` + 3 条相关活测试（**保留** `workflow`/`doc_artifact` 节）
- [ ] D3 裁定：删 `benchmarks/tasks/asterwynd-b03-awaiting-grill-state/` + 同步 `benchmarks/tasks/manifest.json` 的 `coverage` 段（34→33 条）+ 核对叙事数字（本地 34→33、B 轨 12→11、总数 72→71）
- [ ] 合入前检查全仓 awaiting 状态（grill 实测为 0；若有 in-flight change 卡在 awaiting，删除 `flow confirm` 后将无法解除）

## 测试

- [ ] 删除 `tests/test_check_phase_done.py` / `tests/agent/workflow/test_dispatcher.py` / `tests/agent/workflow/test_role_registry.py` / `tests/test_declarative_flow_engine.py`（随 D2）/ `tests/agent/workflow/test_manager.py` + `test_routing.py`（视 Q3 裁定）
- [ ] **改写 `tests/test_workflow_guard.py:32` `_seed_active_change`**（依赖 `WorkflowManager(...).init()`，删 `manager.py` 后断裂——活路径回归核心测试，grill 补列）
- [ ] 改写 `tests/test_workflow_state_cli.py`（删 legacy 用例，保留活子命令用例；`init_handoff_json` 种子改等价字面量，见 grill 报告）
- [ ] **新增负向回归**：每个已删子命令 → argparse 未知子命令错误、非零退出、无副作用（不静默成功）
- [ ] **`handoff.json` 解耦判别性断言**：`flow status` 后 change 目录**无** `handoff.json`（D6 层 1，去掉该改动必红）
- [ ] 改写 `tests/test_workflow_protected_write_channel.py` 与 `tests/test_openspec_artifact_checker.py` 中依赖「`flow status` 映射写 handoff.json」的断言（**不得弱化冷状态判别力**，#199 教训）
- [ ] 活路径回归：`flow status` / `artifact-event` / `review-manifest` / `policy-*`；`test_flow_policy.py` / `test_workflow_guard.py` 全绿
- [ ] 变异验证：恢复任一已删子命令 → 负向用例红；恢复 handoff 映射写 → 解耦用例红

## 文档

- [ ] `AGENTS.md`：删 flow 家族命令段、改 `:213` 的「不删 phase/sub_state 段」规则（视 D4）
- [ ] `docs/requirements-process.md`：改「四阶段状态机驱动」的过时描述
- [ ] `docs/development-guide.md`：同步 flow 命令清单（grill 实测该文件**无** flow 命令清单，AGENTS.md:190-201 才是权威处——按实测更正，勿凭 design 原文盲改）
- [ ] spec delta（`dev-workflow-state-machine`）：REMOVED **12** 条（原 7 + 漏列 5：`Agent 间 handoff`/`handoff.json schema`/`合法流转表`/`流程状态机声明化`/`状态机声明与执行方法分工`）+ MODIFIED **4** 条（原 3 + 漏列 `guard 写操作门禁顺序与路径归一化`，须随 D7 收窄白名单），**全部补为变更后完整正文**并保留 22 条仍活 Scenario（`openspec archive` 为整段替换）
- [ ] `阻塞状态` REMOVED 前**先迁出 2 条活 Scenario**（`checker 派生物一致性`、`guard 读投影执法`——后者 10 条活测试专测）到保留的 Requirement
- [ ] `docs/known-debt.md`：移除 #227 / #228 条目（本 change 收口），配 `protected_artifact_explained` 事件
- [ ] **D9 净损失处置**：`docs/known-debt.md` 记录本退役的净损失（`check_phase_done` 的 100% 全勾要求变薄 + TODO 残留扫描消失，放大 issue #235），或按 grill 裁定把这两项迁入 `check_openspec_artifacts`——二者择一，不得静默消失
- [ ] `docs/openspec-change-backlog.md`：登记本 change + 收尾移除（`backlog_updated` 事件 ×2）
- [ ] **当前规格同步**：delta 合入 `openspec/specs/dev-workflow-state-machine/spec.md`（`current_spec_synced` 事件）

## 审阅闭环

- [ ] `/review-loop` 独立零记忆 subagent 审阅 → PASS 或 3 轮封顶
- [ ] 生成 review manifest（绑归档后最终 head，D3 纪律）

## 验证

- [ ] **benchmark smoke**：本 change 删除 `dispatcher`/`role_registry` 等与 benchmark harness 相邻的模块，跑 `uv run asterwynd benchmark benchmarks/tasks/gate-smoke --source-repo . --runs-dir /tmp/smoke-retire-4phase` 确认 harness 不因删除而崩（fake agent 回显 stub，验证 CLI/AgentLoop 路径端到端无崩溃，非回归信号）
- [ ] 全量 `uv run pytest -q` 通过
- [ ] OpenSpec strict validate 通过
- [ ] artifact checker + `--check-archived` 通过
- [ ] 端到端：`flow status` 可用、已删子命令报错、`handoff.json` 不再自愈产出
- [ ] 收尾：issue #227 与 #228 添加完成 comment 并关闭（本 change 为两者共同收口）

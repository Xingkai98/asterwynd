# Tasks — retire-4phase-state-machine

## 0. 设计追问（实现前门禁）

- [ ] 跑 `batch-grill-me`（或等价设计追问，`/grill`；独立零记忆 subagent）审视 design.md D1–D8，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）
- [ ] **grill 必答项**：D2（`flow/` 引擎存废 + `validate_transition` 存废）、D3（benchmark 任务处置 + 任务集数量影响）、D4（`workflow_methods.json` phase 段 + AGENTS.md 规则）、D5（`state_machine.py` 逐符号保留/删除清单）、D6（层 1 改动后既有测试改法）、D8（逐 Requirement REMOVED/MODIFIED 清单）

## 实现

- [ ] `scripts/workflow_state.py`：删 4 个 legacy 子命令（`discover` / `current` / `validate` / `spawn`）及其 parser 注册、`_cmd_discover_*`、模块 docstring 引用
- [ ] `scripts/workflow_state.py`：删 4 个 gate 家族子命令（`flow approve` / `advance` / `block` / `confirm`），保留 `flow status`
- [ ] 删除 `scripts/check_phase_done.py`
- [ ] 删除 `agent/workflow/doc_artifact_protocol.py` + `doc_artifact_protocol_openspec.py`
- [ ] 删除 `agent/workflow/dispatcher.py` + `agent/workflow/role_registry.py`（及 `agent/workflow/__init__.py` 的导出）
- [ ] `agent/workflow/state_machine.py`：按 D5 清单逐符号删除（**必须保留** `event_log.py` 导入的 `StateMachineError` / `compute_next_hints` / `validate_transition`）
- [ ] `workflow_state.py`：`_refresh_workflow_state` 不再映射写 `handoff.json`（D6 层 1）
- [ ] `.gitignore`：加 `handoff.json` / `workflow-state.json`
- [ ] `scripts/flow-policy.json`：用 `policy-set` CLI 收窄 flow 豁免为 `flow status`（D7，**不可手改**）
- [ ] 视 D2 裁定处置 `flow/`（`engine.py` / `statechart.json`）
- [ ] 视 D3 裁定处置 `benchmarks/tasks/asterwynd-b03-awaiting-grill-state/`
- [ ] 视 D4 裁定处置 `workflow_methods.json` phase/sub_state 段

## 测试

- [ ] 删除 `tests/test_check_phase_done.py` / `tests/agent/workflow/test_dispatcher.py` / `tests/agent/workflow/test_role_registry.py`
- [ ] 改写 `tests/test_workflow_state_cli.py`（删 legacy 用例，保留活子命令用例）
- [ ] 视 D2/D4 改写 `tests/test_declarative_flow_engine.py`
- [ ] **新增负向回归**：每个已删子命令 → argparse 未知子命令错误、非零退出、无副作用（不静默成功）
- [ ] **`handoff.json` 解耦判别性断言**：`flow status` 后 change 目录**无** `handoff.json`（D6 层 1，去掉该改动必红）
- [ ] 改写 `tests/test_workflow_protected_write_channel.py` 与 `tests/test_openspec_artifact_checker.py` 中依赖「`flow status` 映射写 handoff.json」的断言（**不得弱化冷状态判别力**，#199 教训）
- [ ] 活路径回归：`flow status` / `artifact-event` / `review-manifest` / `policy-*`；`test_flow_policy.py` / `test_workflow_guard.py` 全绿
- [ ] 变异验证：恢复任一已删子命令 → 负向用例红；恢复 handoff 映射写 → 解耦用例红

## 文档

- [ ] `AGENTS.md`：删 flow 家族命令段、改 `:213` 的「不删 phase/sub_state 段」规则（视 D4）
- [ ] `docs/requirements-process.md`：改「四阶段状态机驱动」的过时描述
- [ ] `docs/development-guide.md`：同步 flow 命令清单
- [ ] spec delta（`dev-workflow-state-machine`）：REMOVED 7 条 + MODIFIED 3 条，**补全为变更后完整正文**（`openspec archive` 为整段替换）
- [ ] `docs/known-debt.md`：移除 #227 / #228 条目（本 change 收口），配 `protected_artifact_explained` 事件
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

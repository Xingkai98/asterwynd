# Tasks — retire-4phase-state-machine

## 0. 设计追问（实现前门禁）

- [x] 跑 `batch-grill-me`（或等价设计追问，`/grill`；独立零记忆 subagent）审视 design.md D1–D8，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）
- [x] **grill 必答项**：D2/D3/D4/D5/D6/D8 + 追加的 D9（去重损失）均已裁定；grill 另推翻三处 design 事实（D7 白名单位置、D3 任务失效前提、D5 闭包符号）并补出三处高危遗漏（`__init__.py` 包导出、`handoff_note.py`、`test_workflow_guard.py:32` 种子）

## 实现

- [x] `scripts/workflow_state.py`：删 4 个 legacy 子命令（`discover` / `current` / `validate` / `spawn`）及其 parser 注册、`_cmd_discover_*`、模块 docstring 引用
- [x] `scripts/workflow_state.py`：删 4 个 gate 家族子命令（`flow approve` / `advance` / `block` / `confirm`），保留 `flow status`
- [x] 删除 `scripts/check_phase_done.py`
- [x] 删除 `agent/workflow/doc_artifact_protocol.py` + `doc_artifact_protocol_openspec.py`
- [x] 删除 `agent/workflow/dispatcher.py` + `role_registry.py` + `manager.py` + `handoff_note.py`
- [x] **`agent/workflow/__init__.py`：去 re-export**（改为包 docstring + 零导出；包 `__init__` 先于子模块执行，残留导出会打崩 checker/guard）
- [x] `agent/workflow/state_machine.py`：按 D5 清单逐符号删除（保留 `StateMachineError` / `compute_next_hints` / `validate_transition` 及其传递闭包）
- [x] `workflow_state.py`：`_refresh_workflow_state` 不再映射写 `handoff.json`（D6 层 1，仅 gen-2；`_flow_refresh_after_event` 的 gen-1 分支未动）
- [x] `.gitignore`：加 `openspec/changes/*/handoff.json` / `openspec/changes/*/workflow-state.json`（单层 glob，归档面保持可跟踪；`git check-ignore` 双向验证）
- [x] **`scripts/workflow_guard.py`：`_is_privileged_cli` 正则收窄为 `flow\s+status`**（D7——白名单在 guard 硬编码正则，`flow-policy.json` 本次零改动）+ 改 `tests/test_workflow_guard.py`
- [x] D2 裁定：全删 `flow/`（`engine.py` + `statechart.json` + `tests/test_declarative_flow_engine.py`）
- [x] D4 裁定：删 `workflow_methods.json` phase/sub_state 段 + 连带删 `_method_hint`/`_method_review_dims`/`_ticket_tracker_label`/`_build_path`/`_next_action`（保留 `workflow`/`doc_artifact`/`ticket_tracker` 节）
- [x] D3 裁定：删 `benchmarks/tasks/asterwynd-b03-awaiting-grill-state/` + `manifest.json` coverage 34→33 + 叙事数字同步（本地 34→33、B 轨 12→11、总数 72→71、task.json 74→73）
- [x] 合入前检查全仓 awaiting 状态（实测为 0）

## 测试

- [x] 删除 `tests/test_check_phase_done.py` / `tests/agent/workflow/test_dispatcher.py` / `tests/agent/workflow/test_role_registry.py` / `tests/test_declarative_flow_engine.py` / `tests/agent/workflow/test_manager.py`（`test_routing.py` 按 Q3 裁定保留——`routing.py` 原样保留，死函数记 issue #239）
- [x] **改写 `tests/test_workflow_guard.py` 的 `_seed_active_change`**（`WorkflowManager` 依赖改为直接落 `change_created` 事件）
- [x] 改写 `tests/test_workflow_state_cli.py`（删 legacy 用例；`init_handoff_json` 种子改等价字面量）
- [x] **新增负向回归**：`TestRemovedSubcommands`——8 个已删子命令 → 未知子命令非零退出 + 无副作用
- [x] **`handoff.json` 解耦判别性断言**：`test_flow_status_self_heal_does_not_write_handoff_json` + 写通道用例的 post-call 断言
- [x] 改写 `tests/test_workflow_protected_write_channel.py`（docstring 第 3 条重写 + post-call 判别断言）与 `tests/test_openspec_artifact_checker.py`（gen-1 种子改字面量；注释订正）
- [x] 活路径回归：`flow status` / `artifact-event` / `review-manifest` / `policy-*`；`test_flow_policy.py` / `test_workflow_guard.py` 全绿
- [x] 变异验证：恢复 `flow approve` 注册 → 负向用例红（实测 2 条）；恢复 handoff 映射写 → 解耦用例红（实测 2 条）；均已还原

## 文档

- [x] `AGENTS.md`：flow 命令段 + 配置架构表 + P4 声明式引擎段 + 「不再需要 discover/advance/approve」表述
- [x] `docs/requirements-process.md`：四阶段描述改为主干流程 + handoff note/`.handoff` 退役 + review manifest 路径订正（原 `.handoff/` 路径是既有错误，实测 manifest 落在 `reviews/`）
- [x] `docs/development-guide.md`：按 grill 实测确认该文件**无** flow 命令清单，无需改动
- [x] spec delta（`dev-workflow-state-machine`）：**REMOVED 11 + MODIFIED 5**（见下）
- [x] `阻塞状态` 的 2 条活 Scenario（`checker 派生物一致性`、`guard 读投影执法`）**保留**在该 Requirement 内（改为 MODIFIED 而非 REMOVED，与 grill 建议的「迁出到别处」等价但更内聚）
- [x] `docs/known-debt.md`：移除 #227 / #228 条目（已收口），配 `protected_artifact_explained` 事件
- [x] **D9 净损失处置**：`docs/known-debt.md` 记录本退役的净损失（100% 全勾变薄 + TODO 残留扫描消失，关联 issue #235）+ awaiting 残留面
- [x] `docs/openspec-change-backlog.md`：收尾移除（`backlog_updated` 事件）
- [x] **当前规格同步**：delta 合入 `openspec/specs/`（`current_spec_synced` 事件）

> **delta 计数与 grill 建议的差异**：grill 建议 REMOVED 12 + MODIFIED 4，实际落地 **REMOVED 11 + MODIFIED 5**，差在 `阻塞状态`——grill 建议把它整条 REMOVED 并把 2 条活 Scenario 迁到别的 Requirement；实际改为保留该 Requirement 为 MODIFIED（Scenario 内聚在原处）。两者触达的 Requirement 总数同为 16，活 Scenario 均零丢失。

## 审阅闭环

- [x] `/review-loop` 独立零记忆 subagent 审阅 → 第 3 轮封顶轮 **PASS**（R1 3 条、R2 1 条 Issue 全部收敛；四类高危经 3 轮独立实测排除）
- [x] 生成 review manifest（**在 tasks.md 最终化/归档之后**，绑归档后最终 head）

## 验证

- [x] **benchmark smoke**：`uv run asterwynd benchmark benchmarks/tasks/gate-smoke --source-repo . --runs-dir /tmp/smoke-retire` → 2 tasks / passed 2
- [x] 全量 `uv run pytest -q` → 4 failed / 2916 passed（4 条为既有环境失败：memory 2 + docker 2，在 base `ac0ccd7` 上同样失败）
- [x] OpenSpec strict validate 通过（30 passed）
- [x] artifact checker + `--check-archived` 通过
- [x] 端到端：`flow status` 可用、8 个已删子命令均 exit 2、`handoff.json` 不再自愈产出
- [x] 收尾：issue #227 与 #228 添加完成 comment 并关闭（本 change 为两者共同收口）

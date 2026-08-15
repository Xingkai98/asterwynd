# Tasks: flow-event-projection

## 1. 规格

- [x] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #136，父 map #121）。
- [x] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D9）、Risks、Testing Strategy。
- [x] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响面。
- [x] 1.4 维护 `## Reference Implementation Research`（status: disabled + 上游决策锁定理由 + research_tier: exempt）。
- [x] 1.5 开发前使用独立 subagent 等价设计追问（grill）审视 `design.md`，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），逐项确认实现细节；停轮获得用户对 `## Open Questions` 的确认并记录到 `## User Confirmation`。
- [x] 1.6 更新 `docs/openspec-change-backlog.md`，把 flow-event-projection 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [x] 1.7 当前规格同步：把 dev-workflow-state-machine spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件（seq 3 current_spec_synced）。

## 2. 测试

- [x] 2.1 投影派生测试：老世代（initialized+handoff.json）与当代（change_created 开头）各自投影正确；awaiting 态派生（blocked.awaiting_* 建模）；容忍异构（无 change_created 首事件）。
- [x] 2.2 两代 parity 测试：老世代 replay 结果与修复前一致（handoff 形状 golden 断言）；当代事件 replay 不抛错。
- [x] 2.3 `flow status` 测试：单 change 与 `--all` 输出；state/milestones/source_event_seq 字段；stale 提示 + 自愈重建；归档只读。
- [x] 2.4 `flow confirm` / `flow approve` / `flow block` / `flow advance` 测试：写 `blocked_resolved` / transition 事件（复用 v1 blocked 类型）；写路径唯一化（非法写者被 guard 拦）。
- [x] 2.5 guard 兜底测试：投影正常 / 缺失 / 损坏 / stale 四种形态；awaiting 未确认 exit 2；fail-closed（不因投影问题放行）；只读不写盘。
- [x] 2.6 checker 派生物一致性测试：磁盘投影 == replay 通过；人为篡改投影 → 报错；归档 change 只验可投影（Q5）。
- [x] 2.7 废旧命令处理测试（Q2）：advance/approve 删除，discover approve_command 迁移到 flow approve。
- [x] 2.8 回归：现有 guard/checker/policy 测试全绿（全量 pytest 1928 passed；1 个 pre-existing tree-sitter 环境失败与本次无关）。

## 3. 实现

- [x] 3.1 `agent/workflow/event_log.py`：统一投影入口 `project_workflow_state`（两代兼容，change_created seed + milestones 推进器 + 容忍无 seed）；`verify_handoff_projection` 扩为 `verify_projection`；复用 v1 blocked 事件类型，不新增类型。
- [x] 3.2 `scripts/workflow_state.py`：`flow status/confirm/approve/block/advance` 命令组；投影生成（派生 + 落盘 workflow-state.json + source_event_seq + 自愈重建）；删除废旧 advance/approve（Q2）；discover approve_command 迁移；`_all_change_ids` 扩展覆盖当代 change。
- [x] 3.3 `scripts/workflow_guard.py`：读投影判断 awaiting + last_seq 新鲜度 + 缺失/stale/corrupt fail-closed（提示先跑 flow status 重建）；`_is_privileged_cli` 豁免正则扩展 `flow (status|confirm|approve|block|advance)`（防 hijack 保持）。
- [x] 3.4 `scripts/check_openspec_artifacts.py`：tasks 全勾 change 的投影==replay 一致性校验（verify_projection）；`--check-archived` 新增归档可投影校验（结构合法 + 类型可识别，不要求 seed）。
- [x] 3.5 `flow-policy.json`：无需改策略表——`workflow-state.json` + `workflow-events.jsonl` 已由 P0 入受保护清单（governance=cli_written，`flow-policy.json:46-49,70-74` + guard 默认表 `workflow_guard.py:79,84`）；改动会破坏 parity 测试，故只记录该事实。
- [x] 3.6 文档：AGENTS.md（flow 命令说明）、Impact Analysis 回写。
- [x] 3.7 实现中发现的新影响面已回写 Impact Analysis 和本任务清单（gen-2 同步映射写 handoff.json、guard bootstrap 语义、--check-archived 既有 drift）。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试（投影/命令/guard/checker）：166 passed。
- [x] 4.2 运行全量测试 `uv run pytest -q`：1928 passed, 7 skipped；1 个 pre-existing 环境失败（`test_tree_sitter_symbols.py` Java/Kotlin 语法解析，与本次改动无关，见 known-debt 候选）。
- [x] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：30/30 passed。
- [x] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`：passed。
- [x] 4.5 两代兼容人工验证：对归档老 change（gen-1 initialized / gen-2 change_created / gen-0 无 seed）各跑 `flow status` 均不抛错、只读不落盘；当代 change 自愈重建正常。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-flow-event-projection/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次章节。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时，给关联 GitHub issue #136 添加完成说明 comment 并关闭。

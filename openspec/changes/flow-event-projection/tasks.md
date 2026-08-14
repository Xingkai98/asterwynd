# Tasks: flow-event-projection

## 1. 规格

- [x] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #136，父 map #121）。
- [x] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D9）、Risks、Testing Strategy。
- [x] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响面。
- [x] 1.4 维护 `## Reference Implementation Research`（status: disabled + 上游决策锁定理由 + research_tier: exempt）。
- [ ] 1.5 开发前使用独立 subagent 等价设计追问（grill）审视 `design.md`，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），逐项确认实现细节；停轮获得用户对 `## Open Questions` 的确认并记录到 `## User Confirmation`。
- [ ] 1.6 更新 `docs/openspec-change-backlog.md`，把 flow-event-projection 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [ ] 1.7 当前规格同步：把 dev-workflow-state-machine spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。

## 2. 测试

- [ ] 2.1 投影派生测试：老世代（initialized+handoff.json）与当代（change_created 开头）各自投影正确；awaiting 态派生（awaiting_human_review / awaiting_user_confirmation；review_blocked 不入 awaiting 集）；容忍异构（无 change_created 首事件）。
- [ ] 2.2 两代 parity 测试：老世代 replay 结果与修复前一致（golden 断言）；当代事件 replay 不抛错。
- [ ] 2.3 `flow status` 测试：单 change 与 `--all` 输出；state/milestones/source_event_seq 字段；stale 提示。
- [ ] 2.4 `flow confirm` / `flow approve` 测试：写 `blocked_resolved` / transition 事件（复用 v1 blocked 类型）；写路径唯一化（非法写者被 guard 拦）。
- [ ] 2.5 guard 兜底测试：投影正常 / 缺失 / 损坏 / stale 四种形态；awaiting 未确认 exit 2；已确认放行；fail-closed（不因投影问题放行）。
- [ ] 2.6 checker 派生物一致性测试：磁盘投影 == replay 通过；人为篡改投影 → exit 2；归档 change 行为（随 Q5 定）。
- [ ] 2.7 废旧命令处理测试（随 Q2 定）：advance/approve 删除或兼容提示的行为。
- [ ] 2.8 回归：现有 guard/checker/policy 测试全绿。

## 3. 实现

- [ ] 3.1 `agent/workflow/event_log.py`：统一投影入口（当代事件兼容，两代分裂修复）；复用 v1 blocked 事件类型，不新增类型。
- [ ] 3.2 `scripts/workflow_state.py`：`flow status/confirm/approve` 命令组；投影生成（派生 + 落盘 workflow-state.json + source_event_seq）；废旧 advance/approve 处理（随 Q2 定）。
- [ ] 3.3 `scripts/workflow_guard.py`：读投影判断 awaiting + last_seq 新鲜度 + stale 回退正则兜底（fail-closed）。
- [ ] 3.4 `scripts/check_openspec_artifacts.py`：tasks 全勾 change 的投影==replay 一致性校验；verify 扩展覆盖新世代。
- [ ] 3.5 `flow-policy.json`：`workflow-state.json` + `workflow-events.jsonl` 入受保护清单（governance=cli_written，P0 已预留 workflow-state.json 条目，补全 governance）。
- [ ] 3.6 文档：AGENTS.md（flow 命令说明）、Impact Analysis 回写。
- [ ] 3.7 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试（投影/命令/guard/checker）。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.5 两代兼容人工验证：对归档老 change 与新 change 各跑一次 `flow status` 确认不抛错。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-flow-event-projection/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次章节。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时，给关联 GitHub issue #136 添加完成说明 comment 并关闭。

# Tasks: declarative-flow-engine

## 1. 规格

- [ ] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #141，父 map #121）。
- [ ] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D8）、Risks、Testing Strategy。
- [ ] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响面。
- [ ] 1.4 维护 `## Reference Implementation Research`（research_tier: full + statechart 声明化引擎/parity 调研结论）。
- [ ] 1.5 开发前使用 batch-grill-me（独立零记忆 subagent 等价设计追问）审视 `design.md`，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），逐项确认实现细节；停轮获得用户对 `## Open Questions` 的确认（每条配具体例子）并记录到 `## User Confirmation`。
- [ ] 1.6 更新 `docs/openspec-change-backlog.md`，把 declarative-flow-engine 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [ ] 1.7 当前规格同步：把 dev-workflow-state-machine spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`（状态机声明化 requirement，SHALL 目标语言，未实现能力不写成已实现），配 workflow-events.jsonl `current_spec_synced` 事件。

## 2. 测试

- [ ] 2.1 statechart 合法性测试：`validate()` 结构校验（孤立状态 / 转移引用缺失 / 无 initial → exit 2）+ parity 交叉校验（声明的转移对 `validate_transition` 验证，非法转移 exit 2）。
- [ ] 2.2 parity 测试：复用 `test_event_log.py` / `test_workflow_state_cli.py` 事件 fixture（Q8），断言 `engine.derive_state(events) == project_workflow_state(...)` **完整投影**（state + milestones + source_event_seq）+ 逐态 `legal_targets` / `can_transition` 等价；gen-2 only（gen-1 排除）。
- [ ] 2.3 演示测试（fixture，Q1/Q6）：测试内注入 `awaiting_design_confirmation` 态 → 引擎正确派生新态 + transition；提交的 statechart 不含演示态；旧 Python 对该态 raise 属已知边界（本 change 不要求它处理）。
- [ ] 2.4 workflow_methods 兼容测试（Q3）：不删 phase/sub_state 段（`_method_hint`/`_build_path` 直接索引），执行方法映射行为不变。
- [ ] 2.5 引擎 CLI 冒烟（e2e 1）：真实归档 change 的 `workflow-events.jsonl`（如 2026-08-16-platform-gate）跑引擎 `derive_state`，输出 == `flow status`（state + milestones + source_event_seq + 容忍异构）。
- [ ] 2.6 真实生命周期（e2e 2）：临时 change 走 `flow block → confirm → advance → 归档`，全程断言投影正确（覆盖目标驱动 API `legal_targets`/`can_transition` + blocked 恢复语义）。
- [ ] 2.7 演示集成（e2e 3）：测试内注入 `awaiting_design_confirmation` → 引擎真实驱动 `flow block --awaiting` 进等待 + 确认恢复（"改规则不改 Python"的端到端证据）。
- [ ] 2.8 全量 pytest 回归：现有测试保持全绿（pre-existing tree-sitter 环境失败除外）。

## 3. 实现

- [ ] 3.1 创建 `flow/statechart.json`（或 .yaml，grill 定）：声明流程状态机（id/initial/states/on），语义对齐现有 Python 常量（awaiting 三态、blocked 建模、派生 any-of + 容忍异构）。
- [ ] 3.2 创建 `flow/engine.py`：`apply_transition(state, event)`、`derive_state(events)`、`validate()`，stdlib-only（json/argparse），对齐 guard 自包含约束。
- [ ] 3.3 workflow_methods.json：**不删** phase/sub_state 段；statechart.json 成为状态集权威声明，workflow_methods 保留每状态执行方法映射（共享状态名，职责不重叠）。
- [ ] 3.4 演示 fixture：测试内构造含 `planning.awaiting_design_confirmation` 的 statechart，断言引擎派生；提交的 statechart.json **不含**演示态。
- [ ] 3.5 文档：AGENTS.md 补配置架构说明（4 个配置文件各管什么：flow-policy 执法 / statechart 流转 / workflow_methods 执行 / platform-gate 平台）；Impact Analysis 回写。
- [ ] 3.6 实现中发现的新影响面已回写 Impact Analysis 和本任务清单。

## 4. 验证

- [ ] 4.1 运行相关单元测试（合法性 / parity / 演示 / workflow_methods 兼容）。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.5 演示验证：parity 测试内注入 `awaiting_design_confirmation` → 引擎正确派生；旧 Python 不需要处理该态（已知边界）。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-declarative-flow-engine/`，配 workflow-events.jsonl `change_archived` 事件（flow-policy `openspec/changes/archive/` prefix → event_explained）。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次章节，配 workflow-events.jsonl `backlog_updated` 事件（flow-policy `docs/openspec-change-backlog.md` exact → event_explained）。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时给关联 GitHub issue #141 添加完成说明 comment 并关闭。
- [ ] 5.7 合入前用 `gh pr checks <PR>` 核对本 PR 的 `validate` 与 `benchmark-gate` check 均 SUCCESS。
- [ ] 5.8 运行 `/review-loop` 直至 PASS（或 3 轮封顶），产出 `reviews/building-review.md` + review manifest（checker 对 tasks 全勾的 change 强制）。

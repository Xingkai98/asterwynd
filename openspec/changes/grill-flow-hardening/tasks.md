# Tasks: grill 环节加固（grill-flow-hardening）

> process change（primary=process）。改流程规格 + 一个 checker 判据 + 文档；**零运行时行为改动**。

## 1. 立项与设计

- [x] 1.1 写 `proposal.md`（Change Type / Why / What Changes / Capabilities / RIR / Impact Analysis）。
- [x] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions D1–D5 / Risks / Testing / Pre-Implementation Review / Impact Analysis）。
- [x] 1.3 开发前使用 `grilling`（或等价独立设计追问）审视 `design.md`，逐项确认每个关键实现细节、依赖、风险、测试策略和文档影响。
- [x] 1.4 **设计阶段审阅闭环**：独立零记忆审阅者对抗分析（逐条证伪 Confirmed Decisions/假设）→ verdict → 修 `grill-design.md` → 再审直到 PASS 或轮数封顶；逐条作答能用代码定的 Open Question；产出 `reviews/grill-adversarial.md`。
- [x] 1.5 停轮确认：把剩余 `## Open Questions` 逐项（配具体例子）抛给用户，答复记入 `reviews/grill-design.md` 的 `## User Confirmation`。

## 2. spec delta

- [x] 2.1 `specs/change-documentation/spec.md`：grill Requirement 增「设计阶段审阅闭环」+「code-resolved vs user-decision」+ skill 名 `grilling`；补对应 Scenario。
- [x] 2.2 `specs/dev-workflow-state-machine/spec.md`：流程链 `batch-grill-me` → `grilling` + 设计阶段审阅闭环；补 Scenario。
- [x] 2.3 `specs/subagents/spec.md`：Reviewer scenario 的引用名 `batch-grill-me` → `grilling`。

## 3. 文档改动

- [x] 3.1 `AGENTS.md`：4 处引用名 → `grilling`；grill 段落补「设计阶段审阅闭环」+「能代码定的用代码定」+ 停轮只抛 user-decision。
- [x] 3.2 `docs/requirements-process.md`：8 处引用名；流程步骤补作答环节。
- [x] 3.3 `docs/agents/domain.md`：2 处引用名。
- [x] 3.4 `openspec/project.md`：2 处引用名 + 作答语义。
- [x] 3.5 `openspec/templates/tasks.md`：1 处引用名 + 设计审阅 task（与本文 1.3/1.4 对齐）。
- [x] 3.6 **在途 change `add-minimal-tui-runtime-view`**：改其 `design.md:53` + `tasks.md:7` 的 `batch-grill-me` → `grilling`（Q1 code-resolved 结论：纳入改名）。

## 4. 门禁（checker）

- [x] 4.1 `scripts/check_openspec_artifacts.py`：`_has_design_review_task` 加 `grilling` 匹配（保留旧名）；错误文案同步。
- [x] 4.2 checker：加「设计阶段审阅」证据门（`reviews/grill-adversarial.md` 存在，触发口径同 building-review 归档点）——**D3 决策：本轮是否上机械门，按 grill 结论**。
- [x] 4.3 `_unconfirmed_open_questions`：确认只读 `## Open Questions`（`## Code-Resolved Questions` 不要求 User Confirmation）。

## 5. 测试

- [x] 5.1 `tests/test_openspec_artifact_checker.py`：`grilling` 新名匹配通过。
- [x] 5.2 旧名 `batch-grill-me` / `grill-with-docs` / 「等价设计追问」仍匹配通过（向后兼容）。
- [x] 5.3 三者皆无 → 仍报错（不放松）。
- [x] 5.4 `## Code-Resolved Questions` 不计入未确认 Open Question。
- [x] 5.5 （若 4.2 上机械门）设计审阅门：新归档缺 `grill-adversarial.md` → 报错；存在 → 通过。

## 6. 验证

- [x] 6.1 `grep -rn "batch-grill-me"` 在活跃文档/spec **仅允许**出现在 `openspec/changes/archive/**` 与本 change 自身目录 `openspec/changes/grill-flow-hardening/**`；余者应为空。
- [x] 6.2 `openspec validate --all --strict` 通过。
- [x] 6.3 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 通过。
- [x] 6.4 全量 `uv run pytest -q` 无新增失败。
- [x] 6.5 benchmark smoke（本 change 不改运行时，`benchmark-gate` 确认无影响即可）。

## 7. 收尾

- [ ] 7.1 归档 change 到 `openspec/changes/archive/2026-10-07-grill-flow-hardening/`。
- [ ] 7.2 清理 backlog（受保护路径，走 `workflow-events.jsonl` 事件）。
- [x] 7.3 同步 current spec：把 3 个 delta 合入 `openspec/specs/{change-documentation,dev-workflow-state-machine,subagents}/spec.md`（受保护路径，走 `current_spec_synced` 事件）。
- [x] 7.4 独立 subagent 审阅闭环（`/review-loop`，R1 CHANGES_REQUESTED → 修 → R2 PASS）+ review manifest。
- [ ] 7.5 发起 PR，关联 issue #298，写明验证结果。
- [ ] 7.6 (post-merge) PR 合入后给 issue #298 添加完成说明 comment 并关闭。

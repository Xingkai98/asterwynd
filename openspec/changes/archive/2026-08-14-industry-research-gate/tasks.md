# Tasks: industry-research-gate

## 1. 规格

- [x] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #133，父 map #121）。
- [x] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D8）、Risks、Testing Strategy。
- [x] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响面。
- [x] 1.4 维护 `## Reference Implementation Research`（status: disabled + 上游决策锁定理由 + research_tier: exempt）。
- [x] 1.5 开发前使用独立 subagent 等价设计追问（grill）审视 `design.md`，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），逐项确认实现细节；停轮获得用户对 `## Open Questions` 的确认并记录到 `## User Confirmation`。
- [x] 1.6 更新 `docs/openspec-change-backlog.md`，把 industry-research-gate 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [x] 1.7 当前规格同步：把 change-documentation spec delta 合并到 `openspec/specs/change-documentation/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。

## 2. 测试

- [x] 2.1 checker `research_tier` 解析测试：`full|light|exempt` 合法；缺失/非法值在 proposal 阶段报错。
- [x] 2.2 exempt reason 校验测试：结构性豁免关键词命中通过；`#<数字>` issue 引用通过；评审文档路径引用通过；占位词命中（`尚未完成`/`待补充`/`待确认` 等 #123 词表）→ exit 2；空 reason → exit 2。
- [x] 2.3 full/light 内容门槛测试：tasks 全勾 + findings 含「自认未完成」短语 → exit 2（#123 回归）；tasks 全勾 + status=disabled → exit 2；proposal 阶段 full+disabled 不报错。
- [x] 2.4 阶段感知测试：tasks 未全勾时只查结构门槛（tier 存在 + 合法），不触发内容门槛。
- [x] 2.5 现有 RIR 结构门槛回归：enabled/disabled 的 status/reason/questions/findings/design impact 非空检查不破坏。
- [x] 2.6 存量 active change 兼容测试：`openspec/changes/` 下未补 tier 字段的非 docs change 在 proposal 阶段报错信息清晰可修。

## 3. 实现

- [x] 3.1 checker 扩展：`research_tier` 字段解析与合法性校验（proposal 结构门槛）。
- [x] 3.2 checker 扩展：tasks 全勾时的 tier 内容门槛——full/light 的 findings/design impact 占位词检查（复用 #123）+ status 约束；exempt 的 reason 证据校验（结构性豁免关键词 + `#<数字>`/评审路径引用 + 占位词拦截）。
- [x] 3.3 AGENTS.md「参考实现调研」节升级为「业界调研门禁」：三档分流判据表 + 豁免质量门槛 + development-guide 链接。
- [x] 3.4 `docs/development-guide.md` 新增「业界调研门禁」小节：三档判据举例、豁免 reason 写法示范（好/坏例子）、常见误用。
- [x] 3.5 spec delta 合入：change-documentation 的 RIR gate requirement 扩展 + 新增 Research tier triage requirement。
- [x] 3.6 存量 active change（add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method）的 RIR 节补齐 `research_tier` 字段（如合规，配 workflow-events 解释事件）。
- [x] 3.7 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。

## 4. 验证

- [x] 4.1 运行相关单元测试（checker tier 校验矩阵）。
- [x] 4.2 运行全量测试 `uv run pytest -q`。
- [x] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.5 人工核对 AGENTS.md 判据表与 development-guide 示例、spec Requirement 口径一致。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/2026-08-14-industry-research-gate/`。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次章节。
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 PR 合入时，给关联 GitHub issue #133 添加完成说明 comment 并关闭。

## 审阅修复（review-loop，issue #90）

- Round 1（2026-08-14，run aba4d44717337df70）：**[中] light 档「research questions 可省略」与 checker 结构门槛矛盾**——checker 在 status=enabled 结构门槛按 tier 分流，light 跳过 `research questions` 必填（`scripts/check_openspec_artifacts.py` enabled_fields 分支），新增回归测试 `test_light_tier_research_questions_optional`（proposal 阶段 + tasks 全勾完成时均通过）。观察项（full/light+disabled 完成时只报 status 根因错误、不聚合 findings 占位）确认为有意行为：status 错误是根因，修正为 enabled 后 #123 检查即捕获 findings 占位，净效果仍 exit 2，不修复。
- Round 2（2026-08-14，run a8615a71314c8044a）：**[中] spec 侧残留 rq 必填口径**——spec delta/synced 的「Non-docs change records enabled research」与「Artifact checker enforces record shape」两处场景仍无条件要求 enabled 调研含 `research questions`，与「Routine enhancement requires light research」（light 可省略）及已修复的 checker 自相矛盾；改为 `research_tier: full` 才要求 research questions 非空（delta 与 synced spec 同步修）。[低] `tests/test_flow_policy.py` 的 #123 内容门槛 fixture 补 `research_tier: full`（消除多余结构错误）。

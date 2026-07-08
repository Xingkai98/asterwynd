# multi-agent-dev-workflow 设计评审报告

## 总体结论

**CHANGES_REQUESTED**

设计方向成立：五阶段状态机、grill-with-docs 内嵌 planning、角色 agent 一一对应 phase、单 agent 兼容和 human review gate 的总体思路都合理。但当前方案存在多处规范不一致和流转语义缺口，尤其是 `handoff.json` schema、blocked 状态、handoff trigger、closing gate、routing 枚举和 tasks 覆盖范围。建议修正后再进入实现。

## 逐项结论

1. **五阶段划分：通过**

   `planning -> reviewing -> building -> code-review -> closing` 的拆分合理，分别对应规划、独立设计审查、实现、代码审查和收尾。grill-with-docs 放在 `planning.writing_design` 和 `planning.grilling_design` 的迭代中是正确的，因为它是设计自审和澄清机制，不是独立外部审查阶段；`reviewing` 再做独立评审，职责更清楚。需要修正文档中的“四阶段”残留：`dev-workflow-state-machine/spec.md:31`、`:263`、`:289`，`design.md:84`，`tasks.md:50`。

2. **handoff.json schema：需要修改**

   字段方向基本对，但不完整且有自相矛盾点。`design.md:124` 提到 `schema_version` 和 `state_machine_version`，但规范 schema 未包含；`state.phase` 允许 `blocked` / `done`，同时 `state.sub_state` 又强制为 string，和 `blocked` 无 sub_state 的要求冲突；blocked 解除要求恢复前状态，但 blockers 字段没有记录 `return_state` / `blocked_from`；human 触发的 transition 只有 `agent_run_id`，缺少 `actor` / `decision` / `comment` 之类的人审计信息；`last_gate` 只定义 gate 状态下的内容，没有定义非 gate 状态的 null/absent 规则。

3. **流转规则：需要修改**

   正向跨 phase、两个 skip 场景和基本回退都有覆盖，但合法流转表还不够实现。phase 内 sub_state 只有序列描述，没有完整合法边表；`handoff` trigger 被定义为 transition trigger，但跨 phase 流转又要求 gate 后使用 `human_review`，导致 `handoff` transition 是否真实改变 state 不清楚；回退规则声称可回到之前任意阶段，但规范允许回到 `closing` 且排除了 `code-review`，没有限制目标必须早于当前状态；blocked 进入和解除没有纳入合法流转表，也没有明确解除阻塞使用什么 trigger。`closing.syncing_specs -> ... -> pr_ready -> merged -> ready_for_review` 也有问题：merge 已发生后再 human gate，人工控制已经太晚。

4. **角色 agent：通过**

   Planner / Reviewer / Builder / CodeReviewer / Closer 与五个 phase 一一对应，职责边界清楚。需要修正 `proposal.md:24` 的 Modified Capabilities，那里只列了 Planner / Reviewer / Builder / Closer，漏掉 CodeReviewer。

5. **路由配置：需要修改**

   `inline` / `subagent` / `claude-code` / `codex` 加 `same` / `new` / `ask` 的模型合理，两层覆盖也合理。但文档内部不一致：`design.md:22` 的 executor 列表漏了 `codex`，`tasks.md:31` 的实现任务也漏了 `codex`。`session_mode: same` 仅对 `inline` 有效，但没有说明其他 executor 配 `same` 时是拒绝、降级还是转为 `new`。gate 点询问路由时，规范写的是检查“当前 phase 的 session_mode”，但实际应检查即将进入的下一 phase 的路由配置，否则语义会错位。

6. **Human review gate：需要修改**

   每个 phase 末尾设置 `ready_for_review` 能提供人工控制，skip 和 rollback 也符合 human-in-the-loop 目标。但 closing 的 gate 放在 `merged` 之后不合理，应该在 PR ready / merge 前提供最终人工确认；如果保留 merge 后确认，那它只能是合入后核验，不应承担阻断 gate 的职责。另外 transition schema 缺少人审结果元数据，后续审计和 UI 展示会不足。

7. **单 agent 全流程兼容：通过**

   不强制切换 agent 是正确取舍，保留现有线性流程的低摩擦路径。规范也明确即使同一 `run_id` 贯穿全流程，human gate 和 transition 记录仍然保留。需要同步“四个 phase”笔误为“五个 phase”。

8. **风险覆盖：需要修改**

   现有风险覆盖了 schema 演进、返工和 handoff note 质量，但遗漏了几个主要风险：`handoff.json` 并发写入/冲突、gitignored handoff note 导致异地 agent 拿不到上下文、外部 CLI executor 的权限和环境差异、human gate 被绕过或手工修改状态、blocked 恢复语义不清、closing/merge 顺序错误、现有 active change 迁移策略。`design.md:136-140` 还有 schema version、Web UI、CLI 命令等 open questions，进入实现前应收敛为明确结论或任务。

9. **任务完整性：需要修改**

   tasks 覆盖了主要实现和测试，但还缺几类必要任务：补齐 schema version / state_machine_version 和 blocked return state；实现 blocked 进入/解除的状态机逻辑；补充 Codex executor 分发任务；更新 `openspec/config.yaml` 默认路由；明确 CLI/Web UI 影响是本次实现还是显式非目标；增加外部 executor、gate 审计字段、非法 `session_mode` 组合、closing gate 顺序的测试；修正 docs 任务里的“四阶段”表述。

## 发现的问题

### 阻塞性

无根本性设计问题，不需要推倒重来。

### 重要

- **状态机数量表述不一致**：方案核心是五阶段，但多处写“四阶段”，会直接影响实现、文档同步和测试命名。
- **`handoff.json` schema 与设计承诺不一致**：schema version 未落入规范，blocked/done 与 sub_state 要求冲突，blocked 无法可靠恢复前状态。
- **`handoff` trigger 和 `human_review` trigger 职责重叠**：如果 phase 间实际由 human gate 推进，handoff transition 是状态流转还是仅记录 note 尚不清楚。
- **回退和 blocked 流转规则不完整**：回退目标集合与“之前任意阶段”不一致，blocked 缺少合法流转表和解除 trigger。
- **closing gate 放在 merge 后**：这削弱了 human review gate 的控制能力，也与 PR 前归档和校验的现有流程不匹配。
- **路由枚举和任务不一致**：`codex` 在 proposal/spec 中存在，但 design goal 和 implementation task 中遗漏；`session_mode` 与 executor 的非法组合没有规则。
- **Impact Analysis 与 tasks 不闭合**：proposal 提到 CLI/Web UI/权限/trace/config 影响，但 tasks 没有全部覆盖，也没有明确哪些推迟到后续。

### 建议

- 给 `handoff.json` 增加最小示例和 JSON Schema/Pydantic 字段清单，明确 optional/null 规则。
- 将 transition 扩展为 `actor_type`、`actor_id`、`decision`、`reason`、`note_path`，避免把 human 决策塞进 `agent_run_id`。
- 把 blocked 建模为 wrapper 状态，显式保存 `blocked_from`，解除时追加 transition 并恢复。
- 把 closing 调整为 `syncing_specs -> archiving -> updating_backlog -> validating -> pr_ready -> ready_for_review -> done`，merge 后确认另设 post-merge checklist 或独立状态。
- 明确 `handoff_note` 的提交策略：如果 `.handoff/` 不提交，外部新 session/CLI 如何获得 note 内容需要有复制、嵌入 prompt 或可选提交 artifact 的方案。
- 在 tasks 中增加“收敛 Open Questions”任务，避免实现阶段继续保留 schema version、Web UI、CLI 命令等未决问题。

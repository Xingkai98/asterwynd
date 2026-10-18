# Q14: 开发流程——OpenSpec + grill + 审阅闭环

## 讲稿

这个项目最值得讲的不是某个功能，而是**开发流程本身**——它被设计成"每次新功能都强制走工程纪律"。面试官问"你怎么保证代码质量"，答案就是这套流程。

**主干流程**（AGENTS.md）：需求讨论 → proposal/design → tasks/spec delta → 独立 worktree 实现（TDD）→ 强制 subagent 审阅闭环 → 归档 + PR。

**机械门禁的现行分工**：

1. **grill 门禁**（#95，写代码前）。非平凡 change 写代码前，必须由**独立零记忆 subagent** 挑战 design.md，产出结构化决策记录（`reviews/grill-design.md`，≥3 条决策 + Open Questions 用户拍板）。witnessloop plugin guard 在 PreToolUse 检查这个证据——没有 grill 证据就**阻止代码写操作**。这解决的是"agent 自己写设计自己确认"的自我欺骗。

2. **审阅闭环门禁**（#90，实现后）。实现完成、发起 PR 前，必须 spawn **独立零记忆 subagent** 审阅代码（8 个维度：任务逐项验证/正确性/Spec 对齐/冗余度/测试覆盖/安全性/可维护性/CI 完整性），出 verdict。一轮 = 一个**非空 medium+ 批次**的闭环：审阅者开批 → 开发者全修并加回归测试 → 审阅者只做修复验证；验证期新问题只进 deferred（下一批）。批次冻结；最多 **20 个已收口轮**，超限 ⇒ 超上限 **BLOCKED** + 建议推倒重开；出口只有 **PASS** / **BLOCKED** + 成因 / 超上限 **BLOCKED**，CHANGES_REQUESTED 不是出口。审阅报告（含 `## 闭环出口` PASS）+ witnessloop 形态 manifest（绑定 reviewer/author run、base/head sha、report hash）进 change 目录；瘦 checker 校验出口，witnessloop `check` 校验 manifest。

**受保护 artifact 证据**：修改 known-debt / specs / backlog 必须配 workflow-events 结构化事件（archive 不要求）；阶段 review 报告必须配 witnessloop 形态 manifest，building review 的 `## 闭环出口` 须为 PASS。禁止只靠手写 PASS 文本过 gate。

面试时我会讲真实案例：#99 长期记忆可逆性，3 轮审阅——Round 1 修 5 项、**Round 2 抓到一个安全漏洞**（`loser` 参数路径穿越可任意写 `.md`）、Round 3 PASS。这是流程真的抓 bug 的证据，不是摆设。

## 代码走读

### 入口与调用链

```
AGENTS.md（开发流程规则）→ openspec/changes/<id>/（proposal/design/tasks/specs/reviews）
  ├─ /grill → 独立 subagent → reviews/grill-design.md（grill 门禁）
  ├─ witnessloop plugin guard（PreToolUse, Write|Edit）→ 无 grill 证据拦代码写
  ├─ scripts/bash_write_guard.py（PreToolUse, Bash）→ 拦 Bash 写受管/受保护路径
  └─ /review-loop → 独立 subagent → reviews/building-review.md + witnessloop manifest（审阅门禁）
      → scripts/check_openspec_artifacts.py 机械校验六条项目规则
```

### 关键文件逐段

**`AGENTS.md`** — 最高优先级规则。
- "开发流程：OpenSpec 主干 + 强制审阅闭环"节：主干流程 + /review-loop + worktree 隔离 + 验证命令速查。
- 分支纪律：`<change-id>/<YYYY-MM-DD>` 分支（witnessloop guard 依赖分支名推导 change-id）。

**`witnessloop plugin guard` + `scripts/bash_write_guard.py`** — 两个 PreToolUse hook，分工不重叠。
- witnessloop guard（`Write|Edit`）：grill 证据与 change 映射；没有 `reviews/grill-design.md`（≥3 决策 + Open Questions 全确认）就拦代码写。
- Bash guard（`Bash`）：quote-aware tokenizer 解析直接文件写操作，命中 `agent/**`、`scripts/**`、`web/**` 或受保护 artifact 时 `exit 2`；只读命令放行。`git rm` / `git mv` 是删除/改名的合法通道；显式路径的 `git restore` / `checkout --` 与非只读 `git apply` 拦截；变量展开、符号链接、merge/rebase/cherry-pick 等登记为已知绕过面（CI 兜底）。
- 本地 hook 只是 checkpoint；required 的 `gate / check` 才是最终防线。

**`scripts/check_openspec_artifacts.py`（瘦 checker）**
- 六条规则：RIR / Impact Analysis / benchmark smoke / tasks 与归档点完成度（含新归档的 grill 证据）/ backlog 一致性 / building review `## 闭环出口`。
- `_check_building_review`：**宽触发**——只要 `reviews/building-review.md` 存在且 terminal `BLOCKED` / `CHANGES_REQUESTED`，一律报错；**完成面**——非 docs + spec delta + tasks 全勾（或本 PR 新归档目录）必须存在报告且 `## 闭环出口` 为 `PASS`。
- change 契约、review manifest、active-stage grill 证据与受保护写入解释由 witnessloop `gate / check` 承担，瘦 checker 不重复。

**`scripts/platform_gate.py`** — branch protection 的配置即代码：`--apply` 幂等设置、`--verify` 只读漂移检测；witnessloop 不覆盖平台配置，因此保留。

**`.claude/commands/grill.md` / `.claude/commands/review-loop.md`** — grill 与审阅闭环的本地命令。

**`agent/workflow/*` 与 `scripts/workflow_state.py`（已删除）** — 原事件投影 / 状态机残件；新 change 只保留历史 `workflow-events.jsonl` 作为只读数据，产物是 witnessloop 形态 `reviews/<stage>.manifest.json`。

### 设计理由

- **独立 subagent 打破自我确认**：agent 自己写设计自己确认 = 自欺；独立零记忆 subagent 挑战设计/代码才有独立视角（#90/#95 的核心动机）。
- **机械强制而非软提醒**：witnessloop guard + Bash guard + 瘦 checker + witnessloop `gate / check`，把"流程纪律"变成"做不到就合不进来"。
- **证据进 change 目录**：grill 记录 + 审阅报告 + witnessloop manifest 随 PR 进仓库，CI 可机械校验，不依赖口头/手写 PASS（受保护 artifact 证据规则）。
- **有界批次 × 20 轮上限**：一轮 = 一个非空 medium+ 批次的闭环（开批 → 全修 → 只做修复验证 → 收口）；批次冻结，验证期新问题只进 deferred；medium+ 全修，low/nit 可登记不修但须写理由；最多 20 个已收口轮，超限 ⇒ 超上限 BLOCKED + 建议推倒重开——终止性由「收口确认空批 ⇒ PASS / 阻塞 ⇒ BLOCKED」保证。
- **这是面试差异化**：多数项目"写完就提交"，这个项目"每个 change 都有设计追问 + 独立审阅 + 机械门禁"——工程纪律本身就是 Agent 岗位要证明的能力。

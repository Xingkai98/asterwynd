# Q14: 开发流程——OpenSpec + grill + 审阅闭环

## 讲稿

这个项目最值得讲的不是某个功能，而是**开发流程本身**——它被设计成"每次新功能都强制走工程纪律"。面试官问"你怎么保证代码质量"，答案就是这套流程。

**主干流程**（AGENTS.md）：需求讨论 → proposal/design → tasks/spec delta → 独立 worktree 实现（TDD）→ 强制 subagent 审阅闭环 → 归档 + PR。

**两道机械门禁**：

1. **grill 门禁**（#95，写代码前）。非平凡 change 写代码前，必须由**独立零记忆 subagent** 挑战 design.md，产出结构化决策记录（`reviews/grill-design.md`，≥3 条决策 + Open Questions 用户拍板）。workflow_guard 在 PreToolUse 检查这个证据——没有 grill 证据就**阻止代码写操作**。这解决的是"agent 自己写设计自己确认"的自我欺骗。

2. **审阅闭环门禁**（#90，实现后）。实现完成、发起 PR 前，必须 spawn **独立零记忆 subagent** 审阅代码（8 个维度：任务逐项验证/正确性/Spec 对齐/冗余度/测试覆盖/安全性/可维护性/CI 完整性），出 verdict。CHANGES_REQUESTED 就修复加回归测试再审，直到 PASS 或 3 轮封顶。审阅报告 + manifest（绑定 reviewer run、base/head sha、报告 hash）进 change 目录，artifact checker 机械校验。

**受保护 artifact 证据**：修改 known-debt/specs/archive/backlog 必须配 workflow-events 结构化事件；阶段 review 报告必须配 manifest。禁止只靠手写 PASS 文本过 gate。

面试时我会讲真实案例：#99 长期记忆可逆性，3 轮审阅——Round 1 修 5 项、**Round 2 抓到一个安全漏洞**（`loser` 参数路径穿越可任意写 `.md`）、Round 3 PASS。这是流程真的抓 bug 的证据，不是摆设。

## 代码走读

### 入口与调用链

```
AGENTS.md（开发流程规则）→ openspec/changes/<id>/（proposal/design/tasks/specs/reviews）
  ├─ /grill → 独立 subagent → reviews/grill-design.md（grill 门禁）
  ├─ workflow_guard.py（PreToolUse hook）→ 无 grill 证据拦代码写
  └─ /review-loop → 独立 subagent → reviews/building-review.md + manifest（审阅门禁）
      → scripts/check_openspec_artifacts.py 机械校验
```

### 关键文件逐段

**`AGENTS.md`** — 最高优先级规则。
- "开发流程：OpenSpec 主干 + 强制审阅闭环"节：主干流程 + /review-loop + worktree 隔离 + 验证命令速查。
- 分支纪律：`<change-id>/<YYYY-MM-DD>` 分支（门禁依赖分支名推导 change-id）。

**`scripts/workflow_guard.py`** — PreToolUse hook。
- 受保护路径拦截：known-debt/known-issues/specs/archive/backlog/handoff/review-manifest 不可由 agent 直接写（须配 workflow-events 或 manifest）。
- **grill gate**（165 行起）：`_grill_evidence_missing(change_id)` 检查非 docs + 有 spec delta 的 change 是否有 `reviews/grill-design.md` 且 Open Questions 全确认；缺失则 `exit 2` 拦代码写。
- 文档类写操作豁免（`_is_change_doc_write` 340 行）：proposal/design/tasks/specs/reviews 可写（避免死锁）。

**`scripts/check_openspec_artifacts.py`**
- `_check_design_review_task`（438 行）：grill 门禁的 checker 侧——tasks 全勾选的完成 change 必须有 grill 证据（≥3 决策 + Open Questions 全确认）。
- `_check_review_manifests`（732 行）：审阅门禁——非 docs + 有 spec delta + tasks 全勾选的 change 必须有 `reviews/building-review.md` + manifest 且 PASS。
- `_check_benchmark_smoke_task` / `_check_current_spec_sync_task`：benchmark 冒烟 + spec 同步任务校验。

**`.claude/commands/grill.md` / `.claude/commands/review-loop.md`** — grill 与审阅闭环的本地命令。

**`agent/workflow/review_manifest.py`** — manifest 生成：绑定 reviewer run、base/head sha、tasks/spec/diff/report hash。

### 设计理由

- **独立 subagent 打破自我确认**：agent 自己写设计自己确认 = 自欺；独立零记忆 subagent 挑战设计/代码才有独立视角（#90/#95 的核心动机）。
- **机械强制而非软提醒**：workflow_guard PreToolUse 拦截 + artifact checker 门禁，把"流程纪律"变成"做不到就合不进来"。
- **证据进 change 目录**：grill 记录 + 审阅报告 + manifest 随 PR 进仓库，CI 可机械校验，不依赖口头/手写 PASS（受保护 artifact 证据规则）。
- **3 轮封顶**：审阅不会无限循环，第 3 轮仍 CHANGES_REQUESTED 升级人类——流程有终止条件。
- **这是面试差异化**：多数项目"写完就提交"，这个项目"每个 change 都有设计追问 + 独立审阅 + 机械门禁"——工程纪律本身就是 Agent 岗位要证明的能力。

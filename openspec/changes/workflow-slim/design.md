# Design: 流程精简 — 保留 subagent 审阅闭环，停用 workflow 状态机仪式

## Context

PR #67 引入的 workflow 四阶段状态机（`agent/workflow/` + `workflow_state.py`）在 #77/#76/#78 开发中证明仪式过重：phase/sub_state 推进、handoff.json、gate 停止——agent 容易漏走（#78 开发就漏了 reviewing_impl），且价值不大。但状态机里「独立 subagent 审阅 + 机械检查」（`check_phase_done.py` 查 `_agent-calls.json` + `building-review.md`）是有价值的——它用机械手段保证审阅不被漏掉。

本 change 精简 PR #67：保留「subagent 审阅闭环」，停用「状态机仪式」。

## Goals / Non-Goals

**Goals:**

- 开发流程精简为「OpenSpec 主干 + 强制 subagent 审阅闭环」。
- 新增 `/review-loop` 命令封装审阅闭环（审→改→再审直到 PASS 或 3 轮）。
- 机械门禁：非 docs + 有 spec delta + tasks 全勾选的 change 必须有审阅证据。
- 审阅证据随 change 进 PR（`openspec/changes/<id>/reviews/`），CI 可校验。
- 受保护文件保护始终生效（不随状态机停用消失）。

**Non-Goals:**

- 不删除 `agent/workflow/` 模块（保留 review_manifest 等被 check 依赖的部分）。
- 不重做 OpenSpec 主干流程（proposal/design/tasks/spec 照旧）。
- 不引入外部审阅服务。

## Decisions

### Decision 1: 审阅证据存 change 目录 reviews/，随 PR 提交

**方案**：审阅证据（`building-review.md` + manifest）存放于 `openspec/changes/<id>/reviews/`，随 change 文档进 PR，CI 的 artifact checker 可机械校验。

**备选**：存 `.handoff/<id>/`（gitignore，本地）。被拒：`.handoff/` 不随 PR 提交，CI 上强制门禁找不到证据 → 误报 building-review.md missing。这正是方案 A 修复的核心问题。

**理由**：审阅证据是 change 的正式产出，应随 change 提交并接受 CI 校验。

### Decision 2: 强制门禁触发条件 = 非 docs + 有 spec delta + tasks 全勾选

**方案**：`check_openspec_artifacts.py` 的 `_check_review_manifests` 对「非 docs + 有 spec delta + tasks.md 全部 [x]」的 change 强制 building-review.md + manifest 存在且 PASS。

**备选**：只看「非 docs + 有 spec delta」。被拒：spec delta 从 proposal 阶段就存在，提案/部分实现的 change 会被误伤，CI 基线破坏（审阅 Round 1 发现的 HIGH）。

**理由**：tasks 全勾选是"实现完成"的可靠信号，避免误伤在途 change。

### Decision 3: workflow_guard 停用 phase gate，保留受保护文件保护

**方案**：`workflow_guard.py` 移除 phase gate check（active change/worktree/required_files），普通写操作放行；受保护文件（known-issues/known-debt/specs/archive/workflow-events.jsonl 等）始终拦截，不依赖 workflow 状态。

**备选**：保留 gate check。被拒：状态机停用后无 handoff.json，gate check 会阻止所有写操作（开发阻塞）。

**理由**：受保护文件保护是安全边界，不应随流程精简消失；phase gate 是已停用的仪式。

### Decision 4: /review-loop 命令不入库，AGENTS.md 记录

**方案**：`.claude/commands/review-loop.md` 遵循 `.claude/` gitignore 约定不入库；命令的文档化在 AGENTS.md 验证命令速查表。

**备选**：force-add 入库。被拒：破坏 `.claude/` 不入库约定（工作区约束）。

**理由**：命令是本地工具，文档是仓库资产。

## Pre-Implementation Review

经 batch-grill-me（issue #90 讨论）已定稿以下决策：

- 开发流程 = OpenSpec 主干 + 强制 subagent 审阅闭环。
- 机械门禁用 artifact checker（非 CI 单独步骤），PR 前跑。
- 审阅闭环三轮封顶，CHANGES_REQUESTED 必须修复并加回归测试。
- 受保护 artifact 修改仍需 workflow-events.jsonl 结构化事件。

## Reference Implementation Research

- status: disabled
- reason: 本 change 是流程/工具链精简，不涉及 coding-agent 能力实现对比；审阅闭环的设计基于 #77/#76/#78 开发复盘（本仓库自己的经验），无需外部参考。

## Risks / Trade-offs

- **[审阅闭环被漏跑] → 机械门禁兜底（artifact checker 强制）。**
- **[证据路径迁移破坏既有流程] → 迁移后全量测试 + 端到端 CI 场景验证。**
- **[workflow_guard 行为变化] → 受保护文件保护保留，普通写放行，测试覆盖新行为。**

## Testing Strategy

- 单元测试：`_tasks_all_complete`、`_check_review_manifests` 强制逻辑、workflow_guard 新行为。
- 端到端：证据随 change 进 PR → CI 通过；证据只在 `.handoff` → 报缺审阅。
- 回归：全量 pytest + openspec validate + artifact checker。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `AGENTS.md` | 流程文档重写 |
| `.claude/commands/review-loop.md` | 新增审阅闭环命令（本地） |
| `scripts/check_openspec_artifacts.py` | 强制门禁逻辑 |
| `scripts/workflow_guard.py` | phase gate 停用，受保护文件保护保留 |
| `agent/workflow/review_manifest.py` | 审阅证据路径迁移 |
| `scripts/check_phase_done.py` | review report 路径同步 |
| 测试 | 5 个测试文件路径/行为同步 |

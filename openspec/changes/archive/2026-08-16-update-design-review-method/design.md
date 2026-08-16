# Design: 设计追问工具从 grill-with-docs 切换为 batch-grill-me

## Context

`grill-with-docs`（grilling + domain-modeling）是逐条追问，`batch-grill-me` 是设计树逐轮追问——每轮把可问的整个 frontier 一次问完，减少往返。benchmark-evaluation-depth 已用 batch-grill（design.md 记录"经 batch-grill（设计树逐轮确认）"）并验证效率更高。本 change 把项目流程规范从前者切换为后者。

## Goals / Non-Goals

**Goals:**

- 设计追问工具统一切换为 `batch-grill-me`。
- 同步所有引用该工具的权威文档、规格、模板、机械检查与测试。
- 检查器保持向后兼容（历史 change 文档写 `grill-with-docs` 仍可通过）。

**Non-Goals:**

- 不改历史调研报告 `docs/research/agent-engineering-best-practices-2026-07.md`。
- 不重做 `batch-grill-me` skill 本身。

## Decisions

### Decision 1: 统一使用 `batch-grill-me` 作为设计追问工具

**方案**：AGENTS.md、requirements-process.md、project.md、模板、方法映射统一写 `batch-grill-me`；检查器同时接受 `batch-grill` 与 `grill-with-docs`（子串匹配，兼容历史）。

**备选**：仅改 AGENTS.md 不改检查器。被拒：检查器不认新关键字会导致新 change 无法通过门禁。

**理由**：工具切换 + 机械检查同步，才能让新规则真正生效。

### Decision 2: 保留检查器/测试中的旧关键字兼容

**方案**：`_has_design_review_task` 同时匹配 `grill-with-docs`、`batch-grill`、`等价设计追问`；测试夹具保留 `Run grill-with-docs.` 用例验证兼容性。

**备选**：删除旧关键字。被拒：历史 change 的 tasks.md 写 `grill-with-docs` 会全部失效。

**理由**：向后兼容避免历史 change 回归。

### Decision 3: 本次流程变更作为 process change 承载

**方案**：新建 `update-design-review-method` process change，其 workflow-events.jsonl 记录对 3 个受保护 spec 的修改解释（满足受保护 artifact 规则）。

**备选**：直接改 spec 不建 change。被拒：违反"修改 `openspec/specs/**` 必须有 workflow-events.jsonl 结构化解释事件"规则。

**理由**：合规承载受保护 artifact 变更。

## Pre-Implementation Review

- 本 change 为纯流程工具切换（process 类型），不涉及实现方案选择；用户已确认使用 batch-grill-me。无需完整 batch-grill-me 追问。

## Risks / Trade-offs

- **[历史 change 文档兼容] → 检查器保留旧关键字，历史文档不受影响。**
- **[新 change 漏写新关键字] → 检查器接受 `batch-grill` 子串，`batch-grill-me` 天然匹配。**
- **[文档不一致残留] → 已全面 grep 扫描，除历史调研报告与检查器兼容文本外无残留。**

## Testing Strategy

- 检查器测试：`test_openspec_artifact_checker.py`（新断言文案 + 旧关键字兼容用例）。
- 门禁测试：`test_check_phase_done.py`（含 `grill-with-docs` 夹具验证兼容）。
- 回归：全量 pytest 无新增失败（9 个既有环境失败与本次无关，已挂 issue #82）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `AGENTS.md` | 设计追问规则、路由表、worktree 方法表 |
| `docs/requirements-process.md` | 设计追问流程描述 |
| `docs/agents/domain.md` | ADR 创建触发方式 |
| `openspec/project.md` | 项目规则引用 |
| `openspec/templates/tasks.md` | tasks 模板 |
| `scripts/check_openspec_artifacts.py` | 设计审阅任务检查 |
| `scripts/workflow_methods.json` | planning exploring 方法映射 |
| `openspec/specs/*` | 3 个流程规格同步 |
| 测试 | 断言文案同步 |

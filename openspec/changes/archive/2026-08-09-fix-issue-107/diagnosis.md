## Symptom

注入层超预算时 agent 丢失当前执行进度。Todo 列表（当前任务、已完成项）被截断或整层移除，agent 在后续迭代中"忘记自己在做什么"。

## Reproduction

1. 使注入层总 token 超过 `min(20_000, context_window × 20%)`（例如 ASTER.md 过大，或激活大量 skill）。
2. `ContextBuilder._apply_budget` 从最低优先级层尾部截断。
3. `TodoSource` 为 P5 且 `critical=False`，是最先被裁的层之一——先截尾，超额仍不满足时整层删除。
4. agent 的下一次迭代上下文中没有 Todo，执行进度丢失。

## Evidence

- `agent/context/sources.py`（修复前）：`TodoSource.priority = 5`、`critical = False`——最低优先级且可裁剪。
- `agent/context/builder.py:175-179` `_find_trimmable_index` 从尾部（最低优先级）向前找第一个非 critical 且非 cacheable 层：P5 Todo 是首选裁剪目标。
- `agent/loop.py:1352-1354`（修复前）注册顺序确认 Todo 属于 P5 区块。
- issue #107 明确记录：严重程度中——20K 预算日常足够，但 ASTER.md 过大或激活大量 skill 时可能触发；执行进度丢失比技能列表丢失更致命。

## Root Cause

Todo 是执行进度关键状态，却被安排在最低优先级层（P5）且未受保护。截断策略按"优先级 + critical/cacheable 保护"排序，没有区分"可再生的列表（技能索引）"与"不可再生的执行状态（Todo）"，导致最容易丢失的层最先被丢。

## Recommended Direction

最小修改：将 `TodoSource.priority` 提升到 2（与 `MemoryIndexSource` 同级，非 critical、非 cacheable）。这样 Todo 排在 P4（技能层）/ P5（规划层）之后才被裁——只有 P4/P5 全部裁完、预算仍超限时才动 Todo。此方案不改截断机制、不引入层加权，风险最小。

备选方案（issue #107 讨论过，未采用）：
- 标记 `critical=True`：会与 P0/P1 同级的"永不裁剪"语义冲突，Todo 是动态层，不应绝对保护。
- 截断层加权（关键状态只摘要不截断）：改动大，超出 bug fix 范围。
- 合入 PlanningState（P5）：只转移位置，仍在 P5 最先被裁，不能解决问题。

## Regression Tests

- `tests/agent/context/test_builder.py::TestContextBuilderTruncation::test_todo_source_priority_is_p2`：直接断言 `TodoSource.priority == 2`，绑定数据变更本身——若改回 5 该测试失败。
- `tests/agent/context/test_builder.py::TestContextBuilderTruncation::test_real_todo_survives_after_p4_p5_trimmed`：注册真实 `TodoSource`，在预算压力下断言 Todo 完整存活、P4/P5 完整内容被裁剪——若 priority 回退到 5 该测试失败（已实测验证）。

## Why

`agent/context/sources.py` 中 `TodoSource` 的注入优先级是 P5（最低）且 `critical=False`。注入层预算超过 `min(20K, 窗口×20%)` 时，`_apply_budget` 从最低优先级层尾部截断：Todo 会先于 P4 技能层被截断甚至整层移除，导致 agent 丢失当前执行进度（正在做什么、已到哪一步）。执行进度丢失比技能列表丢失更致命——agent 会忘记自己正在执行的任务。

## Change Type

- primary: bugfix
- secondary: []

## What Changes

- `TodoSource.priority` 从 5 提升到 2，与 `MemoryIndexSource` 同级（非 critical、非 cacheable）。
- `agent/loop.py` `_make_default_context_builder` 注册顺序调整为 P2 区块（MemoryIndex 之后）。
- 修复后裁切顺序：PlanningState（P5）→ PlanMode（P5）→ SkillActive（P4）→ SkillIndex（P4）→ Todo（P2）→ （cacheable MemoryIndex 停止）。Todo 只会在 P4/P5 全部裁完、预算仍超限时才被裁。
- 新增回归测试绑定真实 `TodoSource`，验证 priority 回退到 5 时测试失败。

## Capabilities

### Modified Capabilities

- `context-engineering`: 新增"执行进度保留（Todo 层级保护）"Requirement——注入层预算超限时 Todo 层（P2）在 P4/P5 可变层之后才被裁剪，将本次修复确立的行为不变量写入规格。

## Dependencies

- 无新依赖。

## Impact Analysis

- 影响代码：
  - `agent/context/sources.py`：`TodoSource.priority` 5 → 2；`PlanModeSource` 预算注释同步（P5 和 5K → 4K）。
  - `agent/loop.py`：`_make_default_context_builder` 注册顺序（Todo 移入 P2 区块）。
  - `agent/context/builder.py`：`render_layers` docstring 更正（预算先裁 P4/P5，P4/P5 裁完后可能继续裁非 cacheable 的 P2）。
  - `tests/agent/context/test_builder.py`：新增 `test_todo_source_priority_is_p2` 与 `test_real_todo_survives_after_p4_p5_trimmed`。
- 影响文档：`docs/agent-internals.md`、`docs/interview-script/walkthrough/W04-context-engineering.md`、`docs/interview-script/walkthrough/self-test-QA.md` 中 Todo 层归属（P5 → P2）与裁切顺序描述同步。
- 行为影响：超预算时执行进度 Todo 的存活优先级提高；正常预算下行为不变（16.5K < 20K 全部保留）。cacheable 稳定前缀（P0/P1/P2 MemoryIndex）不受影响，cache_control 断点位置不变。

## Reference Implementation Research

- status: disabled
- reason: 本修复是项目内部上下文注入层的优先级归属调整（一个数值 + 注册顺序），不引入新的 coding-agent 能力或对外协议；issue #107 已给出根因与三个候选方案（提升优先级 / 截断层加权 / 合入 PlanningState），选用最小修改方案，无外部参考实现需要调研。

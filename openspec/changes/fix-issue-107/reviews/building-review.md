# Building Review — fix-issue-107

- 审阅轮次: **Round 1**
- 审阅对象: 分支 `fix-issue-107`，提交 `a95e8a3`（`git diff origin/master...HEAD`，单一提交）
- GitHub issue: #107 — Todo ContextSource (P5) 超预算时被截断，agent 可能丢失执行进度
- 审阅者: 独立零记忆 subagent
- 审阅日期: 2026-08-09

## Scope

修复内容：将 `agent/context/sources.py` 中 `TodoSource.priority` 从 5 提升到 2（与 `MemoryIndexSource` 同级），并在 `agent/loop.py` 的 `_make_default_context_builder` 中把 `TodoSource` 的注册移到 P2 区块（MemoryIndex 之后），新增回归测试于 `tests/agent/context/test_builder.py`。

审阅维度：正确性、Spec 对齐、冗余度、测试覆盖、安全性、可维护性、CI 完整性、边界条件。

## Verdict

**CHANGES_REQUESTED**

修复的核心逻辑正确且为最小修改：Todo 提升到 P2（非 cacheable、非 critical）后，在 `_apply_budget` 中只会在 P4/P5 全部裁完、预算仍超时才会被裁，确实解决了 issue #107 描述的执行进度丢失问题。相关测试全部通过，无安全与冗余问题。

但存在两项中等质量问题，修复前应处理：

1. **文档影响未同步（中等问题）**：仓库 AGENTS.md 明确规定收尾阶段必须检查文档影响，且本仓库为文档驱动型仓库（面试讲稿、agent-internals 均逐行镜像代码事实）。本次改动改变了 Todo 的层归属（P5→P2）与 P5 预算和（5K→4K），但 `docs/` 下仍有 7 处文档把 Todo 描述为 P5 层、把裁切顺序描述为"先裁 Todo（P5）"，与修复后行为矛盾（详见 Issues）。
2. **回归测试未绑定真实 `TodoSource`（中等问题）**：新测试用 `FakeSource(name="Todo", priority=2, ...)` 硬编码 priority=2，验证的是 ContextBuilder 的通用机制而非本次修复本身。若有人把 `TodoSource.priority` 改回 5，该测试仍会通过，无法拦住本次 bug 的回归。

不构成 BLOCKED：核心修复真实生效，测试全绿，无安全/性能缺陷，超预算截断顺序推理经模拟验证成立。

## Tasks Verification

本次为 bug fix，无 OpenSpec `tasks.md`（`openspec/changes/fix-issue-107/` 不存在，未立项）。故该项 **N/A**，以下改列修复目标验证：

| 修复目标 | 验证结果 |
| --- | --- |
| Todo 在执行进度丢失场景下存活（P4/P5 先被裁） | ✅ 逻辑验证通过。`_find_trimmable_index`（`builder.py:175-179`）从尾部向前找第一个非 critical 且非 cacheable 层；P2 Todo 非 cacheable 仍可被裁，但只排在 P4/P5 之后。模拟验证：层序 `[P0, P1, P2-Mem, P2-Todo, P4, P4, P5, P5]` 下裁切顺序为 PlanningState → PlanMode → SkillActive → SkillIndex → Todo → （MemoryIndex cacheable 停止） |
| cacheable 稳定前缀语义不受影响 | ✅ Todo 未设 `cacheable`，不进入稳定前缀；`build_blocks` 的 cache_control 断点仍在 MemoryIndex（P2 cacheable）之后，Todo 每轮重渲染且在断点之后，正确 |
| 注册顺序稳定 | ✅ `sorted()` 稳定，`loop.py:1347-1348` MemoryIndex 先于 Todo 注册，同 P2 下 MemoryIndex 在前，符合预期（记忆摘要在前、执行进度在后） |
| P5 预算注释算术 | ✅ `2500 + 1500 = 4000`（原 `2500 + 1500 + 1000 = 5000`），`sources.py:347` 注释 5K→4K 正确 |
| 回归测试 | ✅ 新增 `test_todo_p2_survives_after_p4_p5_trimmed` 通过；但存在绑定弱点（见 Issues #2） |

## Issues

### 1. [中] 文档未随修复同步，7 处仍把 Todo 描述为 P5 层 / 旧裁切顺序

本次修复改变了两个文档化事实：Todo 从 P5 移到 P2；P5 层预算和从 5K 变为 4K。`docs/` 下多处仍为修复前事实，与当前代码矛盾：

- `docs/agent-internals.md:515` — `builder.register(TodoSource(...))  # P5 — 执行进度 Todo`
- `docs/agent-internals.md:532` — 预算示例 `P5  Todo          : 1,000 tokens`
- `docs/agent-internals.md:543` — 注释 `# → 找到 P5 Todo (最末尾的普通层)`（修复后最末尾普通层是 PlanningState，非 Todo）
- `docs/agent-internals.md:552` — `先裁 Todo（P5），不够再裁 PlanningState（P5）…`（修复后裁切顺序颠倒）
- `docs/agent-internals.md:1600` — 架构图 `P5: PlanModeSource / PlanningStateSource / TodoSource — 规划状态`
- `docs/interview-script/walkthrough/W04-context-engineering.md:32` — 层表 `| P5 | TodoSource | 5 | ❌ | ❌ | — |`
- `docs/interview-script/walkthrough/self-test-QA.md:63` — `P5 PlanMode+PlanningState+Todo`

依据：AGENTS.md「文档影响检查」要求收尾阶段用关键词扫描 `docs/` 并更新本次变更造成的事实变化。本仓库面试讲稿与 agent-internals 逐行镜像代码事实，保留 7 处陈旧引用会误导后续阅读与面试准备。

建议：本次变更内同步更新上述文档（Todo 移入 P2 行/列、裁切顺序改为 PlanningState→PlanMode→SkillActive→SkillIndex→Todo、P5 预算 4K）。若属历史口径问题，按规则另记债务并说明。

### 2. [中] 回归测试未绑定真实 `TodoSource`，无法拦截 priority 回退

`tests/agent/context/test_builder.py:163-186` 新测试使用 `FakeSource(name="Todo", priority=2, ...)` 硬编码 priority=2。它验证的是 ContextBuilder 的通用优先级机制（P2 存活于 P4/P5 之后），但没有读取真实 `TodoSource.priority` 的定义。若把 `sources.py:389` 的 `priority = 2` 改回 5，该测试**仍会通过**，即本次 bug 修复本身缺乏回归保护。

另外第二处断言 `assert "SKILL_LIST" not in result or len(result) < 400`（`test_builder.py:186`）偏弱：它是一处长度代理断言（实测结果 337 字符），并非直接验证"裁切顺序"，且依赖 tiktoken 的 token 估算（`builder.py:15-24`），tiktoken 版本或字符内容变化时可能脆弱。

建议（二者取一或都做）：
- 增加一行 `assert TodoSource.priority == 2`（绑定数据变更本身）；或
- 截断测试中注册真实 `TodoSource(todo_renderer=...)` 而非 FakeSource。
- 可将第二断言改为直接验证顺序：例如预算只够 Todo 时，断言 P4/P5 被整层移除且 Todo 完整保留。

### 3. [低] `render_layers` docstring 与修复后行为略有出入

`agent/context/builder.py:74-79` docstring 声称 "the token budget only trims the variable P4/P5 layers"。Todo 提升到 P2 且非 cacheable 后，预算超限时 P4/P5 全部裁完仍可继续裁 Todo（P2），故该表述不再严格成立。`_apply_budget`（`builder.py:132-165`）与 `_find_trimmable_index`（`builder.py:167-179`）的 docstring 仍准确（cacheable 层不裁）。仓库规则要求代码注释准确，建议把该 docstring 改为"budget 优先裁 P4/P5，cacheable 稳定前缀不裁；非 cacheable 的 P2（Todo）在 P4/P5 裁完后也可能被裁"。

### 4. [低/建议] 集成层无 Todo 层级位置断言

`tests/agent/test_loop.py:1229-1256`（`test_todo_context_injected_in_build_mode`）只断言 `"## Current Progress" in contents` 的字符串存在性，未校验 Todo 在注入上下文中的相对层级位置。已有单元级机制测试覆盖，此项非必须；若希望集成层锁定 Todo 位于 MemoryIndex 之后、SkillIndex 之前，可补充位置断言。可选，不阻塞。

## Test Results

实际运行输出：

```
$ python3 -m pytest tests/agent/context/test_builder.py tests/agent/test_context_cache.py tests/agent/tools/test_todo_tool.py -q
..............................................                           [100%]
46 passed in 2.09s

$ python3 -m pytest tests/agent/test_loop.py -q -k 'todo'
.....                                                                    [100%]
5 passed, 57 deselected in 1.12s
```

补充验证：
- 单独运行新回归测试：`tests/agent/context/test_builder.py::test_todo_p2_survives_after_p4_p5_trimmed` 通过（1 passed）。
- 用真实 source 模拟超小预算（total_budget=100）：层序为 `[SystemPrompt(P0), Todo(P2), PlanMode(P5)]` 时，裁切顺序为 PlanMode → Todo，SystemPrompt（critical）保留；Todo 在 P4/P5 之后被裁的行为符合预期，不属回归。
- 环境检查：tiktoken 为 pyproject 声明依赖（`pyproject.toml:29`）且环境可用，token 估算路径稳定。

未发现与本修复相关的失败；无已知环境失败介入。

## Conclusion

修复方向正确、实现最小且核心逻辑经推理与模拟双重验证成立：`TodoSource` 提升到 P2 后，在 `_apply_budget` 中只会在 P4/P5 全部裁完、预算仍超限时被裁，从而解决 agent 丢失执行进度的问题。cacheable 稳定前缀语义、注册顺序、P5 预算注释算术均正确，无安全/冗余/性能问题，测试全绿。

**CHANGES_REQUESTED** 的核心理由：(1) 文档未同步——`docs/agent-internals.md`、`docs/interview-script/walkthrough/` 下 7 处仍把 Todo 描述为 P5 层/旧裁切顺序，违反仓库文档影响检查规则，且本仓库文档逐行镜像代码事实，需随修复更新；(2) 回归测试用 FakeSource 硬编码 priority=2，未绑定真实 `TodoSource`，无法拦截本次修复自身的回退。建议同步补充 `TodoSource.priority == 2` 断言并更新文档后复审。

## Review Evidence

- 变更 diff：`git diff origin/master...HEAD`（提交 a95e8a3，3 文件，+36/−6）
- `agent/context/sources.py:381-390` — TodoSource docstring + `priority = 2`
- `agent/context/sources.py:347` — PlanModeSource 预算注释（5K→4K，算术正确）
- `agent/loop.py:1346-1348` — 注册顺序调整 + P2 注释
- `agent/context/builder.py:132-179` — `_apply_budget` / `_find_trimmable_index`（P2 非 cacheable 仍可裁，排在 P4/P5 后）
- `tests/agent/context/test_builder.py:163-186` — 新增回归测试

# Building Review — fix-issue-107

- 审阅轮次: **Round 2**
- 审阅对象: 分支 `fix-issue-107`，审阅范围 `git diff origin/master...HEAD`（提交 a95e8a3 原始修复 + 1ac0120 审阅修复）
- GitHub issue: #107 — Todo ContextSource (P5) 超预算时被截断，agent 可能丢失执行进度
- 审阅者: 独立零记忆 subagent（Round 2，不继承 Round 1 结论，独立重审）
- 审阅日期: 2026-08-09

## Scope

修复内容：将 `agent/context/sources.py` 中 `TodoSource.priority` 从 5 提升到 2（与 `MemoryIndexSource` 同级但非 cacheable），在 `agent/loop.py` 的 `_make_default_context_builder` 中把 `TodoSource` 注册移到 P2 区块（MemoryIndex 之后），在 `tests/agent/context/test_builder.py` 新增两条回归测试（数据绑定 + 真实 source 截断顺序），并同步 `docs/agent-internals.md`、`docs/interview-script/walkthrough/W04-context-engineering.md`、`docs/interview-script/walkthrough/self-test-QA.md`，更正 `agent/context/builder.py` `render_layers` docstring。

审阅维度：正确性、Spec 对齐、冗余度、测试覆盖、安全性、可维护性、CI 完整性、边界条件。

## Verdict

**PASS**

修复真实生效、实现最小，Round 1 提出的两项中等质量问题（文档未同步、回归测试未绑定真实 `TodoSource`）已全部解决并经验证。全量相关测试 109 通过；回归测试经"改回 priority=5"实测能拦截回退。无未解决中等以上问题。

## Tasks Verification

本次为 bug fix，无 OpenSpec `tasks.md`（`openspec/changes/fix-issue-107/` 无 tasks.md，未立项，为直接修复）。该项 **N/A**，以下改列修复目标验证：

| 修复目标 | 验证结果 |
| --- | --- |
| Todo 在执行进度丢失场景下存活（P4/P5 先被裁） | ✅ 逻辑 + 实测双重验证。`_find_trimmable_index`（`builder.py:168-180`）从尾部向前找第一个非 critical 且非 cacheable 层；P2 Todo 非 cacheable 仍可裁，但只排在 P4/P5 之后。真实 token 实测：skill=151 / plan=101 / todo=15 tokens，budget=100 时裁切顺序为 PlanningState → SkillIndex（截尾），Todo 完整保留 |
| cacheable 稳定前缀语义不受影响 | ✅ Todo 未设 `cacheable` 属性（`sources.py:379-389`），`getattr(source, "cacheable", False)` 为 False，不进稳定前缀；`build_blocks` 的 `cache_control` 断点仍在 MemoryIndex（P2 cacheable，`sources.py:288`）之后，Todo 每轮重渲染且在断点之后，正确 |
| 注册顺序稳定 | ✅ `sorted()` 稳定（`builder.py:81`），`loop.py:1347-1348` MemoryIndex 先于 Todo 注册，同 P2 下 MemoryIndex 在前、Todo 在后，符合"记忆摘要在前、执行进度在后"预期 |
| P5 预算注释算术 | ✅ `sources.py:346` PlanMode 2500 + `sources.py:368` PlanningState 1500 = 4000，注释"shared in P5 4K budget with PlanningState"正确（原 5K 含 Todo 已移除） |
| 回归测试绑定真实 TodoSource 且能拦截回退 | ✅ `test_todo_source_priority_is_p2`（`test_builder.py:164-167`）直接断言 `TodoSource.priority == 2`；`test_real_todo_survives_after_p4_p5_trimmed`（`test_builder.py:169-192`）注册真实 `TodoSource` 并断言 P4/P5 被裁、Todo 完整。实测将 `sources.py:389` 改回 5：两条测试均 FAIL，改回 2 后恢复 PASS |
| 文档同步（Round 1 Issue #1） | ✅ 见 Issues 节，grep 复核无陈旧引用残留 |

## Issues

### 1. [低] `render_layers` docstring 措辞：P2 Todo 称"lower-priority"在数值上颠倒

`agent/context/builder.py:75-79`：

```python
``cacheable`` sources (P0/P1/P2, the stable prefix)
are frozen outside the budget pass — the token budget trims the
variable P4/P5 layers first and may continue into non-cacheable
lower-priority layers (e.g. Todo at P2) only after P4/P5 are fully
removed, ...
```

"lower-priority layers (e.g. Todo at P2)" 中，P2 数值上高于 P4/P5（0 = 最高），此处实指"排在 P4/P5 之后才裁"。含义可辨、实质正确（P4/P5 先裁、P2 Todo 后裁、cacheable 前缀不动），但"lower-priority"字面与优先级数值相反，建议改为"may continue into non-cacheable higher-priority layers (e.g. Todo at P2) only after P4/P5 are fully removed"。低严重度，不阻塞。

### 2. [低/建议] 集成层 Todo 注入测试仅断言字符串存在性

`tests/agent/test_loop.py:1229-1256`（`test_todo_context_injected_in_build_mode`）只断言 `"## Current Progress" in contents` 与任务标题存在，未校验 Todo 在注入上下文中的相对位置。已有单元级机制测试覆盖层级顺序，此项非必须；如需集成层锁定"Todo 位于 MemoryIndex 之后、SkillIndex 之前"可补位置断言。可选，不阻塞。

### 3. [低/观察] Q04 讲稿把 TodoSource 与计划类 source 归为"计划与待办"

`docs/interview-script/questions/Q04-context-engineering.md:41` 列 `PlanModeSource（343 行）/ PlanningStateSource（365 行）/ TodoSource（381 行）：计划与待办`。经核对：三处行号与当前 `sources.py` 完全一致（343/365/381），且该句只描述"渲染内容归属"，未声称 Todo 属于 P5 层；Q04 正文的"critical 永不截断、cacheable 稳定前缀"表述对 Todo 依然成立（Todo 非 critical/cacheable，仍可裁）。不算陈旧引用，无需修改。

未发现其他问题。Round 1 的全部 7 处陈旧文档引用（`docs/agent-internals.md:515/532/543/552/1600`、`W04:32`、`self-test-QA.md:63`）经 grep 复核均已更新为修复后事实（Todo 移入 P2、裁切顺序 PlanningState→PlanMode→SkillActive→SkillIndex→Todo、P5 预算 4K），无残留。

## Test Results

实际运行输出（Round 2 环境）：

```
$ python3 -m pytest tests/agent/context/test_builder.py tests/agent/test_context_cache.py tests/agent/tools/test_todo_tool.py tests/agent/test_loop.py -q
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 10.03s
```

回归拦截实测：

```
# 临时将 sources.py:389 改回 priority = 5 后运行 todo 相关测试：
$ python3 -m pytest tests/agent/context/test_builder.py -q -k 'todo'
FAILED tests/agent/context/test_builder.py::TestContextBuilderTruncation::test_todo_source_priority_is_p2
FAILED tests/agent/context/test_builder.py::TestContextBuilderTruncation::test_real_todo_survives_after_p4_p5_trimmed
2 failed, 16 deselected in 1.14s
# 还原 priority = 2 后：
$ python3 -m pytest tests/agent/context/test_builder.py -q -k 'todo'
2 passed, 16 deselected in 1.01s
```

新测试 token 鲁棒性实测（cl100k_base）：`todo_content` = 44 字符 / 15 tokens；`skill_content` = 550 字符 / 151 tokens；`plan_content` = 550 字符 / 101 tokens；budget=100。合计 ~267 tokens 超预算 167，P5 整层移除、P4 截尾至 ~286 字符，Todo（15 tokens）完整保留。即使 tiktoken 不可用走 chars/4 回退路径（skill/plan ≈ 138 tokens each），结论一致，测试不依赖精确估算。git status 干净（回退实验已还原）。

## Conclusion

修复方向正确、实现最小，核心逻辑经代码走查 + token 实测 + 回退实验三重验证成立：`TodoSource` 提升到 P2（非 critical、非 cacheable）后，在 `_apply_budget` 中只会在 P4/P5 全部裁完、预算仍超限时被裁，从而解决 issue #107 描述的执行进度丢失问题。cacheable 稳定前缀语义（断点仍在 MemoryIndex）、同 P2 注册顺序（MemoryIndex 在前）、P5 预算注释算术均正确。Round 1 的两项中等质量问题已解决：全部 7 处文档陈旧引用已同步；两条回归测试现分别绑定数据变更（`TodoSource.priority == 2`）与真实 `TodoSource` 截断顺序，实测能拦截 priority 回退。无安全/冗余/性能问题，测试全绿（109 passed），工作区干净。

**PASS**。剩余 3 项均为低严重度措辞/建议项，不构成阻塞。

## Review Evidence

- 变更 diff：`git diff origin/master...HEAD`（提交 a95e8a3 + 1ac0120，8 文件，+168/−20）
- `agent/context/sources.py:379-389` — TodoSource docstring（说明 P2 理由、引用 issue #107）+ `priority = 2`
- `agent/context/sources.py:346` — PlanModeSource 预算注释（5K→4K）
- `agent/loop.py:1346-1348` — P2 区块注册顺序（MemoryIndex → Todo）+ 注释
- `agent/context/builder.py:75-79` — `render_layers` docstring 更正（P4/P5 先裁、P2 后裁）
- `agent/context/builder.py:168-180` — `_find_trimmable_index`（非 critical 且非 cacheable 才可裁）
- `tests/agent/context/test_builder.py:164-192` — 两条回归测试（数据绑定 + 真实 TodoSource 截断顺序）
- 文档同步：`docs/agent-internals.md:511/528/552/1598`、`W04-context-engineering.md:28`、`self-test-QA.md:63`

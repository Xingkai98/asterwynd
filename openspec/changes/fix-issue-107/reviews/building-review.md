# Building Review — fix-issue-107

- 审阅轮次: **Round 4（最终确认）**
- 审阅对象: 分支 `fix-issue-107`，审阅范围 `git diff origin/master...HEAD`（6 个提交：a95e8a3 → e15d859）+ 工作区未提交的 manifest 与报告更新
- GitHub issue: #107 — Todo ContextSource (P5) 超预算时被截断，agent 可能丢失执行进度
- 审阅者: 独立零记忆 subagent（Round 4，不继承 Round 1/2/3 结论，对当前完整最终状态独立复核）
- 审阅日期: 2026-08-09

## Scope

最终确认审阅，覆盖全部 6 个提交 + 工作区未提交更新：

1. `agent/context/sources.py` `TodoSource.priority` 5 → 2（`sources.py:381-391`），docstring 说明 issue #107 动机；`PlanModeSource` 预算注释 5K → 4K（`sources.py:347`，算术 2500+1500=4000 正确）。
2. `agent/loop.py` `_make_default_context_builder` 注册顺序：`TodoSource` 移入 P2 区块（MemoryIndex 之后，`loop.py:1346-1348`）。
3. `agent/context/builder.py` `render_layers` docstring 更正（`builder.py:73-79`）。
4. `tests/agent/context/test_builder.py` 两条回归测试（`test_builder.py:164-192`）。
5. 文档同步：`docs/agent-internals.md`、`docs/interview-script/walkthrough/W04-context-engineering.md`、`docs/interview-script/walkthrough/self-test-QA.md`。
6. OpenSpec change 文档（`proposal.md`、`diagnosis.md`、`tasks.md`、`workflow-events.jsonl`）+ spec delta（`changes/fix-issue-107/specs/context-engineering/spec.md`）+ 当前规格同步（`openspec/specs/context-engineering/spec.md`）+ review manifest（`building-review-manifest.json`）+ 本审阅报告。

Round 3 唯一问题（review manifest 过期）已通过重新生成 manifest 修复，本次重点复核 manifest 一致性。

## Verdict

**PASS**

Round 3 唯一中等问题（review manifest 未绑定最终 head）已修复：manifest 现绑定 head `e15d859c`，`tasks_hash`、`spec_hash`、`diff_hash`、`report_hash` 全部与当前实际文件一致，`scripts/check_openspec_artifacts.py` 输出 "OpenSpec artifact checks passed"（exit 0）。代码修复、回归测试、文档同步、spec delta 相互一致，全部机械检查通过。

## Tasks Verification

| task（tasks.md 行号） | 验证结果 |
| --- | --- |
| `tasks.md:5` TodoSource.priority 5→2 + docstring | ✅ `sources.py:389`：`priority = 2`；`sources.py:381-387` docstring 引用 issue #107 |
| `tasks.md:6` spec delta 新增 Requirement | ✅ `changes/fix-issue-107/specs/context-engineering/spec.md` ADDED "执行进度保留（Todo 层级保护）"（2 个 Scenario） |
| `tasks.md:7` 当前规格同步 + workflow-events | ✅ `openspec/specs/context-engineering/spec.md:82-99` 与 delta 内容一致；`workflow-events.jsonl` 有 `current_spec_synced` 事件（approved_by: human） |
| `tasks.md:8` PlanModeSource 预算注释 5K→4K | ✅ `sources.py:347` "shared in P5 4K budget with PlanningState"；2500+1500=4000 算术正确 |
| `tasks.md:9` loop.py 注册移入 P2 | ✅ `loop.py:1346-1348`：P2 区块 MemoryIndex → Todo，注释同步（issue #107） |
| `tasks.md:10` render_layers docstring 更正 | ✅ `builder.py:73-79`：P4/P5 先裁，P4/P5 裁完才继续裁非 cacheable 的 P2 Todo，表述与代码语义一致 |
| `tasks.md:14` 新增 `test_todo_source_priority_is_p2` | ✅ `test_builder.py:164-167`：断言 `TodoSource.priority == 2` |
| `tasks.md:15` 新增 `test_real_todo_survives_after_p4_p5_trimmed` | ✅ `test_builder.py:169-192`：真实 `TodoSource` + FakeSource(P4/P5)，断言 P4/P5 被裁、Todo 完整存活 |
| `tasks.md:16` 验证回归测试有效性（改回 5 失败） | ✅ Round 4 实测：priority 改回 5 → 两条测试均 FAIL；还原 → 恢复 PASS（见 Test Results） |
| `tasks.md:17` 相关测试全绿 109 | ✅ Round 4 实测 109 passed |
| `tasks.md:21/22/23` 三处文档同步 | ✅ `agent-internals.md:511/528/552/1598`、`W04-context-engineering.md:28`、`self-test-QA.md:63` 均为 P2 Todo + 新裁切顺序；grep 复核 live 文档无"Todo 是 P5"的陈旧现状引用 |
| `tasks.md:24` 审阅报告与 manifest 存在 | ✅ 两份文件存在且本轮已更新为 Round 4 PASS（见下文 manifest 一致性） |
| `tasks.md:31` 生成 review manifest 绑定 base/head · 内容 hash | ✅ `building-review-manifest.json` head_sha=`e15d859c...`==HEAD，tasks/spec/diff/report hash 全部实算一致（见 Issues → No issues） |
| `tasks.md:37` OpenSpec artifact checker 通过 | ✅ Round 4 实测 "OpenSpec artifact checks passed"，exit 0 |

## Issues

No issues found.

## Manifest 一致性（Round 3 唯一问题的复核）

独立重算验证（非仅依赖 checker 输出）：

| 字段 | manifest 值 | 实算值 | 一致 |
| --- | --- | --- | --- |
| `base_sha` | `3662f38c65a415e89309bcea455b8a7da172056f` | `git rev-parse origin/master` 同值 | ✅ |
| `head_sha` | `e15d859c487ea1b29a07e5f4772d9422d4d461e2` | `git rev-parse HEAD` 同值 | ✅ |
| `tasks_hash` | `sha256:6119c551bb1a3391b4caf0e9b3ba7c910462ef1082c5672ef1e9fef2bbe67636` | `file_sha256(tasks.md)` 同值 | ✅ |
| `spec_hash` | `sha256:44708dc1e3b8588c1b989e50eeb583e3309632add7eaa3a67db23726a3429054` | `artifact_hash(specs/)`（目录组合 hash，含 rel path + 各文件 hash）同值 | ✅ |
| `diff_hash` | `sha256:b275ebfca9e5bb0d847d06967c0651d0fbcfbaf7c5319a44dd834683ac0142bd` | `git diff --binary base..head | sha256sum` 同值 | ✅ |
| `report_hash` | 本轮随新报告更新 | 与 `reviews/building-review.md`（Round 4）一致 | ✅ |
| `verdict` | `PASS` | 与本报告 `## Verdict` 一致 | ✅ |

注：`spec_hash` 在 `agent/workflow/review_manifest.py` 中对 `change_dir/specs/` 目录计算（`artifact_hash`），非单个 spec 文件的裸 hash——Round 3 报告中 `sha256:missing` 的问题即源于该目录当时不存在，现已可正常计算。

`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 输出 "OpenSpec artifact checks passed"，exit 0。

## 正确性 / Spec 对齐 / 边界条件（独立复核）

- 修复真实生效：`_find_trimmable_index`（`builder.py:176-180`）从尾部向前找第一个非 critical 且非 cacheable 层；`_apply_budget`（`builder.py:118-152`）优先移除/截断最低优先级可裁层。Todo（P2，非 critical、非 cacheable）只在 P4/P5 全部移除后仍超预算时才被裁。
- 回归测试实测（Round 4 复现）：`priority` 改回 5 后 `test_real_todo_survives_after_p4_p5_trimmed` 的失败输出显示 `todo_content` 被整层裁掉（result 只剩 SKILL_LIST），正是 issue #107 描述的 bug 症状，证明测试真实绑定修复行为。
- cacheable 稳定前缀语义不变：MemoryIndex（P2，`cacheable=True`，`sources.py:288`）永不裁；`build_blocks` cache 断点语义未变。
- 同 P2 注册顺序稳定：`sorted()` 稳定（`builder.py:81`），MemoryIndex 先注册（`loop.py:1347`）在前、Todo 在后，符合"记忆摘要在前、执行进度在后"。
- spec delta 与 `openspec/specs/context-engineering/spec.md` 内容逐字一致（同一 Requirement + 2 个 Scenario），与代码行为一致（Scenario 2 "预算极端紧张时 todo 最后才被裁" 与 `_apply_budget` 循环行为一致）。
- `proposal.md`：Why/What Changes/Modified Capabilities/Impact Analysis 与 diff 逐项对应；Reference Research `status: disabled` 理由充分（内部优先级数值调整，issue #107 已列三个候选方案并说明选用理由）。
- `diagnosis.md`：Symptom/Reproduction/Evidence/Root Cause/Recommended Direction 对修复前状态（P5 Todo）的描述均为历史事实；备选方案（critical 标记 / 截断层加权 / 合入 PlanningState）的否决理由成立。
- live 文档无陈旧 "Todo 为 P5" 现状引用：grep `todo.*p5|p5.*todo` 命中均为修复前历史描述（proposal/diagnosis）或正确的新裁切顺序（P5 规划层在 Todo 之前被裁）；`docs/agent-internals.md:552`、`W04:28`、`self-test-QA.md:63` 均为 P2 Todo。

## Test Results

Round 4 实际运行输出：

```
$ python3 -m pytest tests/agent/context/test_builder.py tests/agent/test_context_cache.py tests/agent/tools/test_todo_tool.py tests/agent/test_loop.py -q
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 10.44s
```

回归拦截实测（Round 4 独立复现）：

```
# 临时将 sources.py TodoSource.priority 改回 5 后：
$ python3 -m pytest tests/agent/context/test_builder.py -q -k 'todo'
FAILED ...::TestContextBuilderTruncation::test_todo_source_priority_is_p2
FAILED ...::TestContextBuilderTruncation::test_real_todo_survives_after_p4_p5_trimmed
2 failed, 16 deselected in 1.08s
# 还原 priority = 2 后：
$ python3 -m pytest tests/agent/context/test_builder.py -q -k 'todo'
2 passed, 16 deselected in 1.00s
```

还原后 `git diff --stat agent/context/sources.py` 无差异，工作区干净。

OpenSpec 校验：

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)
```

Artifact checker：

```
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed
EXIT=0
```

## Conclusion

Round 3 的唯一中等问题（review manifest 未绑定最终 head，`spec_hash` 为 `sha256:missing`）已修复：manifest 现绑定 head `e15d859c`（= 当前 HEAD），`tasks_hash` / `spec_hash`（specs 目录组合 hash）/ `diff_hash` / `report_hash` / `verdict` 经独立重算全部一致，artifact checker 通过。

代码修复正确、最小：`TodoSource` 提升到 P2（非 critical、非 cacheable）后，仅在 P4/P5 全部裁完、预算仍超限时才被裁，真实解决 issue #107 的执行进度丢失问题。两条回归测试绑定数据变更（`priority == 2`）与真实 `TodoSource` 截断顺序，改回 priority=5 两条均失败（失败输出复现 todo 整层被裁的原 bug 症状），能有效防回退。文档（agent-internals / W04 / self-test-QA）与 spec delta、proposal、diagnosis、tasks 相互一致，live 文档无陈旧 P5 Todo 现状引用。pytest 109 通过、OpenSpec strict validate 30/30 通过、artifact checker 通过。

**PASS** — 无未解决问题，可以合入。

## Review Evidence

- 变更 diff：`git diff origin/master...HEAD`（6 提交，15 文件，+323/−20）+ 工作区 manifest 与报告更新
- `agent/context/sources.py:381-391` — TodoSource P2 + docstring（引用 issue #107）；`sources.py:347` — PlanModeSource 预算注释（P5 4K）
- `agent/loop.py:1346-1348` — P2 注册顺序（MemoryIndex → Todo）+ 注释
- `agent/context/builder.py:73-79` — `render_layers` docstring；`builder.py:118-152` — `_apply_budget`；`builder.py:176-180` — `_find_trimmable_index`
- `tests/agent/context/test_builder.py:164-192` — 两条回归测试
- `openspec/changes/fix-issue-107/reviews/building-review-manifest.json` — head_sha/tasks_hash/spec_hash/diff_hash/report_hash 全部实算一致
- `openspec/changes/fix-issue-107/specs/context-engineering/spec.md` 与 `openspec/specs/context-engineering/spec.md:82-99` — spec delta 与当前规格逐字一致
- `openspec/changes/fix-issue-107/workflow-events.jsonl` — `current_spec_synced` 事件（approved_by: human）
- 文档同步：`docs/agent-internals.md:511/528/552/1598`、`W04-context-engineering.md:28`、`self-test-QA.md:63`

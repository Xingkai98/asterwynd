# Building Review: foreach-budget-truncation-visibility（Round 2）

- 执行者：独立零记忆代码审阅 subagent（/review-loop 等价流程）
- 分支：foreach-budget-truncation-visibility/2026-10-03
- base: ced78aa / head: da428afd01db7788c4527f68e0a2809c29ed5b0e
- 本轮复核对象：`git diff e0c938d...da428af`（Round 1 head → Round 2 head，即 3 条 Low 的修复 commit）
- 方法：读 Round 2 增量 diff、确认无行为改动、真跑目标测试 + 全 subagent 套件、独立探针复算三出口、跑门禁

## Verdict
PASS

## Round 2 复核：3 条 Low 的修复结论

| Low | 修复目标 | 结论 | 证据 |
|---|---|---|---|
| **Low-1** | `NodeState.items_declared` docstring 改为「两条截断路径都记 declared」 | **已修好，无行为改动** | `agent/subagent/scheduler.py:250-256` 注释已改为「**两条截断路径都记本字段**：`max_items > 0` 的静态截断与 `max_items == 0` 的预算截断…成因由 `items_omitted_cause` 区分」。增量 diff **仅注释行**（`:250-256` 全为 `#:` 前缀），非注释改动行数 = 0（见 Test Results 的 grep 证据），无任何行为变化 |
| **Low-2** | dry-run 静态成因断言 `items_omitted_cause == "max_items"` | **已修好，是真锁** | `tests/agent/subagent/test_foreach_truncation_visibility.py:254` 新增 `assert fan["items_omitted_cause"] == "max_items"`（在 `test_dry_run_reports_declared_expanded_omitted` 内）。在 base `ced78aa` 上单跑该用例 → **FAILED: KeyError: 'items_omitted_cause'**，证明是真断言、非恒真 |
| **Low-3** | 测试文件头 docstring 扩为「#279 静态 + #286 预算」、出口清单含 `RunWorkflow` 信封 | **已修好** | 头部首行改为「issue #279 静态截断 + issue #286 预算截断」；正文列「覆盖两条截断路径、三/四条模型可见出口」，出口清单已含「**运行期 `RunWorkflow` 结果信封**（`nodes` 里的 foreach 节点，#286 OQ2=(b) 新增出口）」；dry-run 出口补 `items_omitted_cause` |

**是否引入新问题：无。** 本轮增量严格限于上述 3 处：`scheduler.py` 仅注释、测试文件仅 docstring + 1 条 `assert`。生产代码 `agent/tools/builtin/subagents.py` 自 Round 1 起**零改动**（`git diff e0c938d...da428af -- agent/tools/builtin/` 为空）。

## 三出口实测（Round 2 head 复算，独立探针）

预算截断确定性图（字面 60 + 上游 planner + `max_items=0` + `max_runs=25`）：

```
DRY RUN    : {'items_declared': 60, 'items_expanded': 24, 'items_omitted': 36, 'items_omitted_cause': 'budget'}
RUNWORKFLOW: {'items_declared': 60, 'items': 24,       'items_omitted': 36, 'items_omitted_cause': 'budget', 'reason': None}
GETWORKFLOW: {'items_declared': 60, 'items': 24,       'items_omitted': 36, 'items_omitted_cause': 'budget', 'reason': None}
```

三出口语义一致报「声明 60 / 展开 24 / 省略 36」+ 成因 `budget`；`RunWorkflow` 信封与 `GetWorkflow(detail='nodes')` 的 `reason` 仍为 `None`（终态原因键未被成因字段覆盖）。

## Test Results

```
# 目标测试（Round 2 head）
.venv/bin/python -m pytest tests/agent/subagent/test_foreach_truncation_visibility.py \
    tests/agent/subagent/test_dynamic_foreach.py tests/agent/subagent/test_foreach_item_refs.py -q
→ 43 passed in 5.04s

# 全 subagent 套件（无回归）
.venv/bin/python -m pytest tests/agent/subagent/ -q -p no:randomly
→ 849 passed in 31.81s

# Low-2 真锁验证：base ced78aa 上单跑新断言
→ FAILED test_dry_run_reports_declared_expanded_omitted：KeyError: 'items_omitted_cause'

# Low-1 无行为改动验证：scheduler.py 增量 diff 的非注释行
git diff e0c938d...da428af -- agent/subagent/scheduler.py | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -v '^[+-]\s*#'
→ （空）

# 测试计数不变（仍 25）
→ 25 tests collected

# 门禁
npx --yes @fission-ai/openspec@1.4.1 validate --all --strict  → 29 passed, 0 failed
PYTHONPATH=. .venv/bin/python scripts/check_openspec_artifacts.py
→ ERROR: foreach-budget-truncation-visibility: review manifest missing:
        openspec/changes/foreach-budget-truncation-visibility/reviews/building-review-manifest.json
```

**关于上述 checker ERROR（非缺陷，属流程中间态）**：该报错由**本报告文件 `building-review.md` 的存在**单独触发——把报告临时移开后 checker 复跑 → `OpenSpec artifact checks passed`。按仓库约定，review manifest 在**审阅通过后**由 review-loop 生成（绑定 reviewer run / base·head sha / tasks·spec·diff·report hash）。故这是「报告已在、manifest 待生」的正常中间态，非本 change 引入的问题；**收尾前需生成 `building-review-manifest.json` 使 checker 转绿**（协调者步骤 4.1 的 follow-up）。

## 结论

- **Verdict = PASS。** Round 1 的 3 条 Low 已全部真实修复，且**未引入新问题**：改动仅限一处注释、一处测试 docstring、一条测试断言；生产代码零变化。
- 三出口在 Round 2 head 上实测仍一致报「声明/展开/省略」三元 + 成因；`reason` 未被覆盖；静态路径既有字段值不变（Round 1 已验证，本 commit 未触碰该逻辑）。
- 唯一需协调者跟进的流程项：生成 review manifest（checker 中间态报错即源于此，非代码缺陷）。

---

## 附录：Round 1 报告摘要（保留历史结论）

- Round 1 head: `e0c938d`；verdict = **PASS**，3 条 Low。
- Round 1 关键验证（均通过）：`items_omitted_cause` 与 `reason` 不碰撞（探针实测两键共存）；`RunWorkflow` 信封后写真绕开 `_bounded_node`（信封带三元 + 成因，base 上该出口连 #279 静态字段都没有）；静态路径值不变；`items_omitted` ≠ `item_refs_omitted`；T1 构造确定性（连跑 3 次全绿）；6 条新断言在 base 全红（真回归）。
- Round 1 测试：目标 43 passed；全量 `2 failed, 3979 passed, 9 skipped`，2 处失败为预存在 `/tmp` 环境问题（`tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` 与 `::test_malformed_git_file_falls_back_to_scan`），与本 change 无关。
- Round 1 发现并已在 Round 2 修复的 3 条 Low：陈旧注释（`scheduler.py:252-254`）、dry-run 静态成因缺直接断言、测试文件头 docstring 口径偏旧。

## 附：审阅独立性声明

本轮为独立零记忆 subagent，未继承开发上下文；未改动任何源码/测试/change 文档（除本报告外工作树 clean），仅写入本报告。所有「实测」结论均由本次真跑命令或独立探针得出，未采信 change 文档或协调者的自述。

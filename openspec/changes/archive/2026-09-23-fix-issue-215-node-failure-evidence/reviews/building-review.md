# Building Review: fix-issue-215-node-failure-evidence（最终报告 · 审阅闭环汇总）

## Reviewer

- run id: review-subagent-215（最终轮 `review-subagent-215-r6`）
- 时间: 2026-09-23 ~ 2026-09-24
- 机制: 每轮都是**独立零记忆 subagent**（paseo 托管 `claude/claude-fable-5[1m]`），在**隔离检出**
  `/tmp/rev-215` 里工作——审阅者不继承开发上下文，也不写开发工作区（前三轮曾出现审阅者的变异改动
  留在开发树里的事故，自 R2 起改为隔离检出口径）。
- 历轮分报告: `building-review-r1.md` … `building-review-r6.md`（逐轮原文，本文件是汇总与最终 verdict）。

## Verdict

**PASS**

## 审阅轮次与 head 的对应关系（显式记录，不留猜测空间）

manifest 绑定**最终 head**；下表说明每轮被 PASS 的树与之后 commit 的关系：

| 轮次 | verdict | 审阅范围 | 该轮之后的提交 |
|---|---|---|---|
| R1 | CHANGES_REQUESTED（1 中 + 3 低） | `1a7df92..c37c267` | `bea27d6` 修复 + 回归 |
| R2 | CHANGES_REQUESTED（2 中 + 4 低） | `..bea27d6` | `80d2c2b` 修复 + 回归 |
| R3 | CHANGES_REQUESTED（1 中 + 5 低） | `..80d2c2b` | `e892e00` 修复 + 回归 |
| R4 | **PASS**（37 条变异 36 杀） | `1a7df92..e892e00` | `63b098d`、`05882d9` — 4 条低危修复（含 `failureCountHint` 措辞口径「工具失败」→「工具/LLM 失败」） |
| R5 | **PASS**（post-PASS 定向确认，9 个变异检查点无存活） | `e892e00..05882d9` | `91ce796` — 测试基础设施（确定性视图守卫）+ 订正一条假注释 |
| R6 | **PASS**（定向确认，无中等及以上） | `05882d9..91ce796` | 仅订正 R6 指出的两处注释引用错误 + 本报告与轮次记录（**注释/文档，无行为变更**） |

**如实说明（供合入者判断）**：R4/R5/R6 均判 PASS。其后 commit 的类别：R4→`63b098d`/`05882d9` 是低危
修复（唯一与行为相关的是线索措辞，已由 R5 定向确认）；R5→`91ce796` 是浏览器测试守卫（R6 已确认不旁路
产品行为）；R6→最终 head 是**注释订正 + 文档**，零行为变更（`test_workflow_graph_browser.py` 的 25 条
用例在提交前重跑通过）。即：**PASS 覆盖的代码行为 ≡ 合入的代码行为**。

## 闭环产出（逐轮修复与验证）

三轮 CHANGES_REQUESTED 共修 **4 中 + 12 低**，每条都补了**可失败的回归测试**并用变异验证实测：

- **R1**：`failure_count` 逃过 `_reset_subtree`（重跑期间前端会显示上一轮的失败线索，
  实测 `status=pending` 配 `failure_count=7`）→ 复位 + 回归（删复位行必红）。
- **R2**：候选行渲染块**零覆盖**（fixture 缺键，`if (evidence)` 恒假）、前端**零消费**后端
  `message`（D1 要求的「尚未派发 vs 取不到记录」区分在 UI 层落空）→ 各补用例 + 变异变红。
- **R3**：**头号交付物**（「对话」tab 的失败证据正文区）零覆盖——删条目列表/删文本/关截断页脚/
  去标题条数，四条变异在 949 条测试下存活 → 补正文区用例；并**顺带修掉一个真 bug**：
  `failureItemSummary` 把首行无界塞进摘要、绕过 Q2 用户确认的 300 字符预览上限（实测渲染 670 字符）。

## 最终验证（R6 之后、合入前）

- **任务逐项**：`tasks.md` 的每个 `[x]` 都有对应实现与用例（逐轮读代码确认，非只看文件名）。
- **Spec 对齐**：spec delta 的 9 个 Scenario 全部有实现与用例；`openspec validate --all --strict` **30 passed**。
  含七态枚举、`failure_evidence` 键名与条目字段名、`text_truncated`、候选轻量 vs 下钻完整、
  以及「SHALL NOT 改变前端取数时机」（懒加载，浏览器用例守护）。
- **变异验证**：累计 **60+ 条**变异（R4 37 条、R5 9 条检查点、R6 抽查 + 各轮修复自带），
  存活项均已处置为「真修复」或「明确记为不阻塞并说明理由」；最终**无已知假保护**。
- **测试**：`tests/web_tests/` + `tests/agent/subagent/` **954 passed / 7 skipped**；
  全量 pytest 的失败经逐类定性为**环境性/既有**（见下）。
- **安全性**：前端失败证据渲染全部走 `textContent`（零 `innerHTML`）；投影只读、不调 LLM、
  不写盘、不改执行状态（有测试锁定）。
- **CI 完整性**：未弱化任何 CI 配置。

## 已知环境性失败（不计入本 change）

1. `tests/agent/memory/test_persistent.py::TestFindScopeRoot::*` — 本环境 `/tmp` 被 git-dir 探测命中
   （`assert PosixPath('/tmp') is None`），master 上同样失败。
2. `tests/agent/tools/test_factory_sandbox_wiring.py::*docker*`、
   `tests/agent/tools/test_sandbox_backends.py::*docker*` — 本环境 `docker info` 不可用。
3. `tests/web_tests/*browser*.py` 的间歇 flake — 仓库既有现象（同一棵树两次跑挂的不是同一批用例）。
   本 change **已治住其中一半**（「渲染了但被切走」这类，补确定性视图守卫）；
   另一半（切换目标本身无行为断言）是既有缺口，记入 `docs/known-debt.md`，本 change 显式不做。

## 遗留（不阻塞合入，已落盘）

- `docs/known-debt.md`：`switchToWorkflowView` 只有字符串匹配断言、无行为测试（既有缺口，非本 change 引入）。
- R5 低 5 的口径残差（`design.md:246` 等处仍引用历史措辞「工具失败」）：属历史引用，
  实现者已按收敛纪律声明不做，不影响事实准确性。

## 结论

**PASS** — 本 change 的头号交付物（workflow 节点失败证据投影）已实现、被 spec 覆盖、
被可失败的测试守护，且「无失败证据」的七态枚举不折叠「没数据」与「没失败」。
审阅闭环 6 轮收敛，无未解决的中等及以上问题。

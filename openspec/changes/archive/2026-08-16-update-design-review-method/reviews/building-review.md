# Building Review: update-design-review-method

## Verdict

**PASS**（Round 1 独立审阅）

本 change 为遗留流程 change：设计追问工具从 `grill-with-docs` 切换为 `batch-grill-me`。核心变更已全部生效在 master（本 worktree 分支与 master 对齐，HEAD=4f99882，无新增实现 commit）。本次收尾为归档 + 审阅闭环，不新增功能。

tasks 1.1-2.3 均有真实文件/代码支撑（逐文件核对，见 Per-Task Verification）；相关测试全通过；无中等以上未解决问题。发现 3 项低严重度文档/措辞问题（见 Issues，均为 minor，不阻塞合入）。其中 Issue #1（描述串陈旧文案）已作为审阅后加固修复（见 Issues 节），加固后复测 107 passed 全绿。

## Scope

- 审阅对象：遗留流程 change `update-design-review-method` 的实现 commit `417b16c`（"流程：设计追问工具从 grill-with-docs 切换为 batch-grill-me"，30 文件 +220/-42）与 HEAD 当前生效态。
- base = HEAD = `4f99882`（`4f9988256ea0da451e52b51bacd1dce9e6ba7724`，与 origin/master 对齐）
- head = HEAD = `4f99882`
- reviewer run id：`review-update-design-review-method-20260816-1`
- 审阅维度：任务逐项验证 / 正确性 / Spec 对齐 / 冗余度 / 测试覆盖 / 安全性 / 可维护性 / CI 完整性

## Per-Task Verification

### 1. 文档同步

- **[x] 1.1 `AGENTS.md`：设计追问规则、自然语言路由表、worktree 阶段方法表**
  - 通过。设计追问规则（`AGENTS.md:18`）已切换为 `batch-grill-me`（含机械强制 /grill 独立 subagent、停轮确认、分支纪律，均为后续 change 增强，与 batch-grill-me 语义一致）；自然语言路由表（`AGENTS.md:72` "开始开发 / 实现这个 change" 行、`:77` 强调行）为 `batch-grill-me`；worktree 阶段方法表（`AGENTS.md:96` planning 行）为 `batch-grill-me`；主干流程表（`AGENTS.md:96`）proposal/design 阶段标注 `batch-grill-me`。
  - 全文 grep 确认无 `grill-with-docs` 残留（除检查器兼容关键字与历史归档）。

- **[x] 1.2 `docs/requirements-process.md`、`docs/agents/domain.md`、`openspec/project.md`、`openspec/templates/tasks.md`**
  - 通过。`docs/requirements-process.md` 共 5 个 hunk 全部切换（步骤 6、开发前设计追问节、自然语言路由表、脚本检查描述、禁止项），当前态 grep 无残留；`docs/agents/domain.md:11,25` 为 `batch-grill-me`；`openspec/project.md:56,62` 为 `batch-grill-me`；`openspec/templates/tasks.md:5` 为 `batch-grill-me`。

- **[x] 1.3 6 个 wayfinder change（tool-governance-deepening 等）的 design.md / tasks.md 引用**
  - 通过。实际同步了 7 个 wayfinder change（提交信息写 "6 个"，见 Issues #2）：add-minimal-tui-runtime-view、context-engineering-deepening、long-term-memory-deepening、multi-agent-collaboration、observability-deepening、sandbox-hardening、tool-governance-deepening。每个 change 的 design.md（`## Pre-Implementation Review`）与 tasks.md（8.1 pre-implementation 审阅任务行）均已从 `grill-with-docs` 切换为 `batch-grill-me`。

- **[x] 1.4 3 个流程规格：`openspec/specs/change-documentation/spec.md`、`dev-workflow-state-machine/spec.md`、`subagents/spec.md`**
  - 通过。commit `417b16c` 对 3 个受保护 spec 做了最小语义替换（`grill-with-docs is available/unavailable` → `batch-grill-me is available/unavailable`；planning sub_state 追问行；Reviewer agent 独立评审非执行 batch-grill-me）。HEAD 当前态均保留 batch-grill-me 语义：
    - `openspec/specs/change-documentation/spec.md:71-74`（Scenario: batch-grill-me is unavailable）
    - `openspec/specs/dev-workflow-state-machine/spec.md:187`（batch-grill-me 或等价设计追问 SHALL 在 exploring 到 writing_design 期间完成）
    - `openspec/specs/subagents/spec.md:79`（Reviewer agent 独立评审，而非执行 batch-grill-me）

### 2. 机械检查同步

- **[x] 2.1 `scripts/check_openspec_artifacts.py`：`_has_design_review_task` 接受 `batch-grill` 子串 + 错误文案**
  - 通过。`_has_design_review_task`（`scripts/check_openspec_artifacts.py:645-651`）同时匹配 `"grill-with-docs"`、`"batch-grill"`、`"等价设计追问"`（向后兼容历史 change）。错误文案更新为 `"tasks.md missing pre-implementation batch-grill-me (grill-with-docs) or equivalent design review task"`（`:760`）。
  - 正确性复核：`batch-grill` 子串天然匹配 `batch-grill-me`；旧关键字保留不破坏历史 change。后续 `grill-enforcement`（master 已生效）在此之上增加结构化证据优先逻辑，并在 fallback 注释显式标注 `# Fallback (compat with update-design-review-method, in-flight changes)`（`:756`）——两 change 兼容性成立。

- **[x] 2.2 `scripts/workflow_methods.json`：planning exploring 方法映射为 `/batch-grill-me`**
  - 通过。`scripts/workflow_methods.json:94` `planning.exploring.method = "/batch-grill-me"`，hint 同步更新（"设计树逐轮追问…一轮问整个 frontier"）。

- **[x] 2.3 测试断言文案同步（`test_openspec_artifact_checker.py`）**
  - 通过。`tests/test_openspec_artifact_checker.py:741` 断言错误文案与检查器 `:760` 完全一致。旧关键字兼容夹具保留（`:598, :636, :667, :701, :724` 用 `grill-with-docs` 均通过）；`batch-grill` 接受性有专门用例（`:821, :836`）；issue #95 结构化证据优先用例保留（`:745, :790`）。

### 3-4. 验证与收尾

- 3.1/3.2 由收尾 agent 验证（我复验：见 实测结果）。
- 3.3/4.1/4.2 由收尾 agent 刚勾选（对应本次验证），4.3「提交本次变更」未勾（提交在收尾最后完成）——按任务说明不视为缺陷。

## Issues

- **✅ 已修复（审阅后加固）[Low] `agent/workflow/doc_artifact_protocol_openspec.py:113`** — ContentRequirement 描述串原为 `"Must include grill-with-docs design review task"`。该描述仅用于 `file_exists` 检查的 `detail` 输出，实际内容检查委托给 `check_change` → `_has_design_review_task`（兼容逻辑），无功能影响。修复：改为 `"Must include batch-grill-me (or grill-with-docs) design review task"`，措辞与 checker `:760` 对齐，落在本 change「同步所有引用该工具的文档与机械检查逻辑」范围内。加固后 `tests/test_check_phase_done.py` + `tests/test_openspec_artifact_checker.py` **107 passed**（无测试断言该描述串）。

- **[Low] commit `417b16c` 提交信息数量** — 提交信息写 "6 个 wayfinder change"，实际 diff 同步了 7 个（add-minimal-tui-runtime-view、context-engineering-deepening、long-term-memory-deepening、multi-agent-collaboration、observability-deepening、sandbox-hardening、tool-governance-deepening）。纯措辞问题，不影响代码/文档正确性。

- **[Low] design.md Non-Goals 引用不存在的文件** — `design.md:17` Non-Goals 写 "不改 `docs/research/agent-engineering-best-practices-2026-07.md`（历史调研记录）"，但 `docs/research/` 已被移出版本控制，HEAD 不存在该目录/文件。历史说明性陈述，无实际影响，可忽略或改为记录"历史调研报告已移出版本控制"。

## 实测结果

（本审阅实际运行，环境：`PATH=/home/happy/.local/bin:$PATH` + `.venv/bin/python`）

- `pytest tests/test_openspec_artifact_checker.py -q` → **79 passed**（3.1 相关，全绿）
- `pytest tests/test_check_phase_done.py -q` → **28 passed**（含 `grill-with-docs` 夹具兼容验证）
- `pytest tests/test_workflow_guard.py -q` → 23 passed, **2 failed** = `test_guard_noops_when_workflow_disabled`、`test_guard_resume_audit_no_longer_blocks_writes`。失败 stderr 明确指向本分支名映射到 `update-design-review-method`（active、有 spec delta、无 reviews/grill-design.md）导致 guard fail-closed——即任务说明中的"分支上下文伪影"，**非本 change 缺陷**。
- 全量 `pytest -q`（deselect 上述 2 个已知失败）→ **1987 passed, 7 skipped**，无其他失败。
- `pytest tests/agent/mcp/test_mcp_manager.py -q` → **11 passed**（PATH 加 ~/.local/bin 后通过，复验任务说明的已知环境项 a）。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**（含 `change/update-design-review-method`）。
- `python3 scripts/check_openspec_artifacts.py`（无参数）→ **OpenSpec artifact checks passed**（tasks 4.3 未勾、change 尚未归档态）。
- 审阅后加固复测：`pytest tests/test_check_phase_done.py tests/test_openspec_artifact_checker.py -q` → **107 passed**（Issue #1 描述串修复后全绿）。

## Other Notes

1. **本 change 自身 tasks.md 通过设计审阅字面检查的机制**：其 tasks.md 文本含 "grill-with-docs 切换为 batch-grill-me"（标题），被 `_has_design_review_task` 的 `"grill-with-docs" in lowered` 匹配而返回 True。属"字面 marker 即过"的纸糊墙性质，但这是本 change 向后兼容设计的预期产物（与 design.md Decision 1/2 一致），且后续 `grill-enforcement` 已把完成态 change 升级为结构化证据验证。

2. **收尾顺序门禁观察（操作提示，非缺陷）**：本 change primary 类型 `process` ∈ DESIGN_TYPES，且有 spec delta（change-documentation）。一旦 tasks 全勾（含 4.3）且仍处 active，artifact checker 的 `_check_design_review_task`（`scripts/check_openspec_artifacts.py:750-754`，grill-enforcement 逻辑）会因缺 `reviews/grill-design.md` 而 fail（已模拟复现：`['reviews/grill-design.md missing — …']`）。CI 不跑 `--check-archived`，且 `iter_change_dirs` 过滤 archive 目录——因此收尾 agent 在最终全量 checker 运行/提交前**先归档本 change** 即可规避；这与任务清单第 4 步"归档 change + change_archived 事件"一致。若在勾选 4.3 后、归档前运行 checker，会命中该门禁。设计上本 change 明确"无需完整 batch-grill-me 追问"（design.md Pre-Implementation Review），不属实现缺陷。

3. **workflow-events.jsonl 事件与受保护修改对应**：4 个事件（3 个 `current_spec_synced` + 1 个 `backlog_updated`）逐一核对：seq 1/2/3 分别对应 commit 中 `openspec/specs/change-documentation/spec.md`、`dev-workflow-state-machine/spec.md`、`subagents/spec.md` 的实际 diff，reason 描述与 diff 语义吻合；seq 4 说明本流程 change 不单独占 backlog 队列项（grep 确认 `docs/openspec-change-backlog.md` 未引用本 change）。符合受保护 artifact 规则。

4. **backlog 一致性**：本 change 未出现在 `docs/openspec-change-backlog.md`，与 backlog_updated 事件口径一致；无残留引用。

5. **业界调研门禁**：本 change RIR 为 `research_tier: exempt` / `status: disabled`，reason 以"无设计决策"结构关键词开头（industry-research-gate 已强化），exempt 证据规则通过（`_exempt_reason_satisfies` 在 archive/全勾态可过）。符合 AGENTS.md 业界调研门禁。

6. **冗余度**：无重复工具引入。检查器保留旧关键字 `grill-with-docs` 为显式向后兼容（design.md Decision 2），非冗余。

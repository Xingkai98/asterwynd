# Building Review: industry-research-gate

## Reviewer
- run id: fa411264-b1e0-4d14-b6c0-a0d35f2b803f
- round: 3
- 时间: 2026-08-14

## Verdict
**PASS**

## Round 1/2 Issue 复核

- **[中] Round 1：light 档「research questions 可省略」与 checker 结构门槛矛盾** — ✅ **已修复且正确**。
  - 代码修复：`scripts/check_openspec_artifacts.py:570-572` enabled 结构门槛按 tier 分流——`normalized_tier == "light"` 时 `enabled_fields = ("findings", "design impact")`，跳过 `research questions`；默认分支（full、tier 缺失/非法）保持三字段必填，未误放宽。
  - tasks 全勾内容门槛对省略 rq 不误报：`:591-592` `if not value: continue`——`_extract_record_field` 对省略字段返回 None，直接跳过。
  - full 仍要求 rq：`tests/test_openspec_artifact_checker.py:1136-1160` `test_reference_implementation_research_enabled_requires_fields`（full + 空 rq 仍报错）。
  - 回归测试真实覆盖两条路径：`tests/test_openspec_artifact_checker.py:1279-1310` `test_light_tier_research_questions_optional`——proposal 阶段（tasks 未全勾）与 tasks 全勾完成时均断言 `check_change == []`。
- **[中] Round 2：spec 侧残留 rq 必填口径** — ✅ **已修复且 delta/synced/checker 三方一致**。
  - delta `openspec/changes/industry-research-gate/specs/change-documentation/spec.md:16-17` 与 synced `openspec/specs/change-documentation/spec.md:203-207`：「Non-docs change records enabled research」改为 "records the reason, findings, and design impact" + "records research questions when `research_tier: full` (omittable for `research_tier: light`)"——逐字一致（仅行宽差异）。
  - delta `:65-66` 与 synced `:263-266`：「Artifact checker enforces record shape」改为 "enabled research has non-empty reason, findings, and design impact" + "research questions are non-empty when `research_tier: full`"——逐字一致。
  - 与「Routine enhancement requires light research」（synced `:288-289` rq may be omitted）及 checker 实现（light 跳过 rq）三方对齐，不再自相矛盾。
  - grep 全 spec 确认无其他无条件 rq 语句：两文件所有 `research questions` 提及均已限定到 full 档或 triage 口径（full 完整记录 / light 可省略）。
- **[低] Round 2：`tests/test_flow_policy.py` #123 内容门槛 fixture 补 `research_tier`** — ✅ 已修复。`tests/test_flow_policy.py:254` 增加 `- research_tier: full`，三个 `test_checker_content_gate_*` 用例断言纯净、无多余结构错误。

## Tasks Verification

### 1. 规格
- **1.1** ✅ — `proposal.md` 存在：需求 5 条、背景、非目标、用户故事、行为定义、Impact Analysis；关联 issue #133、父 map #121。
- **1.2** ✅ — `design.md`：Context、Goals/Non-Goals、Decisions D1-D8、Risks/Trade-offs、Testing Strategy、实施顺序。
- **1.3** ✅ — `proposal.md:69-78` `## Impact Analysis` 表覆盖 checker/Docs/Specs/Tests/CI/明确不受影响，无 `unknown`/`TBD`/`待确认` 残留。
- **1.4** ✅ — `proposal.md:80-87` RIR 节：`research_tier: exempt`（status 前）+ `status: disabled` + reason 命中「上游决策锁定」且含 `#121`/`#126` 引用。
- **1.5** ✅ — `reviews/grill-design.md`：6 条 Confirmed Decisions（≥3）+ Q1-Q6 全部 User Confirmation（每条含「用户答复：」实质内容 + 确认时间，非占位）。
- **1.6** ✅ — `docs/openspec-change-backlog.md` 新增「### 6. `industry-research-gate`」；`workflow-events.jsonl` seq 2 `backlog_updated`。
- **1.7** ✅ — spec delta 合入 synced spec；`workflow-events.jsonl` seq 3 `current_spec_synced`；delta 与 synced 语义逐字一致。

### 2. 测试
- **2.1** ✅ — `tests/test_openspec_artifact_checker.py:1199-1276`：tier 缺失/非法/合法枚举（full/light/exempt 参数化）三用例。
- **2.2** ✅ — `:1313-1424`：结构关键词命中、`#<数字>` 引用、评审路径引用、占位命中（仅 1 条错误，#123 门不重复报）、空 reason、无证据判断性豁免（「与已有模块 X 等价改造」被拒）。
- **2.3** ✅ — `:1430-1505`：full + findings 含「尚未完成」→ exit 报错（#123 回归）、full + disabled + tasks 全勾 → 报错、proposal 阶段 full+disabled 不报错。
- **2.4** ✅ — `:1508-1534` `test_structure_gate_only_when_tasks_not_complete` 阶段感知。
- **2.5** ✅ — `:1136-1193` 既有 RIR 结构门槛回归（full 空 rq / exempt 空 reason / RIR 在 design.md）；`VALID_REFERENCE_RESEARCH`（`:88-99`）含 tier。
- **2.6** ✅ — `:1537-1557` `test_active_change_without_tier_reports_clear_error`（存量缺 tier 报错信息清晰可修）。

### 3. 实现
- **3.1** ✅ — `scripts/check_openspec_artifacts.py:527-542`：`research_tier` 解析 + 缺失/非法枚举报错（proposal 结构门槛）。
- **3.2** ✅ — `:582-627`：tasks 全勾内容门槛——full/light 的 status 闭环（disabled 报错）、exempt 的 status 必须 disabled、exempt reason 证据校验（复用 `SELF_ADMITTED_INCOMPLETE_PHRASES`，不重复报占位）；`_exempt_reason_satisfies` `:488-502` 关键词/正则/`#<数字>`/证据路径四路判据。
- **3.3** ✅ — `AGENTS.md`「业界调研门禁」节：三档判据表 + 豁免质量门槛 + development-guide 链接 + 「本地参考仓库不可用不构成豁免理由」显式排除。
- **3.4** ✅ — `docs/development-guide.md` 新增「业界调研门禁」小节：三档判据表（含反例）、好/坏 reason 示范（与 checker 关键词清单逐项对应）、常见误用 4 条。
- **3.5** ✅ — spec delta 合入（RIR gate 扩展 + 新增 `Research tier triage`）；占位词表引用 #123 不重述（grill Q6 口径）。
- **3.6** ✅ — 三个存量 active change 补齐 tier：add-minimal-tui-runtime-view（full）、add-worktree-tool（full）、update-design-review-method（exempt + reason 强化为「无设计决策——纯工具替换…」，`_exempt_reason_satisfies` 实测返回 True）。
- **3.7** ✅ — Impact Analysis 已含存量 change 补齐影响面（`proposal.md:74`）。

### 4. 验证
- **4.1** ✅ — `uv run pytest tests/test_openspec_artifact_checker.py tests/test_flow_policy.py -q`：103 passed。
- **4.2** ✅ — `uv run pytest -q`：1897 passed、1 failed（`test_tree_sitter_extracts_java_and_kotlin_symbols`，已知环境性失败）、7 skipped。
- **4.3** ✅ — `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：30 passed、0 failed。
- **4.4** ✅（预期中间态）— `uv run python scripts/check_openspec_artifacts.py` 仅报 `review manifest missing`（exit 1）。PASS 后生成 manifest 即消，不算代码缺陷。
- **4.5** ✅ — AGENTS.md 判据表 ↔ development-guide 示例 ↔ spec Requirement 口径一致（人工核对）。

### 5. PR 收尾
- **5.1-5.6** 未勾选 — 预期（后续归档阶段），不算缺陷。

## Issues

- **[低，观察项] 新 spec 场景的「SHALL fail (exit 2)」措辞与实际 exit code 不符**；证据: `openspec/specs/change-documentation/spec.md:231,234,240,241` 与 delta `:36-37,45` 写 "SHALL fail (exit 2)"，而 checker `scripts/check_openspec_artifacts.py:1438` 对任何错误 `return 1`。此措辞继承自 #123 spec（`openspec/specs/dev-workflow-state-machine/spec.md:555,561` 同样写 "exit 2"），属仓库既有约定（非零即 fail，CI 按非零拦截），非本 change 引入的回归；不阻塞。建议: 如后续统一 exit code 语义，可把 checker 错误返回改为 2 或把 spec 措辞改为 "non-zero exit"。
- 其余：无。

## Test Results

| 命令 | 结果 |
|------|------|
| `uv run pytest tests/test_openspec_artifact_checker.py tests/test_flow_policy.py -q` | 103 passed |
| `uv run pytest -q` | 1897 passed, 1 failed（test_tree_sitter_extracts_java_and_kotlin_symbols，已知环境性失败）, 7 skipped |
| `uv run python scripts/check_openspec_artifacts.py` | 仅报 review manifest missing（预期中间态，exit 1，PASS 后生成 manifest 即消） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | 30 passed, 0 failed |

额外验证（不修改仓库文件）：
- 逐行追踪 light + enabled + 无 rq 的两条路径（proposal / tasks 全勾）→ 均返回 `[]`；full + enabled + 空 rq 仍报错（`test_reference_implementation_research_enabled_requires_fields`）。
- tier 缺失/非法时 `normalized_tier` 置 None，不影响 status/reason/enabled 字段检查（proposal 阶段与完成阶段均不因 tier 异常跳过其他检查）。
- `research_tier` 与 `research questions` 前缀无冲突：`_extract_record_field` 用 `field_prefix + ":"` 精确匹配，`"research questions:".startswith("research_tier:")` 与反向均为 False。
- 本 change 自身 RIR（exempt + disabled + reason 命中「上游决策锁定」+ `#121`）自举通过：artifact checker 未报本 change 的 RIR 错误，仅报 manifest 中间态。
- 三个存量 active change 逐一实测：tier 合法、RIR 结构完整（full 档 rq/findings/design impact 齐备）、tasks 未全勾仅过结构门槛、`check_change` 均返回 `[]`；update-design-review-method 的 reason 强化后 `_exempt_reason_satisfies` 返回 True（其 tasks 全勾归档时可通过 exempt 证据校验）。
- delta 与 synced spec 两个场景逐字一致；Research tier triage 的 ADDED 块与 synced triage requirement 语义一致。

## 结论

Round 1（checker light 档跳过 research questions 必填）与 Round 2（spec 两处场景将 rq 要求限定到 full 档 + test_flow_policy fixture 补 tier）的修复均正确、完整且三方（delta / synced / checker）对齐，回归测试真实覆盖 light 省略 rq 的两条路径与 full 仍要求 rq 的路径。tasks 1.x-4.x 全部有真实实现，全量 pytest 与 OpenSpec strict validate 通过，artifact checker 仅报预期的 review manifest 中间态，存量 active change 兼容性与本 change 自举一致性问题均妥善解决。无未解决中等以上问题，最终 verdict 为 PASS。

# Building Review: grill-confirmation-gate

## Verdict

**CHANGES_REQUESTED**

审阅对象：`git diff origin/master...HEAD`（7dbe9ad 立项 → 21dc43a grill 确认 → 1a59099 实现）。

核心承诺（Must-fix A 早返回重构、Must-fix B 判定顺序重构、`_UNCONFIRMED_TOKENS` 占位排除、序号集匹配、checker/workflow_guard 双门禁 + parity 测试、停轮契约）全部真实落地且测试通过。发现 1 个中等问题（未确认 token 判定对标点/空格变体不鲁棒，设计 Decision 4「致命缺口」的覆盖有洞），2 个低等观察。修复后重审即可 PASS。

## Tasks Verification

| task | 实现位置 | 结论 |
|------|---------|------|
| 0.1 独立 subagent grill，产出 `reviews/grill-design.md` | `openspec/changes/grill-confirmation-gate/reviews/grill-design.md`（含 Confirmed Decisions 4 条 + Open Questions Q1-Q7 + User Confirmation Q1-Q7） | ✅ 真实存在 |
| 0.2 Reference Implementation Research 实质调研 | `proposal.md` L42-53、`design.md` L95-107（status: enabled + findings + design impact） | ✅ 实质调研 |
| 1.1 `_extract_open_questions` | `scripts/check_openspec_artifacts.py:502` `_extract_open_question_indexes`（解析 `1.`/`- **Q1**:`/`- Q1`，`- 无` 与占位跳过） | ✅ 真实实现 |
| 1.2 `_extract_user_confirmations` | `scripts/check_openspec_artifacts.py:527` `_extract_user_confirmation_indexes`（`**Q<n>**:` 前缀 + `用户答复：` 字段 + 未确认 token 排除） | ✅ 真实实现 |
| 1.3 `_check_design_review_task` 增强 | `scripts/check_openspec_artifacts.py:435-465`（无早返回，decisions<3 与 User Confirmation 校验合并进 error list；仅在 `_tasks_all_complete` 时强制） | ✅ 真实实现（Must-fix A 已重构，实测 decisions≥3 + 未确认仍报错） |
| 2.1 `_grill_evidence_missing` 增强 | `scripts/workflow_guard.py:204-242`（docs-only/spec-delta 判定前置，证据存在但 Open Questions 未确认 → True） | ✅ 真实实现（Must-fix B 已重构，实测 docs-only 不误拦） |
| 2.2 提取规则与 checker 一致 | `scripts/workflow_guard.py:272-329`（独立复刻，含 `_UNCONFIRMED_*` 与 helper） | ✅ 复刻 + parity 测试兜底 |
| 3.1 checker 回归测试 | `tests/test_openspec_artifact_checker.py` 新增 7 个（为空通过/确认覆盖通过/未确认全勾选报错/无 User Confirmation 节报错/占位不计/重复序号不覆盖/开发中不强制） | ✅ 覆盖要求场景 |
| 3.2 workflow_guard 回归测试 | `tests/test_workflow_guard.py` 新增 3 个（未确认拦截/已确认放行/parity） | ✅ 覆盖要求场景 |
| 4.1 AGENTS.md 最高优先级规则 | `AGENTS.md` 设计追问条追加「停轮确认（grill-confirmation-gate）」段落（停轮、User Confirmation 节、双门禁、占位不计、分支纪律保留） | ✅ 真实更新 |
| 4.2 batch-grill-me / grilling skill | `~/.claude/skills/batch-grill-me/SKILL.md`（## Open Questions must be confirmed…停轮+记录）、`~/.claude/skills/grilling/SKILL.md`（stop and wait + User Confirmation 记录） | ✅ 本地安装件已更新（不进 PR，符合预期） |
| 5.1-5.3、6.1-6.2 收尾 | 均 `[ ]` 未勾选 | ⏸ 收尾阶段任务，属预期（本审阅即闭环之一环）；归档前需补 |

## Issues

### M1 [Medium] `_is_unconfirmed_answer` 对未确认 token 的标点/空格变体不鲁棒

**证据**：`scripts/check_openspec_artifacts.py:101-114`、`scripts/workflow_guard.py:259-269`（两处同缺陷）。

实测（两文件行为一致）：

```text
'待确认。'  → 计入已确认（不应计入）
'未确认。'  → 计入已确认
'待定。'    → 计入已确认
'待主agent提交'（无空格） → 计入已确认
```

`_extract_user_confirmation_indexes` 对 `- **Q1**: 用户答复：待确认。；确认时间: ...` 返回 `['Q1']`（判为已确认），而 `待确认`（无标点）正确返回 `[]`。

**影响**：design.md Decision 4 把「未确认 token 集」定义为 grill Q1「致命缺口」，明确列出 `待确认` / `待主 agent 提交` 等不得计入确认。实现只做整串精确匹配（EXACT）+ 少数强 token 子串（STRONG）。中文句末标点（。，！）与无空格写法是常见变体，恰好绕过该门禁——本 change 的核心承诺（机械拦下「写了占位但没真拍板」）在此变体上失效。`待主agent提交`（issue #74 原文去掉空格）同样漏掉。

**修复建议**（约 3 行）：`_is_unconfirmed_answer` 在精确匹配前先 `answer.strip("。，！!.,;； ")` 归一化；并把 `待确认`/`未确认`/`待定` 这类短 token 加入 STRONG（子串匹配），同时保留 ≤20 字符长度门（长答复仍不误伤）。

### L1 [Low] 两处提取逻辑存在未覆盖的 parity 漂移点

**证据**：checker `scripts/check_openspec_artifacts.py:502-524` 对整节有 `_is_placeholder_body(section)` 守卫，workflow_guard `scripts/workflow_guard.py:272-289` 无该守卫；checker 用 dict（重复 `## Open Questions` 节取**最后一个**），workflow_guard `_h2_section` 线性扫描取**第一个**。parity 测试（`tests/test_workflow_guard.py:311-340`）3 个 fixture 未覆盖这些差异。

**实测差异**：单行节 `## Open Questions\n1. 无` → checker 判空（`_is_placeholder_body` 命中）而 workflow_guard 计为 `['Q1']`。极端场景，但设计 Decision 4 的「两处复刻有漂移风险，用 parity 测试兜底」承诺的是强一致。建议补一条 fixture（含 `1. 无` 与重复节）或在 workflow_guard 补齐 `_is_placeholder_body` 守卫。

### L2 [Low] spec delta 场景措辞严于实现

**证据**：`openspec/changes/grill-confirmation-gate/specs/change-documentation/spec.md`「grill evidence passes design review」把 `## User Confirmation` 节列为通过前置条件；但实现（`_unconfirmed_open_questions`，checker:554-560）在 Open Questions 为空时无需 User Confirmation 节即放行。design.md Decision 2 明确「若 N>0 且 tasks 全勾选才要求确认」，实现与 design 一致，是 spec 场景措辞偏严。归档前建议把场景改写为「…and a `## User Confirmation` section (when Open Questions is non-empty)」或保持现状（非阻塞，记录即可）。

### L3 [Low] checker 读 grill-design.md 无异常兜底

**证据**：`scripts/check_openspec_artifacts.py:446` `text = grill_evidence.read_text(encoding="utf-8")` 无 try/except；workflow_guard 侧有 OSError 兜底（`workflow_guard.py:234-237`）。文件刚 exists() 判定过，实际风险极低，但两侧不对称。建议与 workflow_guard 对齐。

### L4 [Low] 确认记录不强制 `确认时间` 字段

**证据**：`_extract_user_confirmation_indexes` 的正则 `(?:[；;]\s*确认时间|\s*$)`（checker:544）允许无 `确认时间` 的 `- **Q1**: 用户答复：做 A` 行计入。design 规定格式含 `；确认时间: <date>`。属「宽松接受」，在「不防恶意伪造」边界内无害；记录即可，不必改。

## Test Results

```bash
cd /home/happy/my-agent/.claude/worktrees/grill-confirmation-gate
uv run pytest tests/test_openspec_artifact_checker.py tests/test_workflow_guard.py -q
# 63 passed in 1.88s

PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
# OpenSpec artifact checks passed (EXIT=0)
```

- 新增：checker 7 个 + workflow_guard 3 个（含 parity），全部通过。
- 实测本 change 自身 `reviews/grill-design.md`：Open Questions Q1-Q7 与 User Confirmation Q1-Q7 全部匹配，`_unconfirmed_open_questions` 返回 `[]`；checker 与 workflow_guard 提取完全一致。
- 实测 `_is_unconfirmed_answer` 边界：`待主 agent 提交用户确认`/`待确认`/`pending`/`TODO` 正确判为未确认；长答复（>20 字符，含 `待确认` 字样）正确判为实质确认，不误伤。
- 已排除已知环境性失败（`tests/agent/mcp/`、`tests/agent/code_intelligence/`、docker 相关）。

## 结论

实现真实覆盖了 tasks 1.x-4.x 全部 `[x]` 项：Must-fix A（`_check_design_review_task` 不早返回，decisions≥3 时 User Confirmation 校验仍执行）与 Must-fix B（`_grill_evidence_missing` 先判需否 grill 再判证据完整性，docs-only 不误拦）均已落地；序号集匹配防 Q1,Q2,Q3,Q3,Q3 假通过；checker 仅在 tasks 全勾选时强制；AGENTS.md 与两个 grill skill 的停轮契约齐备。测试全绿，checker 门禁通过。

唯一中等问题是 M1：未确认 token 判定对标点/空格变体不鲁棒，使 design.md 明确列出的「致命缺口」token 集（`待确认` 等）在 `待确认。`/`待主agent提交` 等常见变体下失效。该缺陷位于本 change 的核心机械强制路径上，按审阅标准应修复后合入；修复量约 3 行，重审成本低。

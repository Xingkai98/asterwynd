# Building Review: grill-confirmation-gate

## Verdict

**PASS**

审阅对象：`git diff origin/master...HEAD`（7dbe9ad 立项 → 21dc43a grill 确认 → 1a59099 实现 → f60c0ad Round 1 修复）。本报告为 Round 2 复审，验证 Round 1（CHANGES_REQUESTED）的 M1/L1/L2 修复是否到位，并对实现做独立复核。

Round 1 的三项 findings 全部修复到位：M1（未确认 token 标点/空格变体绕过）已用 `_UNCONFIRMED_STRIP` 归一化 + STRONG 集补 `待主agent` 修复，两条回归测试真实覆盖且通过；L1 的 concrete 漂移点（`1. 无` 判空不一致）已统一，parity 测试通过；L2 spec 措辞已与实现对齐。实现核心承诺（Must-fix A/B 重构、序号集匹配、双门禁 + parity、停轮契约）复核通过，测试全绿（65 passed），checker 门禁通过（仅缺 review manifest，本审阅即产出该产物）。

## Round 1 修复验证

### M1 [Medium] → 已修复

**验证结论**：`_is_unconfirmed_answer` 在精确匹配前用 `_UNCONFIRMED_STRIP` 剥离标点/空白（`。．.；;，,、 \t`），STRONG 集含 `待主agent` 无空格变体；两文件行为一致。

**证据**：
- `scripts/check_openspec_artifacts.py:100-101`（`_UNCONFIRMED_STRIP = str.maketrans("", "", "。．.；;，,、 \t")`）、`:95-98`（STRONG 含 `待主 agent` 与 `待主agent`）、`:104-117`（`_is_unconfirmed_answer` 先 `.translate(_UNCONFIRMED_STRIP)` 再精确/子串匹配）
- `scripts/workflow_guard.py:258`（同 `_UNCONFIRMED_STRIP`）、`:253-256`（同 STRONG 集）、`:261-271`（同判定逻辑）
- 回归测试：`tests/test_openspec_artifact_checker.py:814-823`（`test_grill_punctuation_variant_confirmation_not_counted`，fixture `用户答复：待确认。；确认时间: ...`，断言错误含 `未确认` + `Q1`）、`:825-833`（`test_grill_no_space_variant_confirmation_not_counted`，fixture `用户答复：待主agent提交；...`）。两测试均走 `_grill_evidence` 默认 `tasks_all_checked=True`，真实覆盖归档 checker 的拦截路径。

**实测**：`待确认。`/`未确认。`/`待定。`/`待主agent提交`/`待确认`/`pending`/`TODO` 两文件均判 `True`（未确认）；`做 A` 与 27 字符实质长答复判 `False`（不误伤）。端到端 guard：`待确认。` 变体 rc=2（拦截），真实确认 rc=0（放行）。

### L1 [Low] → 已修复（concrete 漂移点），留 1 个极端残余

**验证结论**：Round 1 实测的具体漂移点（单行节 `## Open Questions\n1. 无` → checker 判空、guard 计 `['Q1']`）已消除；两文件 `_extract_open_question_indexes` 现为逐行逻辑逐字节一致，`1. 无` / `- 无` / `- **Q1**:` 三种形式均一致。

**证据**：
- `scripts/check_openspec_artifacts.py:509-535` 与 `scripts/workflow_guard.py:274-296`：逐行逻辑一致——no_q 归一化跳过 `{"无","无。","none","none。","没有","无问题"}`，索引正则 `^[-*]?\s*\**\s*(?:(?:Q|q)\d+|\d+)\s*[:：.]?\s*` 从原始行读取
- `_normalize_question_index` 支持 `- **Q1**:`（`check_openspec_artifacts.py:502`、`workflow_guard.py:322`：`re.sub(r"^[-*]\s*\**\s*", "", cleaned)` 剥离列表/加粗包裹）
- parity 测试：`tests/test_workflow_guard.py:308-340`，3 个 fixture 覆盖 `1. a\n2. b` / `- 无` / `- **Q1**: a\n- **Q3**: c`，对 checker 与 guard 双实现断言一致
- `tests/test_workflow_guard.py:324-327` fixture `- 无` → 两实现均 `[]`

**实测**：`1. 无`/`- 无`/`- 无。`/`**无**`/`<!-- 无问题占位 -->` 两实现均 `[]`；`1. 无\n2. 问题二` 均 `['Q2']`；`- **Q1**: 问题一\n- **Q3**: 问题三` 均 `['Q1','Q3']`；`_normalize_question_index` 对 `- **Q1**:`/`**Q2**:`/`1.`/`1. 问题一` 分别返回 `Q1`/`Q2`/`Q1`/`Q1`，不误伤数字序号。

**残余（新观察，非阻塞）**：重复 `## Open Questions` 节（同一文件两个同标题 H2）仍分歧——checker 用 dict 取**最后一个**，workflow_guard `_h2_section` 线性扫描取**第一个**。实测 `## Open Questions\n1. 无\n## Open Questions\n- **Q1**: 真实问题\n` → checker `['Q1']`、guard `[]`。这是极端 markdown 结构（grill skill 产出的证据单节），且归档门禁侧（checker，CI 强制）是更严方向，不会被此漂移放行未确认项。见 New Issue N1。

### L2 [Low] → 已修复

**验证结论**：spec 场景措辞已对齐实现「Open Questions 空则无需 User Confirmation 节」。

**证据**：`openspec/changes/grill-confirmation-gate/specs/change-documentation/spec.md:25-28`——`**WHEN** the record has at least 3 confirmed decisions` + `**AND** either the Open Questions section is empty, or every listed Open Question has a matching ## User Confirmation entry`。与 `_unconfirmed_open_questions`（`check_openspec_artifacts.py:565-571`：`if not open_indexes: return []`）一致。

## 重点复核

- **`_normalize_question_index` 支持 `- **Q1**:` 不误伤 `1. 问题一`**：实测 `- **Q1**:`→`Q1`、`**Q2**:`→`Q2`、`1.`→`Q1`、`1. 问题一`→`Q1`。剥离正则 `^[-*]\s*\**\s*` 只匹配列表/加粗前缀，数字序号不受影响。
- **真实 change 的 grill-design.md 正确解析、无未确认**：checker open=[Q1..Q7]、confirm=[Q1..Q7]、unconfirmed=[]；guard 完全一致（PARITY）。7 个 Open Questions 与 7 条 User Confirmation 序号一一对应。
- **`_check_design_review_task` 不早返回**：`scripts/check_openspec_artifacts.py:438-468`——`grill_evidence.exists()` 分支内先收集 `decisions < 3` 错误进 error list，随后 `if _tasks_all_complete(change_dir)` 独立执行 `_unconfirmed_open_questions` 校验，无 `return []` 早返回路径。Must-fix A 修复保持有效。
- **`_grill_evidence_missing` 判定顺序（docs-only 不误拦）**：`scripts/workflow_guard.py:204-242`——步骤 1 docs-only（`primary: docs`）return False；步骤 2 无 spec delta return False；步骤 3 才评估证据完整性（缺失或 Open Questions 未确认 → True）。Must-fix B 修复保持有效。实测 docs-only 无证据 → False，feature + spec delta + 未确认 → True。
- **checker 门禁**：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --change grill-confirmation-gate` 仅报 review manifest 缺失（本审阅闭环产物），无 grill/未确认/占位错误——change 自身证据通过。

## New Issues

### N1 [Low] 重复 `## Open Questions` 节的 parity 残余漂移

**证据**：实测 `## Open Questions\n1. 无\n## Open Questions\n- **Q1**: 真实问题\n` → checker `['Q1']`（dict 取末节）、workflow_guard `[]`（线性取首节）。Round 1 L1 已点名该漂移点；修复统一了逐行逻辑，但两文件节提取 helper 差异（`_extract_h2_sections` vs `_h2_section`）未消除。

**影响**：极端 markdown 结构（同文件重复 H2 标题），grill skill 产出的证据恒为单节，实际不会触发；且更严方向在 checker（归档/CI 强制侧），不会放行未确认项。建议后续在 workflow_guard 的 `_h2_section` 或 parity fixture 中补一条重复节用例对齐，非本轮阻塞项。

### N2 [Info] guard 侧无 M1 标点变体的独立单元测试

**证据**：M1 两条回归测试只落在 `tests/test_openspec_artifact_checker.py`；`tests/test_workflow_guard.py` 的 guard 级 M1 覆盖仅 fixture 3 用无标点 `待确认`（`:330`）。guard 的标点变体行为由两文件 `_is_unconfirmed_answer` 逐字节一致 + parity 测试 + 本次端到端实测（`待确认。`→rc=2）兜底。属测试分布不均，非缺陷。

## Test Results

```bash
cd /home/happy/my-agent/.claude/worktrees/grill-confirmation-gate
uv run pytest tests/test_openspec_artifact_checker.py tests/test_workflow_guard.py -q
# 65 passed in 2.62s
```

- 新增（Round 1 修复）：checker 2 个 M1 回归测试（标点变体 + 无空格变体），全通过。
- 实测本 change 自身 `reviews/grill-design.md`：Open Questions Q1-Q7 与 User Confirmation Q1-Q7 全部匹配，`_unconfirmed_open_questions` 返回 `[]`；checker 与 workflow_guard 提取完全一致。
- 实测 `_is_unconfirmed_answer` 边界：`待确认。`/`未确认。`/`待定。`/`待主agent提交`/`pending`/`TODO` 正确判为未确认；`做 A` 与 27 字符实质答复正确判为确认，不误伤。
- 端到端 guard：`待确认。` 变体写操作 rc=2（拦截）；真实确认 rc=0（放行）。
- 全量 checker：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --change grill-confirmation-gate` 仅缺 review manifest（本审阅产出）。

## 结论

Round 1 全部 findings 修复到位：M1（核心机械强制路径上的标点/空格变体绕过）已真实修复并有回归测试兜底；L1 concrete 漂移点已统一并有 parity 测试；L2 spec 措辞已对齐。实现核心承诺（Must-fix A 不早返回、Must-fix B docs-only 不误拦、序号集匹配防 Q1,Q2,Q3,Q3,Q3 假通过、checker 仅 tasks 全勾选时强制、AGENTS.md 停轮契约）复核通过。测试全绿，checker 门禁通过（仅缺本审阅将产出的 review manifest）。残留 N1（重复节 parity 漂移）为极端输入下的 Low 级观察，归档门禁侧更严，不构成合入阻塞。**PASS**。

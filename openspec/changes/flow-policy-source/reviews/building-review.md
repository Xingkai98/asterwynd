# Building Review: flow-policy-source（P0）

- reviewer run: building-review-flow-policy-source-20260814（独立零记忆 subagent）
- 审阅基线: `git diff 774e30a...HEAD`（5 个提交，分支 flow-policy-source/2026-08-14）
- 审阅时间: 2026-08-14

## Verdict

**CHANGES_REQUESTED**

实现主体完整且正确（单一策略源、同源加载、fail-closed、4 绕过纯形态拦截、内容门槛、schema 校验、policy-* CLI 均有真实实现与测试，95 个定向测试全绿，artifact checker 通过）。但存在 **1 个高严重度新绕过**（特权 CLI 豁免可被 `&&`/`;` 链式劫持，使 P0 的「4 绕过修复」可被一行前缀重新绕过）+ 若干中低问题（Q10 违反、checker schema 非法裸崩、tasks 2.5 parity 缺测试锁）。需修复后复审。

## Tasks Verification

| Task | 验证结果 |
|---|---|
| 1.1 proposal.md | ✅ 存在，含需求/非目标/行为定义/验收/Impact Analysis/Reference Implementation Research/测试计划 |
| 1.2 design.md | ✅ 存在，含 Context/Goals/Non-Goals/Decisions(D1-D9)/Risks/Testing Strategy |
| 1.3 Impact Analysis | ✅ proposal.md:91-103，覆盖 guard/checker/CLI/Specs/Tests/CI/Docs/Migration/明确不受影响 |
| 1.4 Reference Implementation Research | ✅ proposal.md:105-118，status: disabled + reason + research questions + findings + design impact |
| 1.5 grill 设计追问 | ✅ reviews/grill-design.md：6 条 Confirmed Decisions + Q1-Q10 + User Confirmation（Q1-Q10 全部 2026-08-14 确认） |
| 1.6 backlog 登记 | ✅ docs/openspec-change-backlog.md 新增 #6 + workflow-events.jsonl 2 个事件（change_created/backlog_updated） |
| 1.7 spec sync | ⏳ `[ ]` 未做（收尾阶段任务，预期内，不算缺陷） |
| 2.1 guard 单元测试 | ✅ test_flow_policy.py:40-102（加载/fail-closed 缺失/损坏/schema 非法）；test_workflow_guard.py 既有 exact/contains。注：prefix（openspec/specs/）无独立 guard 用例，经 contains 语义隐含覆盖 |
| 2.2 4 绕过回归 | ✅ test_flow_policy.py:107-121，实测全部 exit 2 |
| 2.3 正则死锁修复 | ✅ test_flow_policy.py:169-200（Q8 后缀 + fenced block），guard/checker 同步 |
| 2.4 checker 加载 | ✅ test_policy_disk_matches_guard_default 链式断言（guard 内嵌子集 == 磁盘子集 == checker 加载集） |
| 2.5 同源 parity | ⚠️ 部分：path 值集 parity 有测试（test_flow_policy.py:230）；但「bash 写正则 / unconfirmed 词表 guard↔checker 一致」**无测试锁**（见 Issue #4） |
| 2.6 内容门槛 | ✅ test_flow_policy.py:246-296（tasks 全勾触发/未全勾跳过/干净 finding 放行） |
| 2.7 agent schema | ✅ test_flow_policy.py:302-341（合法/未知 phase/缺 model/未知 review 键） |
| 2.8 集成 + policy CLI | ✅ test_flow_policy.py:347-392 + test_guard_loads_rules_from_policy（自定义规则生效） |
| 3.1 flow-policy.json | ✅ scripts/flow-policy.json（11 条规则 + phases/review 占位），与 D4 表一致 |
| 3.2 guard 改造 | ✅ 策略加载（:93-121）、fail-closed（:239-251）、Bash 扫描前移（:554-563）、路径归一化（:124-129） |
| 3.3 guard 正则修复 | ✅ `_extract_user_confirmation_indexes`（:441-460）容忍后缀、`_h2_section`/`_inside_fence`（:472-496）跳 fenced block |
| 3.4 checker 同源加载 | ✅ `_load_protected_path_rules`（check_openspec_artifacts.py:147-180）替换硬编码；`_allowed_event_types_for_protected_path` 接规则参数 |
| 3.5 checker 内容门槛 | ✅ `_self_admitted_incomplete` + `_tasks_all_complete` 阶段感知（:529-542） |
| 3.6 checker agent schema 校验 | ✅ `_validate_policy_agent_schema`（:242-308）+ main() 接线（:1343） |
| 3.7 policy-* 子命令 | ✅ workflow_state.py:794-894（policy-show/policy-validate/policy-set 原子写） |
| 3.8 Impact 回写 | ✅ 新影响面均已在 proposal Impact Analysis 记录 |
| 4.1 定向测试 | ✅ 三文件 95 passed |
| 4.2 全量 pytest | ⏭️ 跳过（已知环境失败：5 个 MCP 缺 uv、tree-sitter pre-existing、background 时序，均与本次无关） |
| 4.3 OpenSpec validate | 提交信息声称已跑；环境无 npx 未复跑 |
| 4.4 artifact checker | ✅ `python3 scripts/check_openspec_artifacts.py` 与 `--change flow-policy-source` 均 PASS |
| 4.5 4 绕过出口 | ✅ 纯形态实测全部 exit 2（⚠️ 但可被 Issue #1 链式绕过） |
| 5.x PR 收尾 | ⏳ `[ ]` 未做（预期内） |

## Issues

### Issue 1 [HIGH] 特权 CLI 豁免是整条命令子串扫描 → `&&`/`;` 链式绕过 4 个绕过修复

- 位置: `scripts/workflow_guard.py:254-261`（`_is_privileged_cli` 用 `re.search` 扫整条命令）、`:556`（`if not _is_privileged_cli(command) and _is_write_bash(command)`）
- 失败场景: `python3 scripts/workflow_state.py policy-show && echo hacked > docs/known-debt.md` → 命令含 `policy-show` → 整条豁免 → **rc=0**。
- 实测: 4 个文档化绕过全部可被一行前缀重新绕过（`policy-show && echo >docs/known-debt.md`、`&& cat <<EOF > ...`、`&& python3 -c "...write_text..."`、`&& echo hi > docs/./known-debt.md` 全部 rc=0）；`artifact-event ...; echo > docs/known-issues.md` 同样 rc=0。
- 根因: 豁免语义本应是「该 CLI 调用本身是合法写通道」，实现却把「整条 Bash 命令只要包含该子串」整体豁免。
- 修复建议: 豁免仅当命令是**独立的**特权 CLI 调用（无 `&&`/`;`/`|`/换行 复合）；或仅豁免命令中该 CLI 对应段而非整条命令；补链式回归测试。`policy-show`/`policy-validate` 本身只读，可考虑不豁免。

### Issue 2 [MEDIUM] `_CURRENT_RULES or _DEFAULT_PROTECTED_PATHS` 违反 Q10，且 Write/Bash 行为不一致

- 位置: `scripts/workflow_guard.py:294`
- 失败场景: 策略文件 `protected_paths: []` 时——Write `docs/known-debt.md` → **rc=0**（`:544` 用空 `_CURRENT_RULES` 匹配，fail-open）；Bash `echo > docs/known-debt.md` → rc=2（`:294` 空列表回退到内嵌默认表）。同一策略文件下两工具判定不一致。
- 违反: grill Q10（grill-design.md:25）「内嵌默认表 parity-only，不参与运行时 enforcement」；也违反 spec delta「guard 与 checker 对同一路径得出一致判定」。
- 修复建议: 去掉 `or _DEFAULT_PROTECTED_PATHS`，或对空规则集也 fail-closed。

### Issue 3 [MEDIUM] checker 对 schema 非法策略抛未捕获 RuntimeError 裸 traceback

- 位置: `scripts/check_openspec_artifacts.py:176`（`raise RuntimeError`）；调用点 `:973`（check_protected_path_explanations）、`scripts/workflow_state.py:823`（policy-validate）、`:888`（policy-set）
- 失败场景: flow-policy.json 含 `{"path":"docs/known-debt.md","match_type":"exact","governance":"event_explained"}`（缺 event_types）→ `check_openspec_artifacts.py` 与 `policy-validate` 直接抛 traceback（exit 1，仍 fail-closed）。
- 影响: 违反设计 Risks「策略文件损坏时 guard 与 checker 报错口径需一致」（design.md:172）；且 guard fail-closed 文案指引用户「用 policy-validate 校验后重试」（workflow_guard.py:245-248），而 policy-validate 恰在此场景裸崩。
- 修复建议: main()/cmd_policy_validate/cmd_policy_set 捕获 RuntimeError 转干净 FAIL 文案。

### Issue 4 [MEDIUM] tasks 2.5「bash 写正则 / unconfirmed 词表 guard↔checker 一致」parity 无测试锁

- 位置: `tests/test_flow_policy.py:230`（只锁 path 值集）、`tests/test_workflow_guard.py:308`（只锁 Open Questions/User Confirmation 提取）
- 现状: `_UNCONFIRMED_EXACT`/`_UNCONFIRMED_STRONG`（workflow_guard.py:391-398 vs check_openspec_artifacts.py:110-117）当前手工比对一致，但无机械断言；`_BASH_WRITE_PATTERNS` 无 parity 锚点。任务 2.5 勾选但该子项缺测试。
- 修复建议: 补一条 parity 测试锁两处词表一致（并可将 `_BASH_WRITE_PATTERNS` 纳入）。

### Issue 5 [LOW] shell 变量拼接路径绕过

- 位置: `scripts/workflow_guard.py:264-283`（`_BASH_TARGET_RE`/`_extract_bash_targets`）
- 失败场景: `echo > doc$V/known-debt.md`（`$V` 未设置）→ 提取 token `doc$V/known-debt.md` → norm 后不命中 → **rc=0**。
- 性质: 残留绕过，需 agent 主动构造变量拼接。P0 的 4 个已知绕过纯形态已堵；此项建议记录 known-debt 或接受残余风险。

### Issue 6 [LOW] guard Write/Edit 用 blanket contains 而非 D2 的 match_type 精确解释

- 位置: `scripts/workflow_guard.py:132-144`（`pattern in normalized`）
- 失败场景: `xdocs/known-debt.md` 写入被 guard 拦（contains 命中），但 checker exact 语义不判受保护 → 两工具判定不一致（保守方向 over-block）。
- 备注: docstring 已声明这是有意的 contains 语义（:136-138），但 D2（design.md:70, 76）要求 match_type 精确解释，spec delta「一致判定」场景未严格满足。建议在 design 中明确记录该偏差或改为 match_type-aware。

### Issue 7 [LOW] policy-set 无法修复损坏 JSON 的策略文件；guard 恢复文案指向只校验的 policy-validate

- 位置: `scripts/workflow_state.py:857-864`（`_read_policy()` None → 报错退出）、`scripts/workflow_guard.py:245-248`（文案）
- 失败场景: flow-policy.json 被截断/损坏 → guard fail-closed exit 2 提示「用 policy-validate 校验后重试」；policy-validate 只校验不修复，policy-set 因 `_read_policy()` None 也无法重建 → 实际恢复只能人类直改。
- 修复建议: 文案改为「人类直改或修复后重试」，或让 policy-set 支持损坏文件重建。

## Test Results

| 命令 | 结果 |
|---|---|
| `python3 -m pytest tests/test_flow_policy.py tests/test_workflow_guard.py tests/test_openspec_artifact_checker.py -q` | **95 passed** |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | PASS（exit 0） |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --change flow-policy-source` | PASS（exit 0） |
| 全量 pytest | 跳过（已知环境失败，与本次改动无关，提交说明已记录） |

## 结论

- **优势**: 架构主线完整——单一策略源（flow-policy.json）真实落地，guard/checker 同源加载，缺失/损坏 fail-closed exit 2，4 个文档化绕过纯形态全部拦截（带回归测试），内容门槛阶段感知与 agent schema JSON Schema 校验均有真实实现和测试，policy-* CLI 原子写可用。parity 链式断言（guard 内嵌子集 == 磁盘子集 == checker 加载集）设计正确。
- **必须修复**: Issue #1（特权 CLI 豁免链式绕过）——它使 P0 的核心交付「4 绕过修复」可被一行前缀重新绕过，属安全边界缺陷，修复（锚定豁免）+ 补链式回归测试后再复审。
- **建议修复**: Issue #2（Q10 违反 + Write/Bash 不一致）、Issue #3（checker 裸崩）、Issue #4（2.5 parity 缺测试锁）。
- **可接受残余**: Issue #5/#6/#7（低严重度，可记 known-debt 或文档化）。

# Building Review: evaluation-narrative

## Reviewer

- run id: review-loop-c4-2026-08-17（独立零记忆 subagent，不继承开发上下文）
- 时间: 2026-08-17
- 审阅基线: base 88ed98a → head 0829a56（evaluation-narrative 文件；C3 `evaluation-protocol-reporting` 立项文档不在审阅对象内，已忽略）

## Verdict

PASS

## 核验基线（审阅者独立实测，非继承）

| 项 | 实测 | 结论 |
|----|------|------|
| 本地任务数 | `ls -d benchmarks/tasks/asterwynd-*` = **27**（26 A 轨 + 1 B 轨） | ✅ |
| SWE-bench 任务数 | `ls -d benchmarks/tasks/swebench-*` = **10** | ✅ |
| 测试文件数 | `git ls-files "tests/*.py"` 中 `test_*.py` = **148** | ✅ |
| 测试函数数 | `rg -c "^\s*(async def|def) test_" tests --glob "test_*.py"` 求和 = **1997** | ✅ |
| 内置工具数 | `agent/tools/factory.py:71` `KNOWN_BUILTIN_TOOL_NAMES` = **38** | ✅ |
| README/README_EN 任务数 | README L178「37 个编码任务」/L373「27 个本地任务」；README_EN L178/L374 同 | ✅ 已 C1 同步 |
| C3 合入状态 | `git ls-tree origin/master --name-only openspec/changes/` 无 `evaluation-protocol-reporting` | ✅ 未合入 |

## Tasks Verification

- [x] 1.1 — proposal.md L5-8 Change Type / L48-57 Impact Analysis / L39-46 RIR（research_tier=exempt，reason 引 docs-only + 已关闭决策 #153/#147）完整，无 `unknown`/`TBD`/`待确认`。
- [x] 1.2 — `reviews/grill-design.md` 存在（run f1c9210c-1fd3-47f2-9358-09b84b483d5a），Confirmed Decisions 6 条（≥3 门禁满足）。
- [x] 1.3 — grill-design.md `## User Confirmation` 8 条 Open Questions 全部有 `用户答复：<实质内容>；确认时间: 2026-08-17`，另有 1 条补充确认；无占位文本。
- [x] 2.1 — resume L9「内置 27 个本地 coding-agent 任务（26 A 轨回归基线 + 1 B 轨当前演进）」、L104 同、L23「约 ~1997 个测试函数」、L116「约 ~1997 个回归测试」、L87 由 D3 草案替换（34 清零）。
- [x] 2.2 — resume 5 处 Claw 目录表述全部重锚：L9「并以统一 harness（SwebenchAdapter + 多 runner）对比 Aider、OpenCode」、L89「统一 harness 对比：SwebenchAdapter + 多 runner（Asterwynd/ClaudeCode/Shell）」、L105 同、L125-126「统一 harness 对比…同一批 SWE-bench Verified 实例上比较」、L132「并以 SWE-bench / 统一 harness 做可复现评测」。`claw-swe-bench`（目录路径）在 resume 全清。
- [x] 2.3 — D3 草案落展开版 §6 Benchmark 闭环 L87 整行替换（含 27 本地任务 + Verified 子集 + bootstrap 95% CI + pass@1/pass@k + 统一 harness 对比 + CI 回归门禁）；简洁版 L9 只改数字不塞长子弹。
- [x] 3.1 — Q13 L7 任务层加「场景×难度分层（5 场景 × easy/medium/hard）+ 三来源 + 过渡句（两类=执行类型轴）」+ 双要素「升级目标 ~90…设计已定、C1 实现中；当前已落 37 = 27 本地 + 10 Verified 子集」。
- [x] 3.2 — Q13 L11 指标层加 pass^k/cost@pass/fault_owner，标「升级方向，C1–C3 实现中」。
- [x] 3.3 — Q13 L13 对比层加「per-task delta + 差异 CI + win-rate（paired bootstrap / McNemar）（升级方向）」。
- [x] 3.4 — Q13 L15 面试重点加污染披露「OpenAI 2026-02 已弃用 Verified：审计 138 题中 59.4% 有实质缺陷 + 训练污染，当对照参考不当金标准」+ pass@1/pass^k 口径分开讲 + 内联 Claw 重锚。
- [x] 3.5 — Q13 L64 Claw 表述重锚「对标 Claw-SWE-Bench 的统一 harness 口径（SwebenchAdapter + 多 runner 对比 Aider/OpenCode），同一任务同一 grading 仅换 agent runtime」。
- [x] 4.1 — W07 L3 顶部引用句 + L98 简历核实表均「37 个 coding 任务（27 本地 + 10 SWE-bench 外部）」/「27 + 10 = 37 | ✅」。
- [x] 4.2 — W07 面试加分点追加 4 条（L110-113）：评测升级路线（37→~90 双要素 + C1–C3 实现中）、SWE-bench 污染披露（138/59.4%）、反作弊诚实边界（A 轨历史可见局限披露）、预算可配置可取消（`--budget-cap`/0 取消 + 「flag 当前代码库未实现」诚实标注）。
- [x] 5.1 — FINAL L111「148 测试文件 / ~1997 测试函数」。
- [x] 5.2 — FINAL L112「38 个（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」+ L113 全量 40+ 同步口径；L134 口径要点说明保留。
- [x] 5.3 — FINAL L117「37（27 本地 + 10 SWE-bench）」+ L118 新增升级目标行（双要素）。
- [x] 5.4 — FINAL bullet 7 L96 讲法追加升级句「任务集从 37 扩到升级目标 ~90…设计已定，实现中」。
- [x] 5.5 — FINAL 速查表新增 5 行升级数字（L118-122：评测任务升级目标/pass^k/cost@pass/fault_owner/预算，标 C1/C2/C3 出处）。
- [x] 6.1 — 扩展词表 grep（`23 个`/`34 个`/`450+`/`claw-swe-bench`/`26 + 10`/`130 文件`/`~1691`/`36（26`）于 5 份目标文档 + 正式 spec 全清。FINAL L11「1700+」为 Q3 用户确认保留（仍真，1997>1700）；FINAL L157「37→36+ 任务」为历史口径变更日志（非现状声明）；walkthrough/README L28「1700+ | 148 文件/~1997 函数」为新核实行。
- [x] 6.2 — README/README_EN 任务数 27/37 已就位，无待改。
- [x] 6.3 — 数字与 master 实测一致（27/37/148/~1997/38），简历用「27 本地任务（26 A 轨 + 1 B 轨）+ Verified 子集」表述。
- [x] 7.1 — proposal Impact Analysis 清理干净（唯一 `unknown` 命中为 design L75 fault_owner 枚举值 `{agent, task, environment, unknown}`，非占位）。
- [x] 7.2 — proposal RIR final findings（实测数字来源 + `.dev/reference-repos.txt` 缺失已记录 + 不用占位豁免）。
- [ ] 7.3 — 未做（与 8.3 归档清理合并，属收尾，不判缺陷）。
- [x] 7.4 — 正式 spec `openspec/specs/interview-script/spec.md` L75-84 已含 ADDED Requirement「面试叙事与评测现状对齐」+ Scenario「现状口径分层」，与 delta 逐字一致；workflow-events seq 2 `current_spec_synced` reason 非占位。
- [x] 7.5 — 审阅者重跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` = 31 passed / 0 failed；`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` = passed。
- [x] 7.6 — C3 未合入 master，升级段维持「设计已定、C1–C3 实现中」标注，无需校准。
- [ ] 8.1-8.5 — 收尾阶段（本审阅即 8.1 第一步，manifest 在审阅通过后由流程生成）。

## Issues

- **低（记录，不阻断）** README.md/README_EN.md 仍有多处 `claw-swe-bench` 引用（README L36/L78-79/L81/L185-186/L374/L410-417/L469-470，README_EN 同），其中含可运行指令（`cd claw-swe-bench`、「详见 CLAW-SWE-BENCH.md」），但目录 `claw-swe-bench/`、文件 `CLAW-SWE-BENCH.md` 均已不在 tree（`git ls-files | rg -i claw` 为空）。design.md `## Known Debt` 只记了 architecture/development-guide/testing-guide/benchmark-plan/coding-agent-roadmap 五份，漏记 README/README_EN 这两份最醒目的失效引用。**不在本 change 声明范围**（tasks 6.2 仅查 README 任务数；Known Debt 为 2026-08-17 用户确认不扩 scope），但建议在归档时把 README/README_EN 补进 Known Debt 或后续专项清理。文件: docs/resume-description.md 之外（README.md:78-81,410-417; README_EN.md:78-81,411-418）。
- **低（记录，不阻断）** `docs/openspec-change-backlog.md` L87 C4 条目仍写「现状口径修正（23→26、450+→1700+）」——为立项时（grill 实测前）口径；tasks 7.3 明确与 8.3 归档清理合并执行，本审阅不计缺陷。归档时需一并更新为 27/~1997。
- **低（记录，不阻断）** resume L23/L116「约 ~1997 个测试函数」存在「约 ~」冗余（同句两个约数词）；为 design D1 用户确认的逐字文本，纯措辞，不改。
- **低（记录，不阻断）** FINAL L157「之前已修正（历史）：37→36+ 任务」是历史口径变更日志条目，与当前 37 不冲突但易误读；非现状声明，不动。
- **流程注记** tasks.md 7.x 勾选（7.1/7.2/7.4/7.5/7.6）为工作区未提交修改（HEAD 0829a56 仅勾了 1.x-6.x）；实质均已核验，收尾提交时并入。

## Test Results

- openspec validate: `31 passed, 0 failed (31 items)`，exit 0。
- artifact checker: `OpenSpec artifact checks passed`，exit 0。

## 结论

docs-only 面试叙事 change 实现完整、口径一致。5 份目标文档（resume/Q13/W07/FINAL/walkthrough-README）+ 正式 spec 的全部数字（27/37/148/~1997/38）与 master 实测逐项相符，审阅者独立复核确认；升级方向（~90/pass^k/cost@pass/fault_owner/污染披露/预算）全部带「设计已定/实现中」标注，~90 三处均带「当前已落 37」双要素，无未实现写成已实现。tasks 1.x-7.x 全部 [x] 均有真实文档实现；正式 spec 的 ADDED Requirement 与 delta 逐字同步。openspec strict validate（31 passed）与项目 artifact checker 均通过。未发现中等以上问题，无 CHANGES_REQUESTED 项。Verdict: PASS。收尾阶段（7.3/8.2-8.5）需在归档时更新 backlog L87 口径并补记 README/README_EN 的 claw-swe-bench 失效引用债务。

# Grill: evaluation-narrative 设计追问

## Reviewer

- run id: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- 时间: 2026-08-17
- 审查对象: `openspec/changes/evaluation-narrative/design.md`（D1–D5）+ proposal.md + tasks.md + spec delta + 4 份目标文档 + README/README_EN
- 审查方式: 独立零记忆 subagent，亲自核验全部数字（不继承开发 session 上下文）

## 核验基线（grill 实测，2026-08-17，本 worktree HEAD=90264cd，基座 master=88ed98a）

| 项 | design 声称 | grill 实测 | 结论 |
|----|-----------|-----------|------|
| T2 交付物 `docs/research/narrative-changes-2026-08-17.md` | 「已定稿」「精确编辑清单」 | **全部 git 分支不存在**，`docs/research/` 目录不存在 | ❌ 关键依赖缺失 |
| 本地任务数 | 「26（C1 新增 b01 后 27）」 | `ls -d benchmarks/tasks/asterwynd-*/` = **27**（26 个 A 轨含 readme-title + b01 B 轨）；`swebench-*/` = **10**；合计 **37** | ⚠️ design 承认 27，但 D1/D3 落稿仍写 26/36 |
| 测试文件/函数 | 「135 文件/1700+ 函数」 | `git ls-files "tests/*.py"` 中 test_*.py = **148**；`rg -c "^\s*(async def|def) test_"` 求和 = **1997** | ❌ design 目标 135/1700+ 与 master 不符 |
| 内置工具 | 「38」 | `KNOWN_BUILTIN_TOOL_NAMES`（factory.py:71）= **38**（含 7 个默认关闭浏览器工具） | ✅ |
| README 口径 | — | README L36/L373「27 个本地任务」、L178「37 个编码任务」；README_EN L36/L374「27 local tasks」、L178「37 coding tasks」；两文件均无「26」 | ✅ README 已 C1 同步，interview 文档是唯一旧口径残留源 |
| 污染披露数字 | 「138 实例 59.4% 缺陷」（tasks 3.4） | 来源已落 `openspec/specs/benchmark/spec.md` L429-431（C1/C2 spec）与 C3 design | ✅ 有据 |
| `docs/benchmark-run-protocol.md` | 「C3 专属，不碰」 | 当前文件不存在（C3 未合入） | ✅ D4 边界正确 |
| `claw-swe-bench/` 目录 | 「已不在 tree」 | 实测不在 tree、`git ls-files` 无跟踪 | ✅ |
| 4 份目标文档行号 | design 引用 L9/L23/L87/L104/L116/L89/L105/L125-126/L132、Q13 L7/11/13/15/64、W07 L3/L98、FINAL L11/L27/L96/L111/L112/L117 | 逐行核对全部命中 | ✅ 行号准确 |
| checker 门禁 | — | `ChangeType.primary = "process"`（非 docs）→ DESIGN_TYPES 含 process，grill-design.md 必查；`_check_review_manifests` 对 primary≠docs + 有 spec delta + tasks 全勾选时**强制 building-review.md** | ⚠️ docs-only 不豁免，`/review-loop` 必跑（tasks 8.1 已含） |

## Confirmed Decisions

- **决策**: D5 不引用 `comparison.md` 的 myagent 旧数字，C3 重跑后替换。理由: 实测 `benchmarks/reports/comparison.md` 为 2026-06 一次性产物，agent 名/任务集与当前不符，面试引用会暴露过期能力证据；与 T2 总原则 4 一致。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- **决策**: D4 C3 并行边界——现状口径修正零依赖 C3；升级叙事段标「设计已定、C1–C3 实现中」措辞稳定；不碰 `docs/benchmark-run-protocol.md`。理由: 实测该协议文档当前不存在（C3 未合入），C4 提前引用会悬空；「实现中」标注使 C3 合入前后数字变化只需收尾校准。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- **决策**: D3 升级不上简历——`~90/pass^k/cost@pass` 未实现不上简历（简历 bullet 7 只写现状口径），升级方向在面试讲稿里讲路线。理由: 符合总原则「不把未实现写成已实现」；简历是静态交付物，写入未实现能力是最直接的穿帮面。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- **决策**: 污染披露数字「138 实例 59.4% 缺陷」可进 Q13 面试重点。理由: 来源已落 `openspec/specs/benchmark/spec.md` L429-431（OpenAI 2026-02 弃用 Verified 审计），非凭空数字；面试被追问时可回指 spec 而非凭记忆。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- **决策**: FINAL L112「38 内置工具」保留 + 口径注明「38 内置（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」。理由: 实测 factory.py:71 集合恰 38 项（含 7 个 Browser* 工具）；「已知名数」比「默认模式启用名数」更精确，避免面试官现场数默认启用工具对不上。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`
- **决策**: Change Type 保持 `primary: process`（不改 `docs`）。理由: checker 对 `primary == "docs"` 会跳过 RIR/Impact Analysis 结构校验并跳过 building-review；本 change 已有完整 RIR+Impact 且 tasks 8.1 已含 `/review-loop`，保持 process 门禁更严、与「docs-only 也要审阅闭环」的仓库规则一致；改 docs 反而放宽门禁。来源: `f1c9210c-1fd3-47f2-9358-09b84b483d5a`

## Open Questions

- **Q1**: FINAL 速查表 L117「评测任务 36（26 本地 + 10 SWE-bench）」在 b01 已合入后写 36 还是 37？
  before: `| 评测任务 | 36（26 本地 + 10 SWE-bench） | benchmarks/tasks/ |`
  实测 `benchmarks/tasks/` = 27 本地（26 A 轨 + b01）+ 10 swebench = 37；README L178 已写「37 个编码任务」。
  after A（与 README 一致）: `| 评测任务 | 37（27 本地 + 10 SWE-bench） | benchmarks/tasks/ |`
  after B（保留 36）: 面试官按 README L178 数目录得 37，追问「为什么讲稿写 36、README 写 37」时穿帮；若强行注明「36 不含 B 轨 b01」，该口径又与 README「27 本地任务」冲突。
  **需用户拍板**：选 A 或 B；且若选 A，FINAL L11 电梯 pitch「36+ 任务」、L27 验证行「36+（26 本地 + 10）」、L96 bullet 7「36+ 任务」三处是否同步改「37」？——design D1 只列了 L117，未覆盖 L11/L27/L96。
- **Q2**: resume 本地任务数用 26（A 轨）还是 27（含 b01）？
  before（D3 草案）: "内置 26 个本地 coding-agent 任务 + SWE-bench Verified 子集，git worktree 隔离 + hidden test patch 确定性验证，bootstrap 95% CI（固定 seed）统计，pass@1/pass@k 指标，支持跨 agent 统一 harness 对比和 CI 回归门禁。"
  实测本地任务目录 = 27；README L36/L373「27 个本地任务」。
  after A（与 README 一致）: "内置 27 个本地 coding-agent 任务（26 A 轨回归基线 + 1 B 轨当前演进）+ SWE-bench Verified 子集，..."（草案其余不变）
  after B（保留 26）: "内置 26 个 A 轨本地回归任务 + SWE-bench Verified 子集，..."——明确 b01 不在口径内（b01 归升级叙事），接受与 README「27」的差异，面试被对照时主动解释。
  **需用户拍板**：D3 草案用 27 还是 26？连带 resume L9/L104「23→27」还是「23→26」、L87「34→27」还是「34→26」？tasks 6.3「26 + Verified 子集 表述避免过期」的意图需点明（26 是 A 轨数还是「不算 b01」的本地数）。
- **Q3**: FINAL 速查表 L111 测试文件/函数数写 135/1700+ 还是 148/~1997？
  before: `| 自动化测试 | 130 测试文件 / ~1691 测试函数 | tests/ |`
  design D1 目标: `| 自动化测试 | 135 测试文件 / 1700+ 测试函数 | tests/ |`
  实测: `git ls-files "tests/*.py"` 中 test_*.py = **148** 文件；`rg -c "^\s*(async def|def) test_"` 求和 = **1997** 函数（design「数字口径基线」的 135/1700+ 与当前 master 不符，疑似 C1/C2 合入前的旧数）。
  after A（与实测一致）: `| 自动化测试 | 148 测试文件 / ~1997 测试函数 | tests/ |`
  after B（design 的 135/1700+）: 面试官现场 `pytest --collect-only` 或 `find tests -name "test_*.py" | wc -l` 得 148/1997，对不上。
  **需用户拍板**：写 148/~1997 还是 135/1700+？连带 resume L23/L116「450+→1700+」是否改「~1997」（或保留「1700+」作下界——1997>1700 仍真，但文件数 148≠135 必改）；FINAL L11「1700+ 自动化测试」可不动（仍真）。
- **Q4**: `docs/interview-script/walkthrough/README.md` L27-L28 简历核实表的两处旧口径不在 4 份目标文档内，改不改？
  before: L27 `| "36+ 任务（26 本地 + 10 SWE-bench）" | 26 + 10 = 36 | ✅ |`；L28 `| "1700+ 自动化测试" | 130 文件 / ~1691 函数 | ✅ |`
  design 的目标文档清单只有 resume/Q13/W07/FINAL；tasks 6.1 的 grep 校验词表 `23 个/34 个/450+/claw-swe-bench/` **扫不到**「26 + 10 = 36」「130 文件 / ~1691」——即使 4 份文档改完，此表仍残留旧口径。
  after（若 Q1/Q3 选 A）: L27 `| "37 任务（27 本地 + 10 SWE-bench）" | 27 + 10 = 37 | ✅ |`；L28 `| "1700+ 自动化测试" | 148 文件 / ~1997 函数 | ✅ |`
  **需用户拍板**：是否把 walkthrough/README.md 纳入本 change（第 5 份目标文档）？若纳入，tasks 6.1 校验词表需扩展（加 `26 + 10`、`130 文件`、`~1691`）。
- **Q5**: D3「简历 bullet 7 改后草案」落到 `docs/resume-description.md` 的哪一处？——design 未指明落点。
  resume-description.md 无「bullet 7」结构；候选落点三处，before/after 完全不同：
  - after A: 替换 推荐写法 L9 的整句"内置 23 个 coding-agent 本地任务、SWE-bench Docker harness 路径，并接入 Claw-SWE-Bench 统一对比框架，..."——但 D3 草案是长子弹，塞进一行式 推荐写法 会破坏简洁风格（L7-10 是「简洁版」）。
  - after B: 替换 选项 A（L100-106）整个 3 行 block——D3 草案是单条长子弹，与选项 A 的 3 行结构不匹配。
  - after C: 替换/新增 展开版 §6 Benchmark 闭环（L87-90 的第 1 行"内置 benchmarks/ runner：34 个本地..."，L87 已在 D1 覆盖 34→26/27）。
  **需用户拍板**：D3 草案到底替换哪一处？若选 A，是否接受长子弹进简洁版；若选 B，选项 A 其余两行（AgentLoop/WorkspacePolicy）保留还是整体替换为 D3 单条？
- **Q6**: W07 L98 简历核实表「26 + 10 = 36 ✅」在 b01 合入后是否仍标 ✅？
  before: `| "36+ 任务（26 本地 + 10 SWE-bench）" | 26 + 10 = 36 | ✅ |`；W07 L3 顶部引用句同款"36+ 个 coding 任务（26 本地 + 10 SWE-bench 外部）"。
  实测 27 本地 + 10 = 37；design tasks 4.1「36+ 保留（当前准确，不改）」基于 26+10=36，已过期。
  after A: L98 `| "37 任务（27 本地 + 10 SWE-bench）" | 27 + 10 = 37 | ✅ |`；L3 同步"37 个 coding 任务（27 本地 + 10 SWE-bench 外部）"。
  after B: 保留「36+」（"+"表示至少 36，字面上 37≥36 仍真），但核实表达式改「27 + 10 = 37」并加注「简历写 36+ 为下界」。
  **需用户拍板**：W07 L3 顶部引用句 + L98 核实表是否都改（与 Q1 同口径联动）；若 Q1 选 B（保留 36），此处必须加「36+ = 下界」注记否则核实表数学错误。
- **Q7**: 升级叙事「场景化 ~90」的措辞如何避免被误读为已实现？
  背景: C1 规划 A 轨 20–24 + B 轨 12–16 + Verified 50 ≈ 82–90；当前实际仅 37 任务（27+10）。
  before（无标注版，FINAL 速查表新增行会被误读成"已有 90 任务"）: `| 评测任务（升级） | ~90 场景×难度分层 | ... |`
  after 草案（带目标/现状双要素）: `| 评测任务（升级目标） | ~90（设计已定：A 轨 20–24 + B 轨 12–16 + Verified 50；当前已落 37） | C1–C3 实现中 |`
  **需用户拍板**：FINAL 速查表升级行、W07 加分点、Q13 升级段三处的「~90」是否统一用「目标 ~90 + 当前 37」双要素标注；简历确认不上升级数字（D3 已定，不变）。
- **Q8**: T2 交付物缺失，Q13/FINAL/resume 的「逐字段落草案」从哪来？
  现状: design/proposal 引用 `docs/research/narrative-changes-2026-08-17.md` 为「精确编辑清单 + 关键段落草案」，但该文件在**全部 git 分支不存在**（`docs/research/` 目录不存在）。design D2 只给了升级段「加什么」（加场景×难度分层 + 三来源、加 pass^k/cost@pass/fault_owner、加配对比较、加污染披露），**没给逐字措辞**；Q13 L7「带过渡句区分『两类=执行类型轴』」、Q13 L15 污染披露句、FINAL 速查表升级数字行、resume 5 处 Claw 重锚逐句，均无 before/after 文本。
  after A（本 change 自足）: 在 design.md 内补齐全部逐字草案（D2 展开为每文件逐句 before/after），grill 确认后落稿——不依赖外部文件。
  after B（引用外部）: 用户提供 T2 文件实际位置（issue #153 附件 / Google Doc / 其他仓库路径），实现时读取。
  **需用户拍板**：选 A 或 B。若选 A，本 change 的 tasks 2.x/3.x/5.x 在落稿前必须先有逐字草案并经用户确认（停轮覆盖）；若选 B，需给出可访问路径。附注: proposal/design 的 RIR exempt reason 引用「#153 已关闭 + T2 已定稿」能通过 checker 的结构检查（命中 `#\d+`），但**实体文件缺失属不可验证依据**，User Confirmation 里必须记录草案实际来源，不能以「T2 已定稿」占位。

## 风险

- **数字口径换版本漂移**: design 的落稿目标（resume 26、FINAL 36、测试 135/1700+）本身与当前 master（27/37/148/1997）不一致。若直接按 D1/D3 落稿，本 change 修掉的只是「23/34/450+」这一版旧口径，却引入「26/36/135/1700+」这一版新旧口径——面试材料与 README（27/37）、现场实测（148/1997）仍对不上。D1/D3 与 risk 节「A 轨 26 + B 轨 1 = 27」自相矛盾，必须按 Q1–Q3 统一后再落稿。
- **「~90」被误读为已实现**: 升级段若只写「场景化 ~90」不带「目标/设计已定/当前 37」标注，面试官会问「90 个任务在哪」，且违反总原则「不把未实现写成已实现」。需按 Q7 统一双要素标注。
- **walkthrough/README.md 校验盲区**: 该文件的「26+10=36」「130/~1691」不在 4 份目标文档、不在 6.1 grep 词表，收尾后仍残留旧口径（Q4）。建议把 walkthrough/README.md 纳入修改清单并扩展 grep 词表。
- **Claw 重锚漏改**: resume 有 5 处 Claw 表述（L9/L89/L105/L125-126/L132）+ Q13 L64 共 6 处，design 只按 D1/D2 覆盖；若某处漏改会残留失效目录引用（`claw-swe-bench/` 已不在 tree）。落稿后应 grep `claw-swe-bench` 全 docs/ 确认清零（含 walkthrough/README）。
- **checker 门禁误判风险已排除但需执行**: Change Type=process（非 docs）→ tasks 全勾选时 `_check_review_manifests` 强制 building-review.md + manifest（tasks 8.1 `/review-loop` 已含，OK）；`_check_design_review_task` 要求 grill-design.md ≥3 Confirmed Decisions 且**全 Open Questions 有 User Confirmation 记录**（占位不计入）。本文件满足结构，但停轮确认必须逐条真实记录用户答复。
- **spec delta 场景可验证性弱**: delta 的 Scenario「现状数字 SHALL 与当前实现一致」未钉死「当前实现」的数字来源（27/37？148/1997？），机械校验时无对照锚点，容易随 Q1–Q3 漂移。建议落稿时在 Scenario 里钉死权威来源（如 `benchmarks/tasks/` 目录计数 + `rg "^\s*(async def|def) test_"` 求和），或引用本 change 归档后的实测数字。
- **C3 合入后升级段数字需校准**: C3 并行中（`docs/benchmark-run-protocol.md` 当前不存在），C4 收尾时若 C3 已合入，任务数/协议细节变化需按 tasks 7.6 校准；C4 不得提前引用 C3 协议文档。

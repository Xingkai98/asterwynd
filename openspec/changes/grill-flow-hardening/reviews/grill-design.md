# Grill 设计追问：grill-flow-hardening

- **Reviewer**: 独立零记忆设计评审 subagent（本 worktree 内直接执行；不继承任何开发上下文）
- **时间**: 2026-10-07
- **对象**: `openspec/changes/grill-flow-hardening/{proposal.md, design.md, tasks.md, specs/*/spec.md}`
- **方法**: 逐条读被改代码（`scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`）+ 上游 `mattpocock/skills` 权威文档核对 + 全仓 sweep（`grep -rn`）。凡标「证据」者均为本机真实读取/命令结果。
- **配套**: 本 change 引入的「设计阶段审阅闭环」产出见同目录 `grill-adversarial.md`（Verdict + Decision Challenge + Code-Resolved）。

## Confirmed Decisions

- **决策**: skill 引用名统一改为 `grilling`（**不是** `grill-with-docs`，也不是仓内 `/grill` 命令名）。
  - **理由**: 上游 `docs/productivity/grilling.md` 明说 `batch-grill-me` 已并入 `grilling`（round-based 追问回归原语），且 `grilling` 是 primitive，`grill-me`/`grill-with-docs` 只是它的两个 front door；`grill-with-docs` **额外**承诺写 `GLOSSARY.md` 与 ADR，而本仓的 grill 产出落在 change 的 `reviews/`，**不产项目 GLOSSARY/ADR**，故取 primitive 名更贴切。仓内 `/grill` 是 harness 命令（`.claude/` gitignore，不进 git），与 skill 名解耦，不能互相替代。
  - **证据**: 上游 `docs/productivity/grilling.md:54-55`（"Into this skill… There is no `batch-grill-me` to install, and no separate sequential skill either"）、`:16`/`:41`（`grill-with-docs` 写 GLOSSARY/ADR）、`:87`（"`grilling` is a **primitive**, not a step you schedule"）；本机已装 `~/.claude/skills/grilling/SKILL.md:1-25`（round/frontier 设计树追问，正对应本仓「设计树逐轮追问」口径）；`.gitignore:9`（`.claude/` 全量忽略）。

- **决策**: 「设计阶段审阅闭环」是 **grill 环节内部的审阅闭环**，产出 `reviews/grill-adversarial.md`，与实现完成后的 `/review-loop` **同构但对象不同**（审设计 vs 审代码），二者分属两阶段、并存。
  - **理由**: 4 个既有 `grill-adversarial.md` 先例真实存在且内容确为「证伪报告」；`/review-loop` 的产物是 `building-review.md`，由 checker 在**归档点**单独强制。把两者区分为「grilling（问）→ 设计阶段审阅闭环（对抗收敛）→ 停轮」与「实现完成后代码审阅」在语义与机械落点上都不冲突。
  - **证据**: `openspec/changes/archive/2026-10-03-tool-result-lifecycle/reviews/grill-adversarial.md:1`（"# 对抗验证：… grill 结论证伪报告"）+ 同目录 `building-review.md` 并存；`scripts/check_openspec_artifacts.py:1617-1622`（归档点强制 `building-review.md`）；`design.md:44`（D2 明确定位）。

- **决策**: checker 的 `_has_design_review_task` **同时接受**新名 `grilling` 与旧名（`grill-with-docs` / `batch-grill` / `等价设计追问`），二者皆无仍报错（向后兼容 + 不放松）。
  - **理由**: 现状匹配串为 `grill-with-docs`/`batch-grill`/`等价设计追问`；101 个归档 change 与 1 个在途 change 仍写 `batch-grill-me`，删旧名分支会误伤历史与在途；该分支只在**缺 `grill-design.md` 的结构化证据**时作为字面兜底，是兼容路径而非常规路径。
  - **证据**: `scripts/check_openspec_artifacts.py:672-678`（匹配串）、`:788-794`（fallback 分支）；`grep -rln batch-grill-me openspec/changes/archive/ | wc -l` = 101；`openspec/changes/add-minimal-tui-runtime-view/tasks.md:7`。

- **决策**: `## Code-Resolved Questions` 内的条目**不进停轮队列、不要求 `## User Confirmation`**；checker 与 guard 的「未确认」判定只读 `## Open Questions`。
  - **理由**: `_unconfirmed_open_questions` 只从 `_extract_open_question_indexes`（读 `## Open Questions`）取索引；guard 的 `_extract_open_question_indexes` 同样只读该节。因此把 code-decidable 问题**物理移出** `## Open Questions` 会同时让停轮队列与门禁放松——两处语义天然一致，不需要额外联动改造。
  - **证据**: `scripts/check_openspec_artifacts.py:814-820`（读 `## Open Questions`）、`:872-878`（`_unconfirmed_open_questions`）；`scripts/workflow_guard.py:434-456`（同款抽取）、`:398-402`（未确认即拦）。

- **决策**: 本 change 为 **process** 型、**零运行时改动**，改动面仅流程规格 + 一个 checker 判据 + 文档 + 测试。
  - **理由**: `DESIGN_TYPES = {feature, refactor, process}` 含 process，故本 change **自身**要过 design-review 门（必须自带 `grill-design.md` + 作答记录）；除此之外不触 `agent/`、CLI、Web、benchmark。
  - **证据**: `scripts/check_openspec_artifacts.py:31-32`（`ALLOWED_TYPES`/`DESIGN_TYPES`）；`proposal.md:62-69`（Impact Analysis 的不改项）。

## Open Questions

### Q2: 本轮是否就上 `grill-adversarial.md` 的**机械文件门**（D3）？

- **背景**: design D3 明写「留 grill 定」。机械门的触发面是「本 PR 新归档的非 docs + 有 spec delta」的 change。
- **具体例子**: 设本轮上机械门。那么下一个 `feature` change（有 spec delta）归档时，若其 `reviews/` 下只有 `grill-design.md` + `building-review.md`、没有 `grill-adversarial.md`，`check_openspec_artifacts.py` 在归档点将直接报错并让 PR 红：
  `ERROR: <archive>/: grill-adversarial.md missing — 归档点要求 post-grill 作答证据。`
  - **选项 A（本轮上）**: 与 AGENTS.md「机械强制」文化一致；缓解（允许如实写「无可证伪项」）已内建。代价：每个非平凡 change 多一个必产文件。
  - **选项 B（下轮上）**: 本轮只写进流程规格（spec delta 已含该 Requirement），机械门留到下一 change。代价：规格与门禁短暂不同步，靠 agent 自觉。
- **建议**: **A**。「靠人记得」正是本 change 要治的病（4 个先例只覆盖部分 change），且本 change 自身已产 `grill-adversarial.md`，可自证门不误伤。

### Q3: 是否为 `## Code-Resolved Questions` 加一道**机械证据形状校验**？

- **背景**: D4 让 code-decidable 问题移出停轮队列，但「问题是否真的 code-decidable」目前**只能由作答 subagent 自述**（理由中的 `文件:行号` 无机械形状要求）。理论上一个想省事的 run 可把**用户取舍**写成一条带假 `file:line` 的 Code-Resolved 条目，从而悄悄绕过停轮门（`_unconfirmed_open_questions` 会因此不再要求确认）。
- **具体例子**: 某 change 的 Open Question 是「新 CLI 默认输出用 JSON 还是表格？」（这是**产品意图**，非代码可判定）。作答 run 把它写成：
  `- **Q4**（code-resolved）: 结论：用 JSON。证据：cli/output.py:88` —— 该行其实只定义了 `OutputFormat` 枚举、并未「决定」默认值。
  - **选项 A（加形状校验）**: 要求每条 code-resolved 条目内必须含 `\S+:\d+` 形状 token（正则即可），与 grill 证据要求「≥3 条决策」同构。→ 拦住「空答」，但**拦不住**「构造一条形状合法的假证据」。
  - **选项 B（不加）**: 维持纯语义约束，如实记录为已知边界（design R2 已自认「语义约束，非机械可验」）。
- **建议**: **A**（低成本、与既有机械文化一致），同时明确它只保证「有证据样」而非「证据真」——真伪仍靠停轮时人的一眼核对。

---

## Code-Resolved Questions

- **Q1（原 Open Question）→ code-resolved**：改名范围是否纳入**在途** change `add-minimal-tui-runtime-view`？
  - **结论（由代码定）**：**纳入**。该在途 change 仍引用旧名共 2 处——`openspec/changes/add-minimal-tui-runtime-view/design.md:53` 与 `.../tasks.md:7`；其处于 proposal 阶段（0/18 未实现），改名成本最低，且「文档不得引用装不到的 skill」是本 change 的 Why 核心，留例外自相矛盾。
  - **附带约束**：task 6.1 的 `grep` 验收须额外允许本 change 自身目录（`openspec/changes/grill-flow-hardening/**`，其合法描述这次改名）——见 design R1 修正。
  - **证据**：`openspec/changes/add-minimal-tui-runtime-view/{design.md:53,tasks.md:7}`；设计审阅闭环 R1（`grill-adversarial.md`）判定。


## User Confirmation

- **Q2**: 用户答复：**A（本轮就上机械门）**——`reviews/grill-adversarial.md` 加入 checker，归档点强制其存在（与 `building-review.md` 归档点同口径，落点 `_check_archived_completion_gate`）。；确认时间: 2026-10-07
- **Q3**: 用户答复：**B（不加形状校验）**——`## Code-Resolved Questions` 维持纯语义约束，不引入 `文件:行号` 正则门槛；「是否真 code-decidable」靠停轮时用户核对。；确认时间: 2026-10-07

# Design: grill 环节加固

## Context

本仓的强制设计追问（grill）由三部分构成：**skill**（agent 加载来做追问）+ **harness**（`/grill` 命令、workflow_guard、artifact checker 强制结构化记录）+ **规格**（`change-documentation` 等 spec 定义 Requirement）。

### 已核实的事实（本设计的地基）

1. **`.claude/` 全量 gitignore**（`.gitignore:9`）——所以 `/grill` 命令文件**不进 git**，**可提交的流程定义只落在 `AGENTS.md` + `openspec/specs/**`**。本 change 改的是后者（及文档）。
2. **「设计阶段审阅」已有 4 个先例**（此前以 `grill-adversarial.md` 之名、作为**惯例**而非流程要求存在）：`find openspec/changes -name grill-adversarial*.md` → `2026-10-02-read-output-bound` / `2026-10-03-foreach-budget-truncation-visibility` / `2026-10-03-tool-result-lifecycle` / `2026-10-03-foreach-truncation-visibility`。本 change 把它**从惯例提升为「设计阶段审阅闭环」流程规格**（加 verdict + 审→改→再审收敛），与实现完成后的 `/review-loop` **同构但阶段/对象不同**。
3. **checker 的 tasks 判据**：`_has_design_review_task`（`scripts/check_openspec_artifacts.py:672`）匹配字面串 `grill-with-docs` / `batch-grill` / `等价设计追问`（`等价设计追问` 命中 `tests/test_openspec_artifact_checker.py:103` 的中文变体用例）。既有在途/归档 tasks.md 大量写 `batch-grill-me`。
4. **checker 的 grill 证据门**（`_check_design_review_task`）：对 **active** change，有 `reviews/grill-design.md` 且 `## Confirmed Decisions ≥ 3` 即通过；tasks 全勾时校验每个 `## Open Questions` 有 `## User Confirmation`。**触发点是归档点**（issue #235）——只对本 PR **新归档**的 change 求值，不追溯历史。
5. **停轮确认**（grill-confirmation-gate）：Open Question 必须逐条配「具体例子/场景」抛给用户，答复记 `## User Confirmation`；占位文本不计。
6. **上游 skill 现状**：`mattpocock/skills` 已删 `batch-grill-me`，round-based 追问并入 `grilling`（直接继任者）；`grill-with-docs` 是「追问 + 顺带产 ADR/GLOSSARY」的变体。

## Goals / Non-Goals

### Goals

- 活跃文档与 spec 不再引用装不到的 skill 名（对齐上游）。
- 流程规定 **grill → 设计阶段审阅闭环（独立零记忆审阅者，对抗分析 → verdict → 修 → 再审直到收敛）→ 停轮只抛真正要用户拍板的**；产出 `reviews/grill-adversarial.md`（与实现后 `building-review.md` 平行）。**实现后的 `/review-loop` 不动、继续存在。**
- 「代码可判定的 Open Question 由审阅者带证据直接定、移出停轮队列」成为**明确语义**，减少用户决策带宽浪费。
- checker 对旧名与新名都判「有设计追问任务」；二者皆无仍报错（向后兼容 + 不误伤历史）。

### Non-Goals

- **不改** `agent/` 运行时、CLI/Web/benchmark 行为。
- **不改** 101 个归档 change 的 tasks/引用（不可变历史）。
- **不引入**新 skill、新依赖或新命令；`grilling` 是上游既有 skill。
- **不重构** grill 的 harness 层（`/grill` 命令 + guard 的既有机制不动，只改流程定义文本 + checker 判据）。
- 不改 `## User Confirmation` 的格式契约。

## Decisions

### D1 — skill 引用名 = `grilling`（保留 `grill-with-docs` 为可选姊妹）

- **选定**：文档里「必须使用的 skill」引用名改为 **`grilling`**。
- **理由**：`grilling` 是 `batch-grill-me` 的**直接继任者**（上游明说 round-based 追问并入了它），语义等价替换最小；`grill-with-docs` 额外承诺产 ADR/GLOSSARY，而本仓的 grill 不必然产这些（决策记录落在 change 的 `reviews/`，不是项目 glossary）。harness 层（`/grill` 命令 + guard）负责本仓特有的「结构化记录 + 停轮门」，与 skill 名解耦。
- **备选**：`grill-with-docs`——若认为「grill 产出 `grill-design.md` 就是产文档」更贴切，可改选。**已定：取 `grilling`**（D1 经设计审阅闭环 R1 判 survives）。
- **兼容**：checker 同时接受 `grilling`（新）+ `batch-grill`/`grill-with-docs`/`等价设计追问`（旧），故新旧文档都能过门。

### D2 — **设计阶段审阅闭环**（本文档核心；与实现后 `/review-loop` 同构、对象不同）

**澄清定位**：grill 环节 SHALL 内含一个**审阅闭环**，形态与实现完成后的 **`/review-loop` 完全同构**——spawn 独立零记忆审阅者 → **对抗分析** → 出 verdict → 修 → **再审，直到收敛**——但它**审的对象是「设计」**（`grill-design.md` / `design.md`），不是代码。**实现后的 `/review-loop` 完全不动、继续存在**（它审代码、产物 `building-review.md`）；二者是**两个阶段、两个独立 loop**：

| | 设计阶段审阅闭环（本 change 新增） | 实现后 `/review-loop`（**不动**） |
|---|---|---|
| 何时 | grill 出结论后、停轮**前** | 实现完成、发起 PR **前** |
| 审什么 | **设计**（决策/假设/Open Questions） | **代码/实现** |
| 产物 | `reviews/grill-adversarial.md` | `reviews/building-review.md` |
| 收敛 | 审→改→再审，PASS 或 **轮数封顶** | 审→改→再审，PASS 或 **3 轮封顶** |

- **形态**（对齐 `/review-loop`）：spawn 独立零记忆审阅 subagent → **对抗分析**（默认设计有错、逐条尝试证伪 Confirmed Decisions 与设计假设）→ 出 **verdict**（`PASS` / `CHANGES_REQUESTED`）→ `CHANGES_REQUESTED` 则**修 `grill-design.md` 并补正文** → **再审**，**直到 `PASS` 或轮数封顶**（与 review-loop 的 3 轮封顶对齐）。
- **额外职责（用户 2026-10-07 要求）**：该闭环内，对每条 Open Question——**能由代码判定的**，由审阅者**带证据（`文件:行号`）直接答出**，移出停轮队列（见 D4）；只有真正的用户取舍才留在 `## Open Questions` 交停轮。
- **产出**：`openspec/changes/<id>/reviews/grill-adversarial.md`（verdict + 逐条 issue `文件:行号` + 对抗结论 + Code-Resolved 答案）。**命名说明**：与 `building-review.md` 平行；既有 4 个 `grill-adversarial.md` 先例是本闭环的**非正式前身**，本 change 把它规格化、加 verdict 与收敛语义（名字已定：`grill-adversarial.md`，沿用先例）。
- **理由**：① 实测教训（`#280`）——grill 结论可能站不住，需要**同种对抗闭环**在设计定稿前拦住；② 大量问题**本就该代码答**，不该占用户决策带宽；③ 与实现后 review-loop **同构**意味着一套心智模型、复用既有 `/review-loop` 纪律，不发明新范式。

### D3 — 设计阶段审阅证据**机械强制**（归档点；落点 = `_check_archived_completion_gate`）

**落点（经设计审阅闭环 R1 修正 F2）**：building-review 有**两个**执法点——
- `_check_review_manifests`（`scripts/check_openspec_artifacts.py:1127-1150`）：**活动/漂移面**，条件含 `not archived and ... and _tasks_all_complete`，按「活动 change」逐目录求值、与 PR diff 无关。
- `_check_archived_completion_gate`（`:1614-1622`，经 `_check_new_archived_completion_gates` `:1645-1667` 只对**本 PR 新归档**目录求值）：**归档点面**，条件 `primary!=docs and 有 spec delta`，**不含** `_tasks_all_complete`（归档侧传 `assume_implemented=True`）。

本 change 的 `grill-adversarial.md` 门 SHALL 加在 **`_check_archived_completion_gate`**（真正的归档点，只对本 PR 新归档求值、**不误伤在途**）。**不加**到 `_check_review_manifests`（那会把任何 tasks 全勾的在途 change 拉进来，恰是要避免的误伤）。

- **口径**：对**本 PR 新归档**的、非 docs + **属 DESIGN_TYPES（feature/refactor/process）** + 有 spec delta 的 change，要求 `reviews/grill-adversarial.md` **存在**（存在性门，与 building-review 在归档点的**存在性**判据同构；building-review 归档点本就是「存在性 only」，非 manifest）。**比 building-review 多一道 `DESIGN_TYPES` 前置**——因为该闭环是 grill 环节的收口，而 grill 只对 DESIGN_TYPES challenge；bugfix/research 不走 grill，要求其产此文件会是「要求一个输入不存在的产物」（R2 修正）。
- **理由**：本仓文化是机械强制（「靠人记得」= 会漏，4 个先例只覆盖部分 change 即为例证）；触发点选归档点 = 不新增独立触发面、不追溯历史、不误伤在途。
- **风险与缓解**：新增必需 artifact 抬高每个非平凡 change 成本。缓解：① 与 building-review 对称，成本可预期；② 允许在本 change 太小、无实质可审时，文件里**如实写「`PASS`：未发现可证伪项 / Open Questions 空」**而非豁免文件本身（保留证据面）。
- **留 grill 定**：是否本轮就上机械门（**倾向本轮上**，与 AGENTS.md「机械强制」一致）——见 stop-turn Q2。

### D4 — 「能代码定的答案用代码定」= Open Question 的**分类语义 + 落点**

- 设计阶段审阅闭环对每条 Open Question 打标并处置：
  - **`code-resolved`**：读代码 / 跑桩即可有确定答案 → 审阅者**带证据（`文件:行号`）直接给出答案**，记入 `grill-design.md` 的新节 **`## Code-Resolved Questions`**（含 `Q#`、结论、证据），**移出 `## Open Questions`**，**不停轮**。
  - **`user-decision`**：真正的用户取舍 → 保留在 `## Open Questions`，按既有 grill-confirmation-gate **配具体例子停轮**。
- **门禁含义**：checker 的「Open Question 必须有 `## User Confirmation`」只对 `## Open Questions` 生效（`_unconfirmed_open_questions` 读该节）；`## Code-Resolved Questions` 不要求用户确认（由代码定，非用户决策）。**这使「把该代码答的问题移出停轮队列」有可机械校验的落点**。
- **理由**：区分的本质是「**验证**（机器可做）vs **决策**（必须人做）」——机器能验的不该占用户带宽。

### D5 — 文档与 spec 的改动面

| 文件 | 改什么 |
|---|---|
| `AGENTS.md` | 4 处 `batch-grill-me` → `grilling`；在 grill 段落**加对抗验证 + 代码可判定语义** |
| `docs/requirements-process.md` | 8 处引用名；流程步骤加对抗环节 |
| `docs/agents/domain.md` | 2 处引用名 |
| `openspec/project.md` | 2 处引用名 |
| `openspec/templates/tasks.md` | 1 处引用名 |
| `openspec/specs/change-documentation/spec.md` | grill Requirement 增对抗 + 代码可判定语义；`batch-grill-me is unavailable` Scenario 改名 |
| `openspec/specs/dev-workflow-state-machine/spec.md` | 流程链里的 `batch-grill-me` → `grilling` + 对抗 |
| `openspec/specs/subagents/spec.md` | Reviewer scenario 的 `batch-grill-me` 引用名 |
| `scripts/check_openspec_artifacts.py` | `_has_design_review_task` 加 `grilling`；错误文案；D3 的对抗文件门 |
| `tests/test_openspec_artifact_checker.py` | 新名匹配 + 旧名仍匹配 + 皆无仍报错 + 对抗文件门的回归 |
| `openspec/changes/add-minimal-tui-runtime-view/{design.md,tasks.md}` | 在途 change 的 2 处旧名（task 3.6；经设计审阅闭环 R1 判 code-resolved） |

## Risks / Trade-offs

- **R1 改名不彻底**：漏改某处 → 文档自相矛盾。缓解：穷举表 + 完成后 `grep -rn batch-grill-me`（**允许面**：`openspec/changes/archive/**`（历史）+ 本 change 自身目录 `openspec/changes/grill-flow-hardening/**`（合法描述这次改名）——余者应为空；经设计审阅闭环 R1 修正 F3）。
- **R2 审阅形式化**：对抗/证伪变成走过场（「survives 全部通过」/ 空答）。缓解：spec 要求审阅者**默认假设结论有错、逐条证伪**，且每条 `code-resolved` 必带证据；如实记录「无可证伪项」而非编造。**这是语义约束，非机械可验——如实记录为已知边界**。
- **R3 门禁误伤**：新审阅门若触发过宽 → 在途 change 被拦。缓解：触发点=归档点（issue #235），只对本 PR 新归档求值；本 change 自身归档前会产 `grill-adversarial.md`。
- **R4 新旧名并存引起混淆**：checker 接受旧名 → 有人继续写旧名。缓解：文档一律新名；旧名匹配仅为**兼容历史/在途**，非鼓励。
- **R5 skill 再次改名**：上游会继续演进。缓解：这是**流程引用**而非硬编码依赖；配合 `skills.sh` 周更（外部已配），未来改名同法再对齐。

## Testing Strategy

- **checker 单测**（`tests/test_openspec_artifact_checker.py`）：
  - `grilling` 出现在 tasks → `_has_design_review_task` 通过。
  - `batch-grill-me`（旧名）仍通过（向后兼容）。
  - 二者皆无 + 无「等价设计追问」→ 仍报错（不放松）。
  - `## Code-Resolved Questions` 不计入未确认 Open Question（新语义）。
  - 设计审阅门：新归档缺 `grill-adversarial.md` → 报错；存在 → 通过。
- **文档一致性**：`grep -rn batch-grill-me` 在活跃文档/spec 应为空（archive 与 本 change 自身目录 除外；见 R1）。
- **门禁**：OpenSpec strict validate + artifact checker + 全量 pytest。

## Pre-Implementation Review

- 本 change 自身走完整流程：grill（独立零记忆）→ **设计阶段审阅闭环**（本 change 引入的机制，自我实践）→ 停轮确认 → 实现。
- 独立 grill 对本文档逐条追问（触发条件、误伤、D3 是否本轮上机械门、D4 分类边界），产出 `reviews/grill-design.md`。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis`（能力域 / 代码 / 测试 / 文档 / 受保护路径 / 不改项）。**核心**：纯流程规格 + 一个 checker 判据 + 文档，**零运行时行为改动**。

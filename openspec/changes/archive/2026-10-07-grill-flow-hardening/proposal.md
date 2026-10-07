# Proposal: grill 环节加固（grill-flow-hardening）

关联跟踪 issue：[#298](https://github.com/Xingkai98/asterwynd/issues/298)（【feature】grill 环节加固）。

## Change Type

- primary: process
- secondary: []

## Why

本仓强制的**设计追问（grill）**环节有两个问题，一起治。

### 问题 A：流程文档引用了装不到的 skill 名

流程文档一律引用 skill **`batch-grill-me`**，但该 skill **在上游已不存在**——`mattpocock/skills` 已把 round-based 追问并入 `grilling`：

> `docs/productivity/grilling.md`："There is no `batch-grill-me` to install, and no separate sequential skill either."

现状：活跃文档 5 份（`AGENTS.md` 4 处、`docs/requirements-process.md` 8 处、`docs/agents/domain.md` 2 处、`openspec/project.md` 2 处、`openspec/templates/tasks.md` 1 处）+ 受保护 spec 3 份（`change-documentation` / `dev-workflow-state-machine` / `subagents`）都在引用一个装不到的 skill；现仅靠 AGENTS.md 里「环境没有该 skill 就按同等标准追问」的 fallback 兜底。

### 问题 B：grill 的问题未经作答就停轮抛给用户

现状：**只有实现完成后**有 `/review-loop`（代码审阅）；**grill 产出**（Confirmed Decisions + Open Questions）**未先在 grill 环节内作答**就直接停轮交给人。两个后果：

- **该由代码答的问题被推给人**：很多 Open Question 读代码 / 跑桩就有确定答案，却占了用户的决策带宽。
- **结论可能站不住**：实测教训——`#280` 的 grill 修法被后续核查发现有洞（`grill-conclusions-need-adversarial-review`）。

**关键定位**：要加的是 **grill 环节内含的「设计阶段审阅闭环」**——与实现完成后的 `/review-loop` **同构**（spawn 独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审直到收敛），但**审的对象是「设计」**（`grill-design.md` / `design.md`）不是代码；**实现后的 `/review-loop` 完全不动、继续存在**（它审代码、产物 `building-review.md`）。两个 loop 分属两阶段、产物不同。

**该步骤在本仓其实已有 4 个先例**（以 `reviews/grill-adversarial.md` 之名、作为惯例）：`2026-10-02-read-output-bound` / `2026-10-03-foreach-budget-truncation-visibility` / `2026-10-03-tool-result-lifecycle` / `2026-10-03-foreach-truncation-visibility`——但**没写进流程与规格**，靠人记得做。

## What Changes

把 grill 环节加固成 **grill → 设计阶段审阅闭环（独立零记忆审阅者，对抗分析 → verdict → 修 → 再审直到收敛；顺带作答能代码定的问题）→ 停轮只抛真正要用户拍板的**（实现后 `/review-loop` 不动）：

1. **skill 名对齐上游**：引用名 `batch-grill-me` → `grilling`（上游直接继任者；`grill-with-docs` 为其「产文档」变体）。更新 5 份文档 + 3 个受保护 spec 的引用；**保留**「环境没有该 skill 时按同等标准追问」的 fallback。
2. **设计阶段审阅闭环**：grill 产出 `reviews/grill-design.md` 后、**停轮前**，跑一个与 `/review-loop` 同构的闭环——独立零记忆审阅者**对抗分析**（逐条尝试证伪 Confirmed Decisions 与设计假设）→ 出 verdict（`PASS` / `CHANGES_REQUESTED`）→ 修 `grill-design.md` → **再审，直到 `PASS` 或轮数封顶**；产物 `reviews/grill-adversarial.md`（与 `building-review.md` 平行；既有 `grill-adversarial.md` 为其非正式前身）。
3. **能代码定的答案用代码定**：审阅闭环对每条 Open Question 分类——**代码可判定**的（读代码 / 跑桩即可有确定答案）**带证据（`文件:行号`）直接定**，移出 `## Open Questions`、落进新节 `## Code-Resolved Questions`，**不停轮**；只有真正的用户取舍才留停轮队列（配具体例子，按既有 grill-confirmation-gate）。
4. **门禁兼容**：`scripts/check_openspec_artifacts.py` 的 `_has_design_review_task` 加 `grilling` 匹配、**保留 `batch-grill` / `grill-with-docs` / `等价设计追问` 匹配**（避免 101 个归档 change 与在途 change 被误伤）；错误文案同步；补回归测试。是否对 `grill-adversarial.md` 加机械证据要求，见 design 的 D3。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `change-documentation`（process）：grill Requirement 增「设计阶段审阅闭环」与「代码可判定问题由代码定」的语义，并更新 skill 名引用。
- `dev-workflow-state-machine`（process）：流程链 `proposal → X → worktree → TDD → PR` 的 `X` 由 `batch-grill-me` 改为「grilling + 设计阶段审阅闭环」；更新 skill 名。
- `subagents`（process）：Reviewer agent scenario 里「而非执行 `batch-grill-me`」的引用名更新。

## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 常规流程增强（把已有实践正式化 + 更新一个上游改名），非架构级改造，无新框架/依赖/协议；按 light 档浅调研。
- findings: **本地参考仓库无直接对应**——对 `/home/shared/agent-study/reference-repos/{codex,pi,deepseek-harness,kimi-code,zcode,opencode}` 检索 `red-team`/`adversarial`/`design review` 两步式，命中均为测试名或无关文档噪声，**未见「设计阶段先对抗再定稿」的成型机制**。业界通用实践为**对抗式验证 / LLM-as-critic**（生成后由独立视角尝试证伪，而非自我确认）与「可机械验证的结论应交给机器」。本仓已有 **4 个 `grill-adversarial.md` 先例**（见 `Why`）证明该实践在本地有效，本 change 把其**从惯例提升为流程规格**。
- design impact: 对抗验证作为 grill 的**强制步骤**写进 `change-documentation` spec；「代码可判定问题由代码定」作为**问题分类**语义落进同一 Requirement；门禁上用既有 `grill-design.md` 证据 + 新增 `grill-adversarial.md`（受控，见 design D3）。

## Impact Analysis

- **能力域**：`change-documentation` / `dev-workflow-state-machine` / `subagents`（均为流程规格，非运行时行为）。**不改任何 `agent/` 运行时语义**。
- **代码**：`scripts/check_openspec_artifacts.py`（`_has_design_review_task` + 文案，向后兼容）。
- **测试**：`tests/test_openspec_artifact_checker.py` 增新名匹配 + 旧名仍匹配 + 二者皆无仍报错的回归用例。
- **文档**：`AGENTS.md`、`docs/requirements-process.md`、`docs/agents/domain.md`、`openspec/project.md`、`openspec/templates/tasks.md`。
- **受保护路径**：`openspec/specs/{change-documentation,dev-workflow-state-machine,subagents}/spec.md`（需 `current_spec_synced` 事件）；归档目录（需 `change_archived` 事件）；backlog（需 `backlog_updated` 事件）。
- **不改**：101 个归档 change、`agent/` 运行时、CLI/Web/benchmark 行为。

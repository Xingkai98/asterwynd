# AGENTS.md

本文件是编码 agent 和 Claude Code 进入本仓库时的入口说明。它只保留最高优先级规则和文档地图；详细背景请按链接读取对应文档。

> **维护规则**: `AGENTS.md` 是唯一维护入口。`CLAUDE.md` 只保留 `@AGENTS.md`，不再重复维护完整说明。`README.md` 是 README 源文档；修改 `README.md` 时必须在同一变更中同步更新 `README_EN.md` 的英文翻译，保持章节、命令和事实口径一致。

## 项目定位

Asterwynd 是一个面向大厂 Agent 相关开发岗位的 Coding Agent 系统项目。主线是 Agent 运行时、工具调用、上下文管理、代码修改、验证、可观测性和 benchmark 闭环；AI Infra、LLM、RAG、后端工程能力都作为支撑能力服务于这条主线。

项目词汇以 [CONTEXT.md](./CONTEXT.md) 为准。

## 最高优先级规则

- **文档语言**: 除 `README_EN.md` 作为 `README.md` 的英文同步翻译外，所有项目文档使用中文；代码、代码注释和公开 API 命名使用英文；提交信息使用中文。
- **需求先行**: 新功能必须先完成需求讨论和需求文档，再进入开发。没有把目标、边界、验收标准、测试策略聊清楚之前，不写实现代码。
- **设计追问**: 非平凡 OpenSpec change 进入实现前，必须使用 `batch-grill-me` skill（设计树逐轮追问，一轮问整个 frontier，效率更高）审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响；如果当前环境没有该 skill，必须按同等标准充分追问并记录最终方案。用户要求“开始开发 / 实现 / 做某个 change”时，第一阶段必须先加载并声明使用 `batch-grill-me`，在逐项确认完成前不得写实现代码或测试代码；agent 可以给推荐答案，但不能把自己的推断当作用户确认。**机械强制（issue #95）**：grill 由独立零记忆 subagent 执行（`/grill` 命令），产出结构化决策记录到 `openspec/changes/<id>/reviews/grill-design.md`；workflow_guard 在写代码前检查该证据，缺失则阻止写操作；artifact checker 对完成 change 验证证据存在且 ≥3 条决策。**停轮确认（grill-confirmation-gate）**：grill 产出后，agent 必须**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复；收到答复前不得写实现代码。用户答复记录进 `grill-design.md` 的 `## User Confirmation` 节（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）。workflow_guard 在 Open Questions 未全部确认时仍拦截代码写；artifact checker 对 tasks 全勾选的完成 change 校验每个 Open Question 都有确认记录。占位文本（`待确认`/`待主 agent 提交` 等）不计入确认。**分支纪律**：每次开发必须切 `<change-id>/<YYYY-MM-DD>` 分支（门禁依赖分支名推导 change-id）。
- **参考实现调研门禁**: 非 docs OpenSpec change 默认必须启用参考实现调研，并在 `proposal.md` 或 `design.md` 维护 `## Reference Implementation Research`，记录 `status`、`reason`、`research questions`、`findings` 和 `design impact`。确实不适用时可写 `status: disabled`，但必须说明原因。该门禁由项目 artifact checker 和 CI 机械检查；checker 不读取本地 `.dev/reference-repos.txt`，本地参考仓库不可用时必须在 change 文档中记录不可用事实和替代依据。
- **问题定位**: 定位问题时，先查清根因并给出解决方案，待确认后再实际修改代码。
- **测试要求**: 每个 bug fix 必须新增回归测试；涉及 CLI、Web、benchmark、工具协议或 AgentLoop 的变更必须覆盖对应层级测试。
- **CI 与影响分析**: 非平凡 OpenSpec change 必须维护结构化 `Impact Analysis`，并在开发中发现新影响面时先回写 change 文档和任务清单；baseline CI 门禁包含全量 pytest、OpenSpec strict validate 和项目 artifact checker。`unknown` / `TBD` / `待确认` 可在 proposal 阶段短暂存在，但归档前必须清理为明确结论或阻塞项。
- **文档影响检查**: 收尾阶段必须检查文档影响，但不要无边界全量改文档。至少检查 change 自身 OpenSpec 文档、`docs/openspec-change-backlog.md`、文档地图中的相关入口文档，并用关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与本次变更相关的段落；只更新当前变更造成的事实变化，历史口径问题另记债务或单独处理。
- **受保护 artifact 证据**: 修改 `docs/known-issues.md`、`docs/known-debt.md`、`openspec/specs/**`、`docs/openspec-change-backlog.md` 或 `openspec/changes/archive/**` 时，必须有 `workflow-events.jsonl` 中的结构化解释事件；阶段 review report 必须有对应 review manifest 绑定 reviewer run、base/head sha、tasks/spec/diff/report hash。禁止只靠手写 `PASS` 文本通过 gate。
- **OpenSpec 收尾**: OpenSpec change 的实现 PR 必须同时包含归档收尾：将已完成 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`，从 `docs/openspec-change-backlog.md` 移除，并运行 OpenSpec 校验和项目 artifact checker。PR 合入后只做确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进到 `origin/master`。
- **自然语言路由**: 用户不需要反复提醒“按 OpenSpec lifecycle 走”。当用户用自然语言表达讨论、立项、开发、同步 spec、收尾或合入意图时，agent 必须自动映射到本文件的 OpenSpec 流程和 `/opsx:*` 等价步骤；如果当前客户端不能直接调用 slash command，也要按同等步骤执行。
- **协议约束**: 保持 tool-call 消息链合法；不要在 `max_iterations` 路径中用工具结果伪造最终 assistant 回复。
- **工作区约束**: 不提交 `.codegraph/`、`.understand-anything/`、`.dev/`、本地 `.env*`、日志、benchmark runs 等生成或本地文件，除非用户明确要求。
- **已有改动**: 可能存在用户未提交改动。不要回滚不是自己产生的改动；如果影响当前任务，先理解并基于它继续。

## 参考实现调研

当需要设计或对比某个 coding-agent 能力的实现方式时，应先查找当前工作区可用的参考仓库，并用 codegraph 加速调用链、类型关系和模块边界分析。非 docs OpenSpec change 默认启用该调研；若关闭，必须在 change 文档中显式写明原因。

- 当前工作区参考仓库路径应写在本地配置 `.dev/reference-repos.txt` 中，每行一个目录路径；该文件不提交。
- 这些路径只是当前工作区的参考资料位置，不是项目依赖，也不要求其他开发者拥有相同目录结构。
- 不要把参考仓库路径、`.codegraph/` 产物或本地索引结果作为可提交项目资产；若需要沉淀结论，应写入本仓库的需求、设计、ADR 或讨论纪要。
- 调研时优先用 codegraph 理解跨文件关系，再用 `rg`、文件阅读和测试补充验证；不要只凭关键词搜索下结论。
- 如果 codegraph 或本地参考仓库不可用，应在 `## Reference Implementation Research` 的 findings 中记录不可用事实，并说明改用的依据。

## Agent skills

### OpenSpec 命令安装

本仓库启用 OpenSpec 命令：`/opsx:explore`、`/opsx:propose`、`/opsx:apply`、`/opsx:sync`、`/opsx:archive`。

命令文件由 `openspec init` 生成到对应工具的命令或 skill 目录。如果对应路径下命令文件缺失，需执行以下命令安装：

| 工具 | 安装命令 | 生成位置 |
| --- | --- | --- |
| **Claude Code** | `npx openspec init --tools claude` | `.claude/commands/opsx/` |
| **Codex** | `npx openspec init --tools codex` | 当前 Codex 环境的全局 prompts / skills，例如 `/home/happy/.codex/prompts/opsx-*.md` 和 `/home/happy/.codex/skills/openspec-change-lifecycle/` |

> 首次进入仓库时，agent 应检查 Claude 本地命令目录以及当前 Codex 环境是否可用 `/opsx:*`。如缺失，自动执行上述安装命令补齐。新版 OpenSpec 的 Codex 初始化可能写入用户级 Codex 目录，而不是仓库内 `.codex/`。

### OpenSpec 自然语言路由

agent 应把用户的自然语言意图自动路由到对应流程，而不是等待用户显式输入 slash command。

| 用户自然语言意图 | 自动采用的流程 |
| --- | --- |
| “讨论一下 / 想想方案 / 看看怎么做 / 有哪些方向” | 进入 `/opsx:explore` 等价流程：读取相关代码和文档，只探索和记录，不写实现代码。 |
| “新起一个 change / 我要做一个功能 / 改一个东西” | 进入 `/opsx:propose` 等价流程：创建或补齐 OpenSpec change、proposal、design、tasks、spec delta，并同步 backlog。 |
| “开始开发 / 实现这个 change / 按 change 推进” | 先执行 `batch-grill-me` 开发前设计追问；确认完成后进入 `/opsx:apply` 等价流程，按 tasks 测试先行并实现。 |
| “同步 spec / 看正式规格有没有更新” | 进入 `/opsx:sync` 等价流程：把 change delta spec 合理合并到 `openspec/specs/`。 |
| “收尾 / 提 PR / 准备合入” | 进入 `/opsx:archive` 等价流程：在同一个实现 PR 内归档 change、清理 backlog、跑 OpenSpec 校验和 artifact checker，并写明验证结果。 |
| “合入 / merge” | 合入已准备好的 PR；合入后只确认本地 `master` 已同步、active change 目录不存在、backlog 不再引用已归档 change。 |

这些命令只负责 OpenSpec 子流程；仓库规则仍然更高优先级。尤其是：非平凡 change 开发前必须 `batch-grill-me`，bug fix 必须有回归测试，README 改动必须同步 `README_EN.md`，PR 发起前必须完成归档收尾。

## 开发流程：OpenSpec 主干 + 强制审阅闭环

**这是最高优先级行为规则。** 本仓库的开发流程精简为两部分：**OpenSpec 主干**（需求→设计→实现→收尾）加 **实现完成后强制独立 subagent 审阅闭环**。旧的四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）已停用，不再需要 discover/advance/approve。

### 主干流程

| 阶段 | 产出 | 工作区 |
|------|------|--------|
| 需求讨论 | 讨论方案、明确边界 | 主仓库 |
| proposal / design | `openspec/changes/<id>/proposal.md` + `design.md`，非平凡 change 先 `batch-grill-me` 设计追问 | 主仓库 |
| tasks / spec delta | `tasks.md` + `specs/` delta，同步 backlog | 主仓库 |
| **building** | 按 tasks 测试先行实现（TDD） | **独立 worktree 必须** |
| **审阅闭环** | 见下节，PR 前必须完成 | building worktree |
| closing / PR | spec 同步、归档、跑 OpenSpec 校验 + artifact checker，发起 PR | 主仓库 |

### 强制审阅闭环（/review-loop）

**每次新 change 实现完成、发起 PR 前，必须运行 `/review-loop`**：spawn 独立零记忆 subagent 审阅 → 判 verdict → CHANGES_REQUESTED 则修复并加回归测试 → 再审，直到 **PASS 或 3 轮封顶**。

- 审阅维度（沿用 `scripts/workflow_methods.json` `building.reviewing_impl`）：任务逐项验证、正确性、Spec 对齐、冗余度、测试覆盖、安全性、可维护性、CI 完整性
- 报告产出到 `openspec/changes/<change-id>/reviews/building-review.md`（随 change 进 PR，CI 可机械校验），含 `PASS`/`CHANGES_REQUESTED`/`BLOCKED` verdict + 逐条任务验证 + 带 `文件:行号` 证据的 issues
- 审阅通过后生成 review manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）
- **机械强制**：`scripts/check_openspec_artifacts.py` 对非 docs + 有 spec delta + **tasks.md 全部 `[x]` 勾选**（实现完成）的 change 强制 building-review.md + manifest 存在且 PASS——缺审阅直接报错。这是 PR 合入前必跑的门禁；提案/部分实现的 change 不受此拦截
- 受保护 artifact（`docs/known-issues.md`、`docs/known-debt.md`、`openspec/specs/**`、`openspec/changes/archive/**`、`docs/openspec-change-backlog.md`）的修改仍需 `workflow-events.jsonl` 结构化解释事件；阶段 review report 需对应 review manifest

### Worktree 隔离规则

**任何涉及代码修改的操作（building / bug fix / 实验性改动），必须在独立 git worktree 中进行。**

**规则**：
- 分支命名：`<change-id>/<YYYY-MM-DD>`
- 禁止多个 change 共用同一个 worktree
- PR 合入并清理后关闭 worktree；已有 worktree 则复用，无需重建

### 验证命令速查

| 操作 | 命令 |
|------|------|
| 跑独立审阅闭环 | `/review-loop <change-id>` |
| 验证 building 审阅完成 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` |
| 全量 pytest | `uv run pytest -q` |
| OpenSpec strict validate | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` |

### ADR 创建规则

在以下情况必须创建 ADR（Architecture Decision Record）并放入 `docs/adr/`：

- planning 阶段做出了有 >= 2 个备选方案的设计决策
- building 阶段需要偏离 design.md 中的已有决策
- 审阅或人工评审要求记录某个决策的上下文

ADR 格式参考 `docs/adr/_TEMPLATE.md`。

### Agent 持久记忆

Agent 可以通过 SaveMemory 工具在 `~/.asterwynd/projects/<hash>/memory/` 维护跨 session 持久记忆。四类记忆：

- **user**: 用户角色、偏好、知识背景。当了解到用户的新偏好或角色信息时保存。
- **feedback**: 用户给出的反馈和规则。用户纠正你的行为或确认非显然方案时保存。
- **project**: 项目相关的非代码信息（截止日期、合规要求等）。保存事实和动机，不保存可从代码/git 推导的信息。
- **reference**: 外部资源指针（bug 跟踪、监控面板 URL 等）。保存资源位置和用途。

#### 保存时机

- 用户纠正你的方法或明确说"不要这样做"时，写入 feedback。
- 用户确认了非显然的方案选择时，写入 feedback。
- 了解到用户角色/偏好/知识背景时，写入 user。
- 了解到项目约束、截止日期、合规要求等时，写入 project。
- 了解到外部资源位置时，写入 reference。

#### 不保存的内容

- 代码模式、架构、文件路径（可从当前代码推导）
- Git 历史、最近变更（git log 是权威来源）
- 在当前 conversation 中即可完成的临时任务状态
- 已在 AGENTS.md / CLAUDE.md 中记录的内容

### Issue tracker

Issues 和 PRD 发布到 GitHub Issues，仓库为 `Xingkai98/asterwynd`。见 [Issue tracker](./docs/agents/issue-tracker.md)。

### Triage labels

使用 Matt Pocock skills 默认 triage 角色标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。见 [Triage labels](./docs/agents/triage-labels.md)。

### Domain docs

本仓库是 single-context：优先读取根目录 [CONTEXT.md](./CONTEXT.md)；只有存在且相关时才读取 `docs/adr/`。见 [Domain docs](./docs/agents/domain.md)。

## 常用命令

优先使用 `uv run` 保持依赖解析可复现。

```bash
uv sync --extra dev
uv run pytest -q
uv run pytest tests/agent/tools/test_registry.py -v
uv run asterwynd run "用 Read 工具读 /tmp"
uv run asterwynd web --port 8000
uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

更多命令见 [开发指南](./docs/development-guide.md)。

## 文档地图

- [项目定位](./docs/project-positioning.md): 说明项目目标、目标岗位、主线能力、支撑能力和能力证明链。
- [上下文词汇](./CONTEXT.md): 定义需求、路线图、面试材料和设计文档中使用的核心项目语言。
- [架构说明](./docs/architecture.md): 说明 AgentLoop、上下文注入管线、插件系统、工具系统、Web UI、LLM provider、benchmark 架构。
- [开发指南](./docs/development-guide.md): 记录安装、运行、常用命令、环境变量和开发注意事项。
- [测试指南](./docs/testing-guide.md): 记录测试分层、回归测试规则、CLI/Web/benchmark 覆盖要求。
- [需求流程](./docs/requirements-process.md): 规定后续每个功能如何先讨论、写需求文档、评审、实现和验收。
- [OpenSpec Change 实现队列](./docs/openspec-change-backlog.md): 记录当前未实现 OpenSpec changes，并按建议实现顺序排列。
- [OpenSpec 项目说明](./openspec/project.md): 记录当前能力域地图；`openspec/specs/` 是已确认规格，`openspec/changes/` 承载后续需求变更。
- [经验教训](./docs/lessons-learned.md): 记录历史问题、根因和后续开发必须吸取的教训。
- [Coding Agent 路线图](./docs/coding-agent-roadmap.md): 当前 coding-agent 能力建设路线图，后续需要按新项目定位继续修订。
- [Benchmark 方案](./docs/benchmark-plan.md): benchmark 任务、运行器、评测指标和结果文件设计。

## 当前文档债务

- `docs/coding-agent-roadmap.md`、`docs/benchmark-plan.md` 仍保留部分历史英文设计记录和旧阶段数据；后续整体改为中文并更新 benchmark 结果数据。

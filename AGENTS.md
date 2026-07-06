# AGENTS.md

本文件是编码 agent 和 Claude Code 进入本仓库时的入口说明。它只保留最高优先级规则和文档地图；详细背景请按链接读取对应文档。

> **维护规则**: `AGENTS.md` 是唯一维护入口。`CLAUDE.md` 只保留 `@AGENTS.md`，不再重复维护完整说明。`README.md` 是 README 源文档；修改 `README.md` 时必须在同一变更中同步更新 `README_EN.md` 的英文翻译，保持章节、命令和事实口径一致。

## 项目定位

Asterwynd 是一个面向大厂 Agent 相关开发岗位的 Coding Agent 系统项目。主线是 Agent 运行时、工具调用、上下文管理、代码修改、验证、可观测性和 benchmark 闭环；AI Infra、LLM、RAG、后端工程能力都作为支撑能力服务于这条主线。

项目词汇以 [CONTEXT.md](./CONTEXT.md) 为准。

## 最高优先级规则

- **文档语言**: 除 `README_EN.md` 作为 `README.md` 的英文同步翻译外，所有项目文档使用中文；代码、代码注释和公开 API 命名使用英文；提交信息使用中文。
- **需求先行**: 新功能必须先完成需求讨论和需求文档，再进入开发。没有把目标、边界、验收标准、测试策略聊清楚之前，不写实现代码。
- **设计追问**: 非平凡 OpenSpec change 进入实现前，必须使用 `grill-with-docs` skill 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响；如果当前环境没有该 skill，必须按同等标准充分追问并记录最终方案。用户要求“开始开发 / 实现 / 做某个 change”时，第一阶段必须先加载并声明使用 `grill-with-docs`，在逐项确认完成前不得写实现代码或测试代码；agent 可以给推荐答案，但不能把自己的推断当作用户确认。
- **问题定位**: 定位问题时，先查清根因并给出解决方案，待确认后再实际修改代码。
- **测试要求**: 每个 bug fix 必须新增回归测试；涉及 CLI、Web、benchmark、工具协议或 AgentLoop 的变更必须覆盖对应层级测试。
- **文档影响检查**: 收尾阶段必须检查文档影响，但不要无边界全量改文档。至少检查 change 自身 OpenSpec 文档、`docs/openspec-change-backlog.md`、文档地图中的相关入口文档，并用关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与本次变更相关的段落；只更新当前变更造成的事实变化，历史口径问题另记债务或单独处理。
- **OpenSpec 收尾**: OpenSpec change 的实现 PR 必须同时包含归档收尾：将已完成 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`，从 `docs/openspec-change-backlog.md` 移除，并运行 OpenSpec 校验和项目 artifact checker。PR 合入后只做确认：active change 目录不再存在、backlog 干净、本地 `master` 已快进到 `origin/master`。
- **自然语言路由**: 用户不需要反复提醒“按 OpenSpec lifecycle 走”。当用户用自然语言表达讨论、立项、开发、同步 spec、收尾或合入意图时，agent 必须自动映射到本文件的 OpenSpec 流程和 `/opsx:*` 等价步骤；如果当前客户端不能直接调用 slash command，也要按同等步骤执行。
- **协议约束**: 保持 tool-call 消息链合法；不要在 `max_iterations` 路径中用工具结果伪造最终 assistant 回复。
- **工作区约束**: 不提交 `.codegraph/`、`.understand-anything/`、`.dev/`、本地 `.env*`、日志、benchmark runs 等生成或本地文件，除非用户明确要求。
- **已有改动**: 可能存在用户未提交改动。不要回滚不是自己产生的改动；如果影响当前任务，先理解并基于它继续。

## 参考实现调研

当需要设计或对比某个 coding-agent 能力的实现方式时，应先查找当前工作区可用的参考仓库，并用 codegraph 加速调用链、类型关系和模块边界分析。

- 当前工作区参考仓库路径应写在本地配置 `.dev/reference-repos.txt` 中，每行一个目录路径；该文件不提交。
- 这些路径只是当前工作区的参考资料位置，不是项目依赖，也不要求其他开发者拥有相同目录结构。
- 不要把参考仓库路径、`.codegraph/` 产物或本地索引结果作为可提交项目资产；若需要沉淀结论，应写入本仓库的需求、设计、ADR 或讨论纪要。
- 调研时优先用 codegraph 理解跨文件关系，再用 `rg`、文件阅读和测试补充验证；不要只凭关键词搜索下结论。

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
| “开始开发 / 实现这个 change / 按 change 推进” | 先执行 `grill-with-docs` 开发前设计追问；确认完成后进入 `/opsx:apply` 等价流程，按 tasks 测试先行并实现。 |
| “同步 spec / 看正式规格有没有更新” | 进入 `/opsx:sync` 等价流程：把 change delta spec 合理合并到 `openspec/specs/`。 |
| “收尾 / 提 PR / 准备合入” | 进入 `/opsx:archive` 等价流程：在同一个实现 PR 内归档 change、清理 backlog、跑 OpenSpec 校验和 artifact checker，并写明验证结果。 |
| “合入 / merge” | 合入已准备好的 PR；合入后只确认本地 `master` 已同步、active change 目录不存在、backlog 不再引用已归档 change。 |

这些命令只负责 OpenSpec 子流程；仓库规则仍然更高优先级。尤其是：非平凡 change 开发前必须 `grill-with-docs`，bug fix 必须有回归测试，README 改动必须同步 `README_EN.md`，PR 发起前必须完成归档收尾。

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
uv run python cli.py main "用 Read 工具读 /tmp"
uv run python cli.py web --port 8000
uv run python cli.py benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke
```

更多命令见 [开发指南](./docs/development-guide.md)。

## 文档地图

- [项目定位](./docs/project-positioning.md): 说明项目目标、目标岗位、主线能力、支撑能力和能力证明链。
- [上下文词汇](./CONTEXT.md): 定义需求、路线图、面试材料和设计文档中使用的核心项目语言。
- [架构说明](./docs/architecture.md): 说明 AgentLoop、插件系统、工具系统、Web UI、LLM provider、benchmark 架构。
- [开发指南](./docs/development-guide.md): 记录安装、运行、常用命令、环境变量和开发注意事项。
- [测试指南](./docs/testing-guide.md): 记录测试分层、回归测试规则、CLI/Web/benchmark 覆盖要求。
- [需求流程](./docs/requirements-process.md): 规定后续每个功能如何先讨论、写需求文档、评审、实现和验收。
- [OpenSpec Change 实现队列](./docs/openspec-change-backlog.md): 记录当前未实现 OpenSpec changes，并按建议实现顺序排列。
- [OpenSpec 项目说明](./openspec/project.md): 记录当前能力域地图；`openspec/specs/` 是已确认规格，`openspec/changes/` 承载后续需求变更。
- [经验教训](./docs/lessons-learned.md): 记录历史问题、根因和后续开发必须吸取的教训。
- [Coding Agent 路线图](./docs/coding-agent-roadmap.md): 当前 coding-agent 能力建设路线图，后续需要按新项目定位继续修订。
- [Benchmark 方案](./docs/benchmark-plan.md): benchmark 任务、运行器、评测指标和结果文件设计。
- [讨论纪要](./docs/discussions/): 保存重要设计讨论和阶段性决策记录。

## 当前文档债务

- `docs/coding-agent-roadmap.md`、`docs/benchmark-plan.md` 仍保留部分历史英文设计记录；当前事实口径已经补齐，但后续如做文档整理，应整体改为中文并清理旧阶段叙述。

# AGENTS.md

本文件是编码 agent 和 Claude Code 进入本仓库时的入口说明。它只保留最高优先级规则和文档地图；详细背景请按链接读取对应文档。

> **维护规则**: `AGENTS.md` 是唯一维护入口。`CLAUDE.md` 只保留 `@AGENTS.md`，不再重复维护完整说明。

## 项目定位

MyAgent 是一个面向大厂 Agent 相关开发岗位的 Coding Agent 系统项目。主线是 Agent 运行时、工具调用、上下文管理、代码修改、验证、可观测性和 benchmark 闭环；AI Infra、LLM、RAG、后端工程能力都作为支撑能力服务于这条主线。

项目词汇以 [CONTEXT.md](./CONTEXT.md) 为准。

## 最高优先级规则

- **文档语言**: 所有项目文档使用中文；代码、代码注释和公开 API 命名使用英文；提交信息使用中文。
- **需求先行**: 新功能必须先完成需求讨论和需求文档，再进入开发。没有把目标、边界、验收标准、测试策略聊清楚之前，不写实现代码。
- **设计追问**: 非平凡 OpenSpec change 进入实现前，必须使用 `grill-with-docs` skill 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响；如果当前环境没有该 skill，必须按同等标准充分追问并记录最终方案。用户要求“开始开发 / 实现 / 做某个 change”时，第一阶段必须先加载并声明使用 `grill-with-docs`，在逐项确认完成前不得写实现代码或测试代码；agent 可以给推荐答案，但不能把自己的推断当作用户确认。
- **问题定位**: 定位问题时，先查清根因并给出解决方案，待确认后再实际修改代码。
- **测试要求**: 每个 bug fix 必须新增回归测试；涉及 CLI、Web、benchmark、工具协议或 AgentLoop 的变更必须覆盖对应层级测试。
- **协议约束**: 保持 tool-call 消息链合法；不要在 `max_iterations` 路径中用工具结果伪造最终 assistant 回复。
- **工作区约束**: 不提交 `.codegraph/`、`.understand-anything/`、`.dev/`、本地 `.env*`、日志、benchmark runs 等生成或本地文件，除非用户明确要求。
- **已有改动**: 可能存在用户未提交改动。不要回滚不是自己产生的改动；如果影响当前任务，先理解并基于它继续。

## 参考实现调研

当需要设计或对比某个 coding-agent 能力的实现方式时，应先查找当前工作区可用的参考仓库，并用 codegraph 加速调用链、类型关系和模块边界分析。

- 当前工作区参考仓库路径应写在本地配置 `.dev/reference-repos.txt` 中，每行一个目录路径；该文件不提交。
- 这些路径只是当前工作区的参考资料位置，不是项目依赖，也不要求其他开发者拥有相同目录结构。
- 不要把参考仓库路径、`.codegraph/` 产物或本地索引结果作为可提交项目资产；若需要沉淀结论，应写入本仓库的需求、设计、ADR 或讨论纪要。
- 调研时优先用 codegraph 理解跨文件关系，再用 `rg`、文件阅读和测试补充验证；不要只凭关键词搜索下结论。

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

- `README.md`、`README_EN.md`、`docs/coding-agent-roadmap.md`、`docs/benchmark-plan.md`、`docs/resume-description.md` 中存在历史口径，后续需要统一到“Agent 相关开发岗位导向”的项目定位。
- `README_EN.md` 是历史英文副本；是否保留需要后续单独决策。

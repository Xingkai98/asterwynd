# MyAgent OpenSpec 项目说明

## 项目目标

MyAgent 是一个面向大厂 Agent 相关开发岗位的 Coding Agent 系统项目。OpenSpec 是后续需求和能力规格的 source of truth，用来连接项目定位、实现行为、测试证据和面试叙事。

## 规格原则

- `openspec/specs/` 记录当前已经确认的系统规格。
- 当前规格只能描述代码和项目文档已经成立的行为。
- 尚未实现的能力域可以保留目录和状态说明，但不得写成已交付能力。
- 新功能必须先通过 `openspec/changes/<change-id>/` 描述需求 delta，再进入实现。
- 涉及 AgentLoop、工具协议、CLI、Web、benchmark、workspace safety 的变更必须同步测试策略。

## 文档语言

项目文档使用中文。代码、代码注释、公开 API、命令参数和文件名保持英文。提交信息使用中文。

## 能力域

- `agent-runtime`: AgentLoop、消息循环、停止条件和 tool-call 协议。
- `agent-modes`: 单轮、交互、Web、benchmark 等运行入口和未来模式边界。
- `planning`: 计划拆分和 todo 展示语义，当前为预留能力域。
- `tool-system`: 工具协议、注册、schema、执行、错误和权限元数据。
- `coding-tools`: 文件、搜索、编辑、命令和 diff 检查工具。
- `research-tools`: WebSearch、WebFetch 等联网研究工具。
- `workspace-safety`: 路径、敏感文件、命令和 git diff 安全边界。
- `memory-context`: 消息历史、AutoCompact 和上下文保留策略。
- `skills`: Markdown skill 加载、匹配和注入。
- `subagents`: 子 agent 委托、ParentChannel、结果回传和取消。
- `mcp-integration`: MCP 集成，当前为预留能力域。
- `code-intelligence`: LSP、符号、诊断和代码索引，当前为预留能力域。
- `browser-computer-use`: 浏览器和桌面操作，当前为预留能力域。
- `cli`: Typer 命令入口和非交互运行。
- `tui`: 终端 UI，当前为预留能力域。
- `web-ui`: FastAPI、WebSocket、Chat 和 Debug 页面。
- `benchmark`: 任务 schema、runner、artifact、hidden tests 和结果汇总。
- `change-documentation`: OpenSpec change 的 proposal、spec、design、diagnosis 和 tasks 文档流程。

## Change 文档约束

OpenSpec 的 `spec-driven` schema 已包含 `proposal`、`specs`、`design` 和
`tasks` artifacts。MyAgent 在此基础上采用以下项目级规则：

- 非平凡 change 必须包含 `design.md`，用于记录详细设计和关键技术取舍。
- bug、回归、工具不可用、故障复盘和调研驱动的 change 必须包含 `diagnosis.md`。
- `diagnosis.md` 记录症状、复现、证据、假设、根因、修复选项、推荐方案和回归测试要求。
- `design.md` 记录目标、非目标、当前架构、方案、接口、配置、错误处理、测试策略、替代方案和风险。
- `proposal.md` 不承载详细实现；spec delta 不承载问题定位过程；`tasks.md` 不替代设计。
- `proposal.md` 必须包含 `## Change Type`，声明 `primary` 和 `secondary` 类型。
- 项目文档规则按 `primary` 与 `secondary` 的类型并集校验；每个涉及类型的要求都必须满足。
- 新建 `tasks.md` 应参考 `openspec/templates/tasks.md`，保留通用验证项，并按影响面补充 benchmark、Web、TUI、browser 或外部集成 smoke。

当前 OpenSpec CLI 可通过 `openspec status --change <id>` 检查 schema
artifact 完成状态。`diagnosis.md` 属于项目条件规则，由项目本地文档规则脚本检查。

项目本地脚本只做机械校验：`Change Type` 合法、文件存在、必填章节存在、章节非空、没有模板占位符。设计内容是否合理不由脚本判断；开发前必须人工审核 `design.md` 并确认通过。

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


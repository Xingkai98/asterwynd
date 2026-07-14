# Asterwynd 上下文

Asterwynd 是一个以拿到大厂 offer 为目标的 Coding Agent 项目。本词汇表定义需求、路线图、面试材料和设计文档中使用的项目语言。

## 语言

**Offer 导向项目**:
一个以能否帮助拿到大厂工程岗位 offer 为判断标准的项目；设计、范围、证据和叙述都必须服务于这个目标。
_避免_: 兴趣项目、通用框架、演示项目

**目标岗位**:
以 Agent 相关开发为主线的工程岗位，同时要求候选人具备 AI Infra、LLM 应用、RAG 和后端工程基本能力。
_避免_: 纯后端岗位、纯算法岗位、纯前端岗位、泛 AI 应用岗位

**Coding Agent 系统**:
一个能够理解代码仓库、修改代码、运行验证、记录过程并报告结果的 agent 系统。
_避免_: 通用聊天机器人、泛化 agent 框架

**Code Intelligence**:
服务 Coding Agent 系统的只读代码理解能力；当前阶段包含 workspace-aware repo map、文件级结构摘要、Python AST 符号提取、tree-sitter 多语言语法级符号提取，以及 Python LSP 语义工具（定义跳转、引用、hover、文档符号、工作区符号和诊断）。
_避免_: 纯文本 grep、通用 RAG 知识库、无降级策略的全量语义索引承诺

**LSP**:
Language Server Protocol；一种为代码编辑器和 agent 提供定义跳转、引用、hover、诊断等语义能力的标准协议。当 LSP server 不可用时，系统可降级到 repo map 和 tree-sitter 符号提取。
_避免_: 语法高亮器、轻量 repo map、通用知识库

**Repo Map**:
面向 agent 上下文选择的仓库结构摘要，帮助 agent 快速识别源码、测试、配置、入口模块和可提取符号；它是运行时可再生成的只读产物，不是需要提交的长期索引文件。
_避免_: 全量文件树转储、语义引用图、持久向量索引

**Project Root Marker**:
用于标识某个子目录属于一个独立项目边界的文件或目录名，例如 `pyproject.toml`、`package.json`、`go.mod` 和 `Cargo.toml`。
_避免_: 语言后缀、本身就是 workspace root、任意文件路径

**主线能力**:
围绕 Agent 运行时、工具调用、上下文管理、任务执行、可观测性和评测闭环展开的核心能力。
_避免_: 平均铺开所有 AI 方向、只堆功能点

**支撑能力**:
服务于主线能力表达的 AI Infra、LLM、RAG 和后端工程能力；它们用于增强项目深度，而不是替代 Agent 开发主线。
_避免_: 无边界扩展、为了覆盖而覆盖

**能力证明链**:
从面试要求到项目能力、实现、测试、benchmark 证据和面试讲述点之间的可追踪链路。
_避免_: 功能列表、路线图条目、简历 bullet

**需求讨论**:
针对单个能力点，在开发前明确目标、边界、行为、测试和验收标准的讨论过程。
_避免_: 随口想法、实现备注

**Agent Mode**:
一次 Agent 运行的顶层权限意图，用于约束工具可见性、工具执行权限和运行记录；具体路径、文件和命令安全仍由工作区策略约束。
_避免_: 仅靠 prompt 的行为建议、具体工具实现细节、工作区路径规则

**Tool Capability**:
工具能力；描述一个工具能够执行哪类操作，例如读取工作区、写入工作区、执行命令、读取网络资源、产生外部副作用、修改 agent state 或控制浏览器。它回答“工具能做什么”，不回答“工具来自哪里”或“风险多高”。
_避免_: 工具来源、风险等级、具体工具名称

**Tool Risk Level**:
工具风险等级；描述工具默认安全风险，例如 low、medium、high。它回答“这个工具默认风险多高”，不回答“工具来自哪里”。高风险工具可能来自内置工具，也可能来自外部工具。
_避免_: 外部来源标记、是否只读、mode 名称

**Tool Origin**:
工具来源；描述工具由哪个来源提供，例如 builtin、mcp、plugin、subagent 或 browser。它用于审计、展示、默认策略推导和排查，不应直接替代权限判定。
_避免_: dangerous 标记、风险等级、工具能力

**Permission Profile**:
Agent Mode 绑定的工具权限配置，用 capability、risk level、origin 和 allow/deny override 决定工具可见性和执行权限。它让 `plan`、`read_only`、`build` 等 mode 不必硬编码为某个 boolean 组合。
_避免_: 单个工具权限、WorkspacePolicy 路径规则、用户审批流程

**Plan Mode**:
一种面向分析、方案制定和人工确认的 Agent Mode；它在只读权限边界内产出可审批的 Plan Document，并可同步生成机器可读的 Planning State。
_避免_: 执行实现、任务调度器、执行期 todo list

**Planning State**:
一次 Agent 运行中的结构化计划状态，描述 Plan Document 中可跟踪的步骤、每个步骤的状态以及简要说明；它是运行时可观察状态，不是 Plan Document 本身，也不是执行调度器。
_避免_: 完整设计文档、任务队列、人工审批流

**Plan Item**:
Planning State 中的单个可跟踪步骤，包含稳定标识、内容、状态和可选说明；它可作为执行期 todo 的输入，但不等同于已经开始执行的任务。
_避免_: 整个计划文档、后台任务、工具调用记录

**Plan Document**:
Plan Mode 产出的人读 Markdown 方案，说明目标理解、实施步骤、风险、边界和建议验证方式；它可以先作为草案随讨论更新，定稿后成为人工确认和后续 build mode 执行的依据。
_避免_: Planning State、执行期 todo list、自动审批结果

**Session ID**:
一次面向用户的连续交互会话标识；Web 中对应一个浏览器聊天会话，CLI 交互模式中对应一个 REPL 会话，未来 TUI 中对应一个 TUI 会话。一个 Session 可以贯穿多个 workflow phase，并产生多个 Run ID。
_避免_: 单次 Agent 运行、benchmark 批次编号、鉴权凭证

**Run ID**:
一次 executor 处理 WorkItem 或用户 turn 的可复制运行标识；同一个 Session ID 下可以产生多个 Run ID，后台更换 executor 也不要求用户更换 Session。
_避免_: 交互式会话、benchmark 批次编号、分布式 tracing 标识

**Managed Workspace Root**:
显式加入 Workflow Control Plane 路径列表的项目根目录；只有位于该目录或其已识别 Git worktree 中的 agent session 才启用开发流程管理。
_避免_: 任意当前目录、自动猜测的项目目录、普通 workspace root

**Workflow Bypass**:
当前 session 因启动路径不属于任何 Managed Workspace Root 而完全绕过 Workflow Control Plane 的固定状态；旁路判定必须在调用模型前完成，整个 session 不自动重新判定，且不得注入 workflow prompt 或消耗额外模型 token。
_避免_: exploring phase、未创建 change、workflow blocked

**Exploration Workflow**:
受管项目中新 session 在没有恢复目标时自动创建的轻量工作流，用于承载闲聊探索、方向讨论和需求形成前的连续状态；未进入 Requirements 且未产生结构化产出时可以按老化策略自动放弃。
_避免_: 普通未受管对话、正式 Requirements、OpenSpec change

**Workflow Output**:
Exploration Workflow 中被控制面显式记录的结构化成果，例如需求摘要、已确认决策、调研结论或 artifact 引用；draft/proposed output 不阻止老化，只有经 Human Acceptance 或正式 gate snapshot 引用的 durable output 才阻止 empty exploration aging。
_避免_: 聊天消息、token 使用量、临时思考过程

**Natural Language Gate Decision**:
用户在当前 session 中通过受配置白名单约束的完整消息表达 gate 批准；该决定由 host 在消息进入模型前精确匹配并绑定当前 gate 和状态版本，不能由 agent 转述、模糊解释或补造。
_避免_: 同义词猜测、Agent 总结的用户意图、自由文本 actor 字段、未绑定 gate 的普通“继续”

**Gate Approval Token**:
配置中允许批准当前唯一 pending gate 的完整用户消息；V1 默认白名单仅包含精确字符串 `ok`，不做模糊匹配或语义分类。
_避免_: 关键词包含、正则猜测、大小写自动推断、LLM 意图识别

**CLI 交互模式**:
一个低依赖的多轮终端入口，适合 SSH、无浏览器环境和最小调试路径；它长期保留，但不承接复杂多面板终端体验。
_避免_: TUI 替代品、完整终端工作台、废弃入口

**Workflow Prompt Adapter**:
通过 Codex/Claude/Happy Coder 等客户端已有的 skill、prompt 或 `AGENTS.md` 接入说明调用 `workflow enter/report/status` 的轻量兼容方式；它不侵入宿主客户端，但只能提供软约束、状态恢复和审计提示，不能宣称等同 Host Wrapper 的可信 gate 或写权限强制。
_避免_: Host Wrapper、可信批准能力、进程级 sandbox、Happy Coder 原生插件

**TUI**:
未来面向复杂多轮终端体验的交互界面，承接工具结果展开、Planning State、diff/test 面板和快捷键等能力；它复用核心运行语义，不替代 CLI 单轮运行或 CLI 交互模式的低依赖入口价值。
_避免_: 另起一套运行协议、普通 CLI 输出、多轮 CLI 的简单别名

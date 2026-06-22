## Context

当前 agent 主要依赖文本搜索定位代码。多文件任务中，纯 grep 容易漏掉模块关系、符号定义和测试入口，也需要较多工具调用才能形成可用上下文。完整 LSP 或向量索引成本较高，不适合作为第一步。

参考实现显示 coding-agent 类产品通常有两层能力：文件/仓库索引用于快速定位上下文，LSP 或更强语义层用于 definition、references、diagnostics。Aider 的 repo map 更接近第一层，Claude Code 和 opencode 同时保留文件索引与 LSP 工具。本 change 只实现第一层的 MyAgent 版本：workspace-aware repo map 基础设施，并以 Python AST 作为首个结构化 extractor。

## Goals / Non-Goals

**Goals:**

- 生成 workspace 范围内的轻量 repo map。
- repo map 覆盖多语言文件级扫描，包含源码、测试、配置和文档文件的路径、类型、分类和大小摘要。
- 提取 Python module、class、function、method 和 import 摘要，作为首个可替换 extractor。
- 提供只读工具查询 repo map 和符号。
- 扫描遵守 workspace policy 和 ignore rules。
- 输出可用于 benchmark trace，证明 agent 更快定位本仓库的 AgentLoop、ToolRegistry、WorkspacePolicy 和对应测试入口。

**Non-Goals:**

- 不实现完整 LSP。
- 不做 tree-sitter 多语言符号提取。
- 不做跨语言引用分析、诊断或类型推断。
- 不接外部向量数据库。
- 不让 code intelligence 工具修改文件。

## Decisions

### Decision 1: Repo map 是上下文选择基础设施，不是低配 LSP

repo map SHALL 优先服务 agent 的上下文选择：快速暴露源码、测试、配置、入口模块和可提取符号。它不承诺定义跳转、引用分析、诊断或类型信息。

理由：当前项目目标是尽快证明 coding agent 能更好理解本仓库；LSP 能力复杂且依赖语言服务器，不适合塞进第一阶段。

### Decision 2: 使用可替换 extractor 接口承载 Python AST

首版 extractor 使用 Python 标准库 `ast` 提取 Python 符号和 import，不执行用户代码。repo scanner 和 repo map 输出不应绑定 Python AST 细节；后续 tree-sitter 或 LSP 能以新 extractor / provider 接入。

理由：安全、可测试、依赖少，足以覆盖当前 MyAgent 仓库；同时避免未来多语言能力推倒重来。

### Decision 3: Repo map 是运行时可再生成产物

repo map 按 workspace 和 ignore rules 生成，可按需刷新，不作为长期源文件提交。

理由：避免索引过期污染仓库，同时减少重复扫描成本。

### Decision 4: 工具保持只读

新增工具只返回文件、符号和摘要，不提供编辑入口。

理由：代码理解能力应受 workspace safety 管控，编辑仍由 Write/Edit 负责。

## Risks / Trade-offs

- [Risk] AST 提取无法理解动态导入。Mitigation: 初版记录静态 imports，动态行为留给后续能力。
- [Risk] Python AST 容易被误读为“只支持 Python 仓库”。Mitigation: repo map 做多语言文件级扫描，文档明确 Python AST 只是首个 extractor。
- [Risk] 当前能力被误读为 LSP 替代品。Mitigation: specs 明确不提供 definition、references、diagnostics、hover 或类型信息，并新增后续 LSP change。
- [Risk] 大仓库扫描慢。Mitigation: 遵守 ignore rules，限制文件类型和输出大小。
- [Risk] 摘要过粗。Mitigation: trace 记录查询，后续根据任务反馈扩展字段。

## Testing Strategy

- 单元测试覆盖 Python symbol extraction。
- workspace policy 测试覆盖忽略目录、敏感路径和 workspace 外路径。
- 工具测试覆盖 schema、输出限制和错误处理。
- 小型 fixture repo 测试覆盖 repo map 生成。
- benchmark smoke 覆盖一个本仓库定位任务，验收 trace 中 code intelligence 工具能帮助定位 AgentLoop、ToolRegistry、WorkspacePolicy 或相关测试入口。

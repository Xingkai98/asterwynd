## Context

当前 agent 主要依赖文本搜索定位代码。多文件任务中，纯 grep 容易漏掉模块关系、符号定义和测试入口。完整 LSP 或向量索引成本较高，不适合作为第一步。

本 change 先实现轻量 repo map 和 Python symbol extraction。

## Goals / Non-Goals

**Goals:**

- 生成 workspace 范围内的轻量 repo map。
- 提取 Python module、class、function、method 和 import 摘要。
- 提供只读工具查询 repo map 和符号。
- 扫描遵守 workspace policy 和 ignore rules。

**Non-Goals:**

- 不实现完整 LSP。
- 不做跨语言深度语义索引。
- 不接外部向量数据库。
- 不让 code intelligence 工具修改文件。

## Decisions

### Decision 1: 使用静态 AST 提取 Python 符号

先用 Python 标准库 `ast` 提取符号和 import，不执行用户代码。

理由：安全、可测试、依赖少，足以覆盖当前 Python 项目主线。

### Decision 2: Repo map 是缓存产物

repo map 按 workspace 和 ignore rules 生成，可按需刷新，不作为长期源文件提交。

理由：避免索引过期污染仓库，同时减少重复扫描成本。

### Decision 3: 工具保持只读

新增工具只返回文件、符号和摘要，不提供编辑入口。

理由：代码理解能力应受 workspace safety 管控，编辑仍由 Write/Edit 负责。

## Risks / Trade-offs

- [Risk] AST 提取无法理解动态导入。Mitigation: 初版记录静态 imports，动态行为留给后续能力。
- [Risk] 大仓库扫描慢。Mitigation: 遵守 ignore rules，限制文件类型和输出大小。
- [Risk] 摘要过粗。Mitigation: trace 记录查询，后续根据任务反馈扩展字段。

## Testing Strategy

- 单元测试覆盖 Python symbol extraction。
- workspace policy 测试覆盖忽略目录、敏感路径和 workspace 外路径。
- 工具测试覆盖 schema、输出限制和错误处理。
- 小型 fixture repo 测试覆盖 repo map 生成。

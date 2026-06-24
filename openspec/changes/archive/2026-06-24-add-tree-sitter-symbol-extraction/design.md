## Context

第一阶段 repo map 提供 workspace-aware 文件级扫描和 Python AST 符号提取。它解决当前 MyAgent 仓库的快速定位问题，但对非 Python 仓库只能返回文件级条目。

Tree-sitter 可以在不启动语言服务器的情况下，为多语言代码提供稳定语法树和 query-based symbol extraction。它适合作为 LSP 之前的第二阶段 code intelligence。

## Goals / Non-Goals

**Goals:**

- 引入 tree-sitter 作为多语言结构化解析层。
- 支持一组明确语言的 symbol extraction：Python 继续使用现有 AST extractor；tree-sitter 首批覆盖 TypeScript/JavaScript、Go 和 Rust。
- 复用第一阶段 repo scanner、WorkspacePolicy、ignore patterns、输出格式和只读工具。
- 让 repo map / symbol 查询返回多语言结构化摘要。

**Non-Goals:**

- 不实现 LSP 语义能力。
- 不提供 definition、references、diagnostics、hover、rename 或类型推断。
- 不做跨文件调用图或引用图。
- 不接语义向量索引。

## Decisions

### Decision 1: tree-sitter 作为 extractor，不替代 repo scanner

Tree-sitter 只负责已允许读取文件的语法解析和符号提取；workspace 扫描、ignore rules、denied path 过滤和输出截断继续由 repo map 基础设施负责。

理由：保持安全边界集中，避免每个语言 extractor 重复实现 workspace policy。

### Decision 2: 每种语言显式注册 grammar 和 query

系统 SHALL 维护 language registry，记录扩展名、tree-sitter grammar、symbol query 和 import/export query。未注册语言只保留文件级 repo map 条目。

理由：tree-sitter 核心通用，但 grammar 和 query 是语言相关的；显式注册能避免“假多语言”。

### Decision 3: 输出保持 repo map / symbol search 稳定形状

新增语言的符号 SHALL 复用第一阶段 Symbol 数据模型，并通过 `language` 或 `source` 字段标识 extractor 来源。

理由：让 AgentLoop、tool output、trace 和未来 LSP provider 不因 parser 替换而破坏接口。

### Decision 4: tree-sitter 文件大小上限来自统一配置

Tree-sitter extractor SHALL 通过 `myagent.yaml` 的 `tools.code_intelligence.tree_sitter_max_file_bytes` 控制单文件解析上限，默认值为 `262144`。入口层解析配置后显式传给工具和 repo map，底层 code intelligence 模块不隐式读取配置文件。

理由：大文件解析上限是工具策略配置，不应硬编码在 extractor 内；复用统一配置也符合现有配置发现和优先级规则。

### Decision 5: 首批符号范围保持语法级

TypeScript/JavaScript 首批提取 class、function、method、arrow/function variable、interface/type 和 import/export 名称；Go 首批提取 function、method、struct 和 interface；Rust 首批提取 function、impl method、struct、enum 和 trait。Python 继续由现有 AST extractor 提取 module-level function、class、method 和 import。

理由：首版只承诺语法级结构摘要，不做类型推断、引用关系或跨文件语义。

## Risks / Trade-offs

- [Risk] tree-sitter 依赖和 grammar 包增加安装复杂度。Mitigation: 先覆盖少量高价值语言，并将缺失 grammar 降级为文件级条目。
- [Risk] 不同语言 query 质量不一致。Mitigation: 为每种语言建立 fixture 测试，并在输出中标识语言和 extractor。
- [Risk] 大仓库解析成本上升。Mitigation: 延续输出限制，增加可配置解析文件大小上限。
- [Risk] 用户误以为 tree-sitter 提供引用/类型语义。Mitigation: specs 明确 tree-sitter 只提供语法级 symbol，不提供 LSP 语义能力。

## Testing Strategy

- 为每个支持语言新增 tree-sitter fixture symbol extraction 测试。
- 测试未注册语言只返回文件条目，不伪造符号。
- 测试 grammar 缺失、文件超过配置上限或解析失败时 repo map 降级而不失败。
- 测试工具 schema 和输出仍保持第一阶段兼容。
- 用一个多语言 fixture benchmark smoke 验证 repo map 能定位目标文件和符号。

## Context

语法级搜索（Grep、SymbolSearch）依赖精确的符号名或正则表达式。对于"修改所有类似的错误处理模式"这类任务，agent 需要先构想正则，再反复调整。语义搜索让 agent 用自然语言描述意图即可找到相关代码。

## Decisions

### 1. Embedding 模型选择

默认使用 `all-MiniLM-L6-v2`（sentence-transformers）：
- 开源、本地运行、无需 GPU。
- 384 维向量，内存/磁盘开销小。
- 虽然不是 code-specific 模型，但对自然语言描述找代码的效果可接受。

可通过配置切换为 code-specific 模型（如 `jina-embeddings-v2-base-code`），配置路径：`config.code_intelligence.embedding_model`。

### 2. 索引存储

方案对比：

| 方案 | 优点 | 缺点 |
|------|------|------|
| `sqlite-vec` | 零依赖（SQLite 扩展）、纯本地、和现有 sqlite 使用一致 | 较新、生态不如 ChromaDB |
| `ChromaDB` | 成熟、Python 原生 | 额外进程依赖、重 |
| `faiss-cpu` | Facebook 出品、高性能 | 无元数据存储、需自己搭 |

选择 **`sqlite-vec`**：
- 零额外服务进程，启动成本低。
- 嵌入已有的 sqlite 使用模式（项目已在 LSP 和其他地方用 sqlite）。
- `sqlite-vec` 支持 SIMD 加速的向量搜索。

### 3. 索引内容

索引单元 = 函数/方法级别的代码片段。使用 tree-sitter 将每个函数切分为独立的 chunk：

```python
@dataclass
class CodeChunk:
    file_path: str
    function_name: str
    start_line: int
    end_line: int
    code_text: str
    embedding: list[float] | None  # lazy computed
```

索引粒度选择函数/方法级而非文件级或行级：
- 文件级太粗：一个 500 行的文件匹配到不知道具体位置。
- 行级太细：单行代码缺乏足够语义。
- 函数级刚好：自包含语义单元，搜索结果可直接定位。

### 4. 构建策略

两种触发方式：

1. **随 RepoMap 构建（配置开关）**：`RepoMap` 生成时可选同步生成 embedding 索引。通过 `config.code_intelligence.enable_embedding_index: bool` 控制。
2. **懒构建（默认）**：首次调用 `SearchSimilar` 时触发，遍历仓库提取函数并生成 embedding。

初始采用懒构建策略，避免 RepoMap 生成变慢。

### 5. 增量更新

`SearchSimilar` 执行时：
1. 检查已索引文件的 mtime，失效已修改文件的旧条目。
2. 扫描新增文件，补充索引。
3. 仅对新/修改文件重新 embedding。

不主动监控文件变更——依赖搜索时的被动探测。

### 6. SearchSimilar 工具设计

```
SearchSimilar(query: str, top_n: int = 5) -> str
```

- `query`：自然语言描述或代码片段
- `top_n`：返回结果数（默认 5）
- 返回：每行 `file_path:start_line-end_line: function_name — relevance_score`

工具能力：`WORKSPACE_READ` / `LOW` risk。

### 7. 降级行为

- sentence-transformers 未安装 → `SearchSimilar` 注册但不工作，返回明确的 "embedding 模型不可用" 错误。
- 索引构建超时（>60s）→ 只索引已完成的文件，返回部分结果 + 警告。
- 空仓库或无可提取函数 → 返回 "无可用索引"。

## Goals / Non-Goals

- 不支持跨仓库语义搜索。
- 不支持自然语言生成代码（仅搜索已有代码）。
- 不支持代码变更的语义 diff。
- 不支持图片或多模态 embedding。
- 不做分布式或远程索引。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 的语义搜索是如何实现的？
2. 开源 embedding 模型对代码的语义理解效果如何？
3. sqlite-vec vs ChromaDB 的选择？

- findings:

- Claude Code 没有公开其语义搜索实现细节，但其 `Grep` 工具的描述暗示主要依赖正则搜索而非语义搜索。Cursor 和 Copilot 使用 embedding-based 代码搜索作为核心体验。
- `all-MiniLM-L6-v2` 在自然语言→代码的语义匹配上效果中等（比 code-specific 模型差 10-20%），但胜在轻量、本地、零成本。随着项目发展可升级模型。
- `sqlite-vec` v0.0.1 已稳定，支持余弦相似度、欧氏距离搜索，Python binding 完善。ChromaDB 功能更全但引入了客户端-服务端架构开销。
- Aider 使用 tree-sitter 将代码分割为函数级 chunks 并做 embedding 索引，其 `repo_map.py` 支持 `--map-tokens` 参数控制 token 预算——这与本 change 的索引粒度一致。

- design impact:

- 采用 sqlite-vec 以保持轻量和零服务依赖。
- 函数级 chunk 与 Aider 的实践一致，提供可解释的搜索结果。
- 懒构建策略避免 RepoMap 的性能回退。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| code_intelligence 模块 | 新增 embedding 和 index 子模块 |
| RepoMap | 可选集成索引构建，默认不影响 |
| 工具系统 | 新增 SearchSimilar 工具 |
| pyproject.toml | 新增 sentence-transformers、sqlite-vec 依赖 |
| 首次启动 | 懒构建可能耗时（大仓库几十秒），需有进度提示 |
| MCP / benchmark / workspace safety | 不影响 |


## Risks / Trade-offs

- [Risk] 首次懒构建在大型仓库可能耗时数分钟。Mitigation: 构建过程输出进度提示，超时后返回部分结果。
- [Risk] embedding 模型依赖 `sentence-transformers` 包，增加安装成本。Mitigation: 标记为可选依赖，模型不可用时工具明确报错而非崩溃。
- [Risk] 函数级 chunk 对 C/Go 的非面向对象代码切分效果差。Mitigation: 对无法切分的文件降级为文件级 chunk。

## Testing Strategy

- embedding 生成测试：Python 函数生成 384 维向量。
- sqlite-vec 索引测试：创建/查询/更新/增量失效。
- SearchSimilar 工具测试：自然语言查询、代码片段查询。
- 降级测试：模型不可用、空仓库、超时。
- 懒构建性能测试：中等仓库 < 60s。
## Cancellation Record

**决策**: 取消此 change，归档不实现。

**日期**: 2026-07-09

**原因**:

1. **与 CONTEXT.md 冲突**: 项目词汇表明确将 "持久向量索引" 列为 Code Intelligence 和 Repo Map 的 _避免_ 项。本 change 的核心交付物（sqlite-vec 持久向量索引）直接违反该约束。
2. **优先级不匹配**: 当前 benchmark 瓶颈在执行可靠性（多文件任务、跨文件 trace propagation、task 拆解），而非搜索多样性。现有 Grep + SymbolSearch + RepoMap + LSP 工具已覆盖 agent 当前搜索需求。
3. **路线图对齐**: 项目差异化定位是 "explainable, reproducible, benchmarkable local coding agent"，优先投入 benchmark 通过率比引入体验类搜索功能更有证明力。

**后续**: 如未来需增强代码搜索能力，建议先探索基于 tree-sitter AST 结构相似度的轻量方案，避免引入 embedding 模型和持久向量索引的复杂度。

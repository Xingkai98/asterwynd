## Why

当前代码智能工具（`RepoMap`、`SymbolSearch`、Grep、LSP 符号系列）全部是语法/结构级的。缺少基于语义的相似代码搜索能力。

Claude Code、Cursor、Copilot 均支持 embedding-based 语义搜索，让 agent 能问"这里有没有类似这段错误处理的代码"、"找一下和这个函数签名相似的所有实现"。语法级搜索（Grep 按正则）无法捕捉意图相似性。

该能力补齐后，code-intelligence 域从 "语法级" 扩展到 "语法级 + 语义级"，是 coding agent 代码理解能力的自然升级。

## What Changes

- 新增 `agent/code_intelligence/embeddings.py`：基于 sentence-transformers 的代码 embedding 生成器（默认 `all-MiniLM-L6-v2`，可配置为 code-specific 模型）。
- 新增 `agent/code_intelligence/index.py`：基于 `sqlite-vec` 或 `ChromaDB` 的本地 embedding 索引，存储文件路径 + 代码片段 + embedding 向量。
- 新增 `SearchSimilar` 工具：输入自然语言查询或代码片段，返回语义最相似的 Top-N 文件位置和代码片段。
- 索引构建：作为 `RepoMap` 生成流程的扩展步骤（可选，通过配置开关），或首次调用 `SearchSimilar` 时懒构建。
- 增量更新：文件修改后失效该文件对应的索引条目，下次搜索时增量重建。

## Capabilities

### Modified Capabilities

- `code-intelligence`: 新增 embedding 生成、向量索引和 `SearchSimilar` 语义搜索工具。

## Impact

- 影响代码：
  - `agent/code_intelligence/embeddings.py`（新增）
  - `agent/code_intelligence/index.py`（新增）
  - `agent/tools/builtin/code_intelligence.py`（新增 SearchSimilar）
  - `agent/code_intelligence/repo_map.py`（扩展：集成索引构建）
  - `pyproject.toml`（新增依赖：sentence-transformers 或 chromadb）
- 影响测试：
  - `tests/agent/code_intelligence/test_embeddings.py`
  - `tests/agent/code_intelligence/test_index.py`
  - `tests/agent/tools/test_code_intelligence.py`
- 不影响：现有搜索工具、workspace safety、AgentLoop。

## Change Type

- primary: feature

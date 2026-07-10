## 1. 规格

- [ ] 1.1 更新 `code-intelligence` spec delta：定义语义搜索能力、embedding 模型、索引存储和 SearchSimilar 工具。
- [ ] 1.2 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.3 维护 `## Impact Analysis`。
- [ ] 1.4 维护 `## Reference Implementation Research`。

- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [ ] 2.1 embedding 生成测试：Python 函数生成 384 维向量。
- [ ] 2.2 索引测试：创建/查询/更新 sqlite-vec 索引。
- [ ] 2.3 SearchSimilar 工具测试：自然语言查询返回相关函数。
- [ ] 2.4 code chunk 提取测试：tree-sitter 正确提取函数级 chunk。
- [ ] 2.5 增量更新测试：修改文件后旧索引失效、新文件被索引。
- [ ] 2.6 降级测试：sentence-transformers 不可用时返回明确错误。
- [ ] 2.7 降级测试：空仓库返回"无可用索引"。
- [ ] 2.8 懒构建性能测试：中等仓库（100+ 函数）构建时间 < 60s。

## 3. 实现

- [ ] 3.1 实现 `agent/code_intelligence/embeddings.py` —— embedding 模型加载和编码。
- [ ] 3.2 实现 `agent/code_intelligence/index.py` —— sqlite-vec 索引创建和查询。
- [ ] 3.3 实现 tree-sitter 函数级 chunk 提取（复用现有 tree-sitter 符号提取）。
- [ ] 3.4 在 `code_intelligence.py` 新增 `SearchSimilar` 工具。
- [ ] 3.5 接入 factory.py，注册 SearchSimilar 到 coding tool registry。
- [ ] 3.6 更新 `pyproject.toml`：添加 sentence-transformers 和 sqlite-vec 依赖。
- [ ] 3.7 配置项：`config.code_intelligence.embedding_model` 和 `enable_embedding_index`。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 手动验证：用一个已知代码片段搜索，验证结果相关性。

- [ ] 4.5 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-semantic-code-search/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。

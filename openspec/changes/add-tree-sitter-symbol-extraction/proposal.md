## Why

`add-repo-map-code-intelligence` 首版只用 Python AST 提取结构化符号。它能证明 MyAgent 在当前 Python 仓库中更快定位上下文，但不能覆盖用户可能带来的 TypeScript、JavaScript、Go、Rust 等多语言仓库。

Tree-sitter 适合作为 LSP 之前的多语言结构化解析层：它比 grep 更懂语法，比 LSP 更轻，不需要启动语言服务器，也不承诺引用、诊断或类型信息。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 tree-sitter parser / grammar registry。
- 新增 tree-sitter query registry，用于按语言提取 class、function、method、import/export 等符号摘要。
- 将 tree-sitter extractor 接入既有 repo map extractor 接口。
- repo map 和 symbol 查询工具 SHALL 返回多语言结构化符号。
- 扫描、解析和输出 SHALL 继续遵守 WorkspacePolicy、ignore patterns 和输出限制。
- 通过 `myagent.yaml` 的 `tools.code_intelligence.tree_sitter_max_file_bytes` 配置 tree-sitter 单文件解析上限。

## Capabilities

### Modified Capabilities

- `code-intelligence`: 从 Python-only structured symbol 扩展到 tree-sitter 多语言 symbol extraction。
- `coding-tools`: 只读 repo map / symbol 工具可返回多语言符号摘要。
- `workspace-safety`: 多语言解析仍不得绕过 workspace read policy。
- `configuration`: 增加 code intelligence 工具策略配置。

## Impact

- 影响代码：
  - `agent/code_intelligence/`
  - tree-sitter 依赖与语言 grammar 注册
  - `agent/tools/builtin/` code intelligence 工具输出
  - `agent/config.py` 和入口层工具配置注入
- 影响测试：
  - `tests/agent/code_intelligence/`
  - `tests/agent/tools/`
- 不实现 LSP definition、references、diagnostics、hover、rename 或类型推断。
- 不接向量库或语义检索。

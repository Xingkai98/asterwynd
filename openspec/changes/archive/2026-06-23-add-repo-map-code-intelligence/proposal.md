## Why

当前 agent 依赖 Grep、Find、ListFiles 和 Read 做文本级代码定位。多文件任务中，agent 需要多轮工具调用才能拼出仓库入口、模块边界、工具实现和测试入口，容易漏掉相关文件。

本 change 先实现 workspace-aware repo map 基础设施，并以 Python AST 作为首个结构化符号提取器。目标不是交付低配 LSP，而是让 coding agent 更快选择本仓库任务所需上下文，并为后续 tree-sitter / LSP 能力保留稳定接口。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 repo scanner，按 workspace policy 和 ignore rules 扫描 workspace 内的源码、测试、配置和文档文件。
- 新增 repo map 输出格式，返回路径、文件类型、源码/测试/配置分类、大小/行数和可提取结构摘要。
- 新增 Python AST 符号提取器，覆盖 module、class、function、method 和 import 摘要，并作为后续多语言 extractor 的首个实现。
- 新增只读工具暴露 repo map 和 Python 符号查询。
- trace SHALL 记录 code intelligence 工具调用。

## Capabilities

### Modified Capabilities

- `code-intelligence`: 从预留能力域升级为 repo map 基础设施和 Python symbol 能力。
- `coding-tools`: 增加只读代码理解工具。
- `workspace-safety`: code intelligence 扫描必须遵守 workspace policy。

## Impact

- 影响代码：
  - `agent/code_intelligence/`
  - `agent/tools/builtin/`
  - `agent/tools/__init__.py`
- 影响测试：
  - `tests/agent/code_intelligence/`
  - `tests/agent/tools/`
- 不实现完整 LSP、不做跨语言语义索引、不接外部向量库。
- 不实现 tree-sitter 多语言符号提取；该能力由后续 `add-tree-sitter-symbol-extraction` change 承接。
- 不实现 LSP definition、references、diagnostics、hover 或 workspaceSymbol；该能力由后续 `add-lsp-code-intelligence` change 承接。

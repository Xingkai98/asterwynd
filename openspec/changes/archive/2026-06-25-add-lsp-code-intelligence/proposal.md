## Why

Repo map 和 tree-sitter 能帮助 agent 快速选择上下文和提取语法级符号，但不能回答定义跳转、引用、hover、诊断、实现关系和调用层级等语义问题。

成熟 coding agent 通常通过 LSP 获得这些能力。MyAgent 需要在 repo map 基础设施稳定后，引入 LSP 作为更强的 code intelligence provider。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 LSP server 配置、发现和进程生命周期管理。
- 新增文档打开/同步、请求超时、错误处理和状态观测。
- 新增只读 LSP 工具或 provider，支持 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics。
- Write/Edit/ApplyPatch 类修改后 SHALL 能触发 LSP diagnostics 并把可读结果反馈给 agent。
- LSP 能力 SHALL 遵守 workspace policy、agent mode 和工具权限边界。

## Capabilities

### Modified Capabilities

- `code-intelligence`: 增加 LSP 语义能力。
- `coding-tools`: 新增只读 LSP 工具或扩展 code intelligence 工具。
- `workspace-safety`: LSP server 启动、文件读取和诊断输出必须受安全边界约束。

## Impact

- 影响代码：
  - `agent/code_intelligence/`
  - `agent/lsp/`
  - `agent/tools/builtin/`
  - Write/Edit/patch 类修改工具的诊断反馈路径
  - 配置加载路径
- 影响测试：
  - `tests/agent/lsp/`
  - `tests/agent/tools/`
  - `tests/agent/code_intelligence/`
- 优先使用 fake LSP server 做协议和工具测试。
- 不实现自动安装任意 language server；语言服务器发现和配置必须显式、可审计。

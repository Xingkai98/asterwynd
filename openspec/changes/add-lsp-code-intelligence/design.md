## Context

Repo map 和 tree-sitter 解决的是“看见仓库结构”和“提取语法级符号”。LSP 解决的是更重的语义问题：定义、引用、hover、诊断、实现关系和调用层级。

LSP 需要启动外部 language server，处理初始化、文档同步、请求超时、错误恢复和进程清理。它的收益更高，风险也更高，因此应在 repo map 和基础 workspace safety 稳定后单独实现。

## Goals / Non-Goals

**Goals:**

- 引入 LSP server 配置、发现和生命周期管理。
- 提供只读 LSP code intelligence 能力。
- 支持 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics。
- 编辑后能把 LSP diagnostics 反馈给 agent，形成更强验证闭环。
- 让 LSP 能力遵守 workspace policy、agent mode 和工具权限。

**Non-Goals:**

- 不自动安装任意 language server。
- 不把 LSP 作为 repo map 的唯一数据源。
- 不实现复杂 IDE 功能，例如 rename、code action、formatting 或实时补全。
- 不绕过现有 Write/Edit 工具做文件修改。

## Decisions

### Decision 1: LSP 是 code intelligence provider，不替代 repo map

LSP SHALL 作为更强语义 provider 接入 code intelligence，但 repo map 仍负责轻量上下文选择和文件级结构摘要。

理由：LSP 依赖语言服务器和项目环境，可能不可用；repo map 必须保持低成本、可降级。

### Decision 2: 使用显式配置和 fake server 测试

首版 SHALL 支持显式 LSP server 配置和 fake LSP server 测试，不自动下载或安装语言服务器。

理由：自动安装带来供应链、权限和平台复杂度，不适合作为首版。

### Decision 3: LSP 工具保持只读，诊断反馈接入写工具结果

LSP 查询工具 SHALL 是只读工具。Write/Edit/patch 类工具可以在成功修改后触发 diagnostics，并把诊断作为工具结果附加信息返回。

理由：保持修改权仍由现有编辑工具控制，同时让诊断进入 agent 反馈闭环。

## Risks / Trade-offs

- [Risk] language server 启动慢或不稳定。Mitigation: 配置超时、状态观测和 graceful degradation。
- [Risk] 外部进程扩大安全边界。Mitigation: 显式配置、workspace 限制、权限审计和进程清理。
- [Risk] LSP 结果过大。Mitigation: 对 references、workspaceSymbol 和 diagnostics 做数量/字符截断。
- [Risk] 多语言 server 行为不一致。Mitigation: 用 fake server 验证协议层，再为少数真实 server 做 smoke。

## Testing Strategy

- fake LSP server 覆盖 initialize、document sync、definition、references、hover、symbols 和 diagnostics。
- 工具测试覆盖 schema、权限、超时、错误和输出截断。
- workspace safety 测试覆盖 workspace 外路径、denied paths 和 LSP server 访问边界。
- 编辑工具测试覆盖修改后 diagnostics 反馈。
- benchmark smoke 覆盖一个需要根据 diagnostics 修复代码的任务。

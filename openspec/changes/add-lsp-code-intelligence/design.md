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

### Decision 4: LSP 配置挂在 CodeIntelligenceConfig.lsp 子字段

LSP 配置 SHALL 作为 `CodeIntelligenceConfig` 的 `lsp` 子字段存在，结构为 `LspConfig`，包含 `servers: tuple[LspServerConfig, ...]`、`default_request_timeout_ms`、`max_diagnostics_per_file` 等字段。每个 `LspServerConfig` 包含 `language`、`command`（tuple[str,...]）、`args`、`root_markers`（tuple[str,...]，例如 `pyproject.toml`、`package.json`）、`initialize_timeout_ms`、`request_timeout_ms`、`enabled`。按 language 匹配 server（一种语言一个 server），用 `root_markers` 找 project root。

理由：LSP 是 code intelligence 的一种 provider，挂在 `CodeIntelligenceConfig` 下语义最一致；单独包成 `LspConfig` 子字段避免扁平化后字段膨胀，且为未来扩展（如 `max_references`、`workspace_symbol_limit`）留位置。

### Decision 5: LSP server 进程级单例 + lazy start + atexit/进程组清理

LSP client SHALL 按 (language, workspace_root) 缓存单例，第一次请求时 lazy 启动（initialize → initialized），agent run 结束时统一 shutdown。进程清理 SHALL 同时使用 `atexit` 注册和进程组 spawn，确保父进程退出时子进程随之退出。请求超时不立即 kill server，标记 unhealthy，下次请求仍超时则 shutdown 重启。文档同步 SHALL 采用按需 didOpen（只在被查询文件未同步时才同步）+ Write/Edit 后 didChange（agent 修改文件后自动同步给 LSP），不主动全量 didOpen。

理由：LSP 的价值在于复用索引状态，每次启停会让 definition/references 慢到不可用；跨 agent run 常驻 daemon 引入进程归属复杂度，首版不上；全量 didOpen 对大仓库过重，按需同步配合 Edit 后 didChange 保证 LSP 看到的是 agent 当前视图。

### Decision 6: 六个 LSP 能力拆成六个独立 tool

LSP SHALL 暴露六个独立只读 tool：`LspDefinition`、`LspReferences`、`LspHover`、`LspDocumentSymbols`、`LspWorkspaceSymbols`、`LspDiagnostics`。diagnostics 底层 provider 函数（`LspClient.diagnostics(path)`）同时给 `LspDiagnostics` tool 和 Write/Edit 内部调用复用，tool 壳只是给 agent 暴露的入口。

理由：拆分让每个 tool schema 简单清晰、模型容易用对；trace_recorder 按能力统计调用频次和耗时，benchmark 按 tool 粒度分析 agent 行为，符合项目主线（可观测性 + 评测闭环）。diagnostics 跟另外五个不对称（既是 agent 主动查的 tool、也是 Write/Edit 内部反馈通道），但底层 provider 共享，tool 壳独立不混淆。

### Decision 7: diagnostics 在 Write/Edit 成功修改后总是触发

Write/Edit 成功修改后 SHALL 总是调用 `LspClient.diagnostics(path)`，把诊断摘要以简单行列表（`path:line:col [severity] message`，截断到最多 N 条、每条最大 M 字符）追加到工具返回。无可用 LSP server 时 SHALL 快速跳过（不等超时），不影响 Write/Edit 本身的延迟。

理由：design.md 明确要求"SHALL 能在文件修改后请求 LSP diagnostics，并将相关诊断以可读形式反馈"，按需触发会让验证闭环断在 agent 自觉性上；快速跳过路径保证无 LSP 场景不被拖慢；简单行列表跟现有 tool 返回风格（InspectGitDiff、Bash）一致。

### Decision 8: LSP server 限写不限读 + project root 强制在 workspace 内

LSP server SHALL 禁止任何 write 操作（首版不实现 `workspace/applyEdit`、`codeAction` 等 write 类方法），但读取不限于 workspace 内（允许读 stdlib、依赖目录等 server 正常工作所需路径）。`root_markers` 找到的 project root 若在 workspace 外，SHALL 回退到 workspace root 本身并 warn，不越界扫描 workspace 外兄弟目录。

理由：限写不限读靠"不实现 write 方法"天然满足，实现成本最低且不破坏 server 功能；硬拦 server 读 stdlib/依赖会让 server 报错或降级。root 强制在 workspace 内是"agent 活动边界"的硬承诺，跟 `workspace_policy.assert_within_workspace` 一致，越界回退让 server 仍能工作但不扫描 workspace 外。

## Risks / Trade-offs

- [Risk] language server 启动慢或不稳定。Mitigation: 配置超时、状态观测和 graceful degradation。
- [Risk] 外部进程扩大安全边界。Mitigation: 显式配置、workspace 限制、权限审计和进程清理。
- [Risk] LSP 结果过大。Mitigation: 对 references、workspaceSymbol 和 diagnostics 做数量/字符截断。
- [Risk] 多语言 server 行为不一致。Mitigation: 用 fake server 验证协议层，再为少数真实 server 做 smoke。

## Testing Strategy

- **单元测试（in-process fake transport）**：`LspClient` 抽象出 `LspTransport` 接口（send_request/recv_response/send_notification），测试注入 `FakeLspTransport` 返回预设响应，覆盖 initialize、didOpen、didChange、definition、references、hover、documentSymbol、workspaceSymbol、diagnostics 的 happy path 和协议边界 case。
- **集成测试（真实 fake server 脚本）**：`tests/fixtures/fake_lsp_server.py` 作为独立 stdio LSP server 进程，覆盖 spawn、stdio 帧解析、initialize 握手、请求/响应配对、initialize 超时、request 超时、atexit 清理、进程组退出等真实进程路径。case 数量精简，只跑关键 happy path + 超时 + 进程清理。
- **工具测试**：六个 LSP tool 各自覆盖 schema 校验、workspace policy 拒绝、agent mode 拒绝、超时返回可读错误、references/diagnostics/workspaceSymbol 输出截断。
- **workspace safety 测试**：root_markers 在 workspace 外时回退到 workspace root 并 warn；LSP server 访问 denied path 时不返回结果；workspace 外路径的 didOpen 被拒绝。
- **编辑工具测试**：Write/Edit 成功修改后触发 `LspClient.diagnostics(path)`，诊断摘要追加到工具返回；无可用 server 时快速跳过且不改 Write/Edit 本身行为。
- **benchmark smoke**：在 `benchmarks/tasks/` 新增独立 LSP 诊断任务，task 里故意留一个类型错误或未定义符号，agent 需靠 LSP diagnostics 定位并修复；Docker 镜像装一个 language server（如 pylsp）。run config 打开 LSP，验证 agent 能利用 diagnostics 闭环修复。

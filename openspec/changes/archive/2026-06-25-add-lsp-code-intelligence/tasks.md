## 1. 规格

- [ ] 1.1 修改 code-intelligence 规格，定义 LSP provider 和语义能力（definition/references/hover/documentSymbol/workspaceSymbol/diagnostics）。
- [ ] 1.2 修改 coding-tools 规格，定义六个 LSP 只读 tool（LspDefinition/LspReferences/LspHover/LspDocumentSymbols/LspWorkspaceSymbols/LspDiagnostics）和编辑后 diagnostics 反馈要求。
- [ ] 1.3 修改 workspace-safety 规格，定义 LSP server 进程边界（限写不限读、project root 强制在 workspace 内、atexit/进程组清理）。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 开发前使用 `grill-with-docs` 审视 `design.md`，确认 config schema、生命周期、工具拆分、diagnostics 反馈、workspace safety、测试策略、依赖选择、文档影响。决策已写入 design.md Decision 4-8 和细化 Testing Strategy。

## 2. 测试

- [ ] 2.1 新增 in-process fake transport 单测：覆盖 initialize/didOpen/didChange/definition/references/hover/documentSymbol/workspaceSymbol/diagnostics 的 happy path 和协议边界。
- [ ] 2.2 新增真实 fake server 集成测试：`tests/fixtures/fake_lsp_server.py` 覆盖 spawn、stdio 帧解析、initialize 握手、请求/响应配对、initialize 超时、request 超时、atexit 清理、进程组退出。
- [ ] 2.3 新增六个 LSP tool 各自的 schema 校验、workspace policy 拒绝、agent mode 拒绝、超时返回可读错误、输出截断测试。
- [ ] 2.4 新增 workspace safety 测试：root_markers 在 workspace 外回退并 warn、denied path 不返回结果、workspace 外路径 didOpen 被拒绝。
- [ ] 2.5 新增 Write/Edit 成功修改后触发 diagnostics 反馈测试：诊断摘要追加到工具返回、无可用 server 快速跳过。

## 3. 实现

- [ ] 3.1 新增 `agent/lsp/` 模块：config（LspConfig/LspServerConfig 挂在 CodeIntelligenceConfig.lsp）、JSON-RPC 帧解析、LSP 消息 dataclass、LspTransport 抽象接口。
- [ ] 3.2 新增 LspClient：按 (language, workspace_root) 缓存单例、lazy start、initialize 握手、按需 didOpen、didChange 同步、atexit + 进程组清理、超时标记 unhealthy + 重启。
- [ ] 3.3 新增六个 LSP 只读 tool，注册到 factory 和 KNOWN_BUILTIN_TOOL_NAMES，接入 ModePolicy。
- [ ] 3.4 将 diagnostics 反馈接入 Write/Edit：成功修改后调 `LspClient.diagnostics(path)`，简单行列表格式截断追加，无 server 快速跳过。diagnostics provider 函数同时给 LspDiagnostics tool 复用。
- [ ] 3.5 新增状态观测、超时、错误和输出截断：references/workspaceSymbol/diagnostics 数量和字符截断、可读错误信息、graceful degradation。
- [ ] 3.6 root_markers 发现与回退：在 workspace 内向上找 root_markers，命中 workspace 外则回退到 workspace root 并 warn。

## 4. 验证

- [ ] 4.1 运行 LSP 单测、集成测试、tool 测试和 workspace safety 测试。
- [ ] 4.2 运行全量测试（`uv run pytest -q`），确认 Write/Edit diagnostics 接入不破坏现有 tool 行为。
- [ ] 4.3 在 `benchmarks/tasks/` 新增独立 LSP 诊断 benchmark task，Docker 镜像装 language server，跑通 agent 利用 diagnostics 闭环修复的 smoke。
- [ ] 4.4 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。

## 5. 文档

- [ ] 5.1 微调 CONTEXT.md LSP 词条，点明"LSP 在本项目中作为 code intelligence 的语义 provider，按需启用，可降级到 repo map 和 tree-sitter"。
- [ ] 5.2 更新 docs/architecture.md，补 LSP provider 在 code intelligence 架构里的位置。
- [ ] 5.3 更新 docs/coding-agent-roadmap.md，把 LSP 状态从"计划中"推进。
- [ ] 5.4 更新 docs/development-guide.md，补 `tools.code_intelligence.lsp` YAML 配置示例和说明。
- [ ] 5.5 更新 myagent.example.yaml，补 `tools.code_intelligence.lsp` 示例配置块。
- [ ] 5.6 README.md/README_EN.md 只提一句 LSP 已接入，详情指向 docs（历史口径问题不在本 change 处理）。
- [ ] 5.7 先读 docs/testing-guide.md 和 docs/benchmark-plan.md，按其结构决定是否补 LSP 测试设施和 benchmark task 说明。

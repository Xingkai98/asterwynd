## 1. 规格

- [x] 1.1 修改 browser-computer-use 规格，定义 URL、凭据、截图、超时和审计策略。
- [x] 1.2 修改 tool-system 规格，定义 browser tools 权限元数据。
- [x] 1.3 修改 workspace-safety 规格，定义 browser artifact 存储边界。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`（收尾时统一同步）。
- [x] 1.5 开发前使用 `grill-with-docs` 审视 `design.md`，确认每个关键实现细节。
- [x] 1.6 开发前补实 `## Reference Implementation Research`，调研 Claude Code、Codex、OpenHands 等 browser use 安全边界，并回写 findings / design impact。

## 2. 测试

- [ ] 2.1 新增 BrowserPolicy URL allowlist 匹配/拒绝单元测试。
- [ ] 2.2 新增 browser tool 超时和错误返回测试。
- [ ] 2.3 新增 screenshot artifact 存储路径受 WorkspacePolicy 约束的测试。
- [ ] 2.4 新增 browser tools 受 mode policy 控制的测试。
- [ ] 2.5 新增 browser tool schema 和权限元数据校验测试。
- [ ] 2.6 新增 BrowserService（fake）单元测试。

## 3. 实现

- [ ] 3.1 新增 `BrowserConfig` 配置到 `agent/config.py`（ToolsConfig 下），含 enabled、url_allowlist、idle_timeout、各超时配置。
- [ ] 3.2 新增 `agent/browser/policy.py` — BrowserPolicy：URL allowlist 校验、超时、artifact 路径。
- [ ] 3.3 新增 `agent/browser/session.py` — BrowserSession：单页面封装（navigate/get_content/screenshot/scroll）。
- [ ] 3.4 新增 `agent/browser/service.py` — BrowserService：Playwright 实例生命周期、标签页集合管理。
- [ ] 3.5 新增 7 个 browser 工具（`agent/tools/builtin/browser_*.py`）：
  - BrowserNavigate、BrowserGetContent、BrowserScreenshot、BrowserScroll、BrowserListTabs、BrowserSwitchTab、BrowserCloseTab
- [ ] 3.6 新增 `agent/tools/builtin/browser.py` — 工具共用基础：`BROWSER_READ_PERMISSION` 常量、BrowserTool 基类。
- [ ] 3.7 在 `agent/tool_permissions.py` 新增 `BROWSER_READ_PERMISSION` 常量。
- [ ] 3.8 在 `agent/tools/factory.py` 注册 browser tools 到默认 registry（受 `BrowserConfig.enabled` 控制）。
- [ ] 3.9 接入 ToolRegistry、mode policy 和 trace。
- [ ] 3.10 Playwright lazy import，缺失时优雅降级。

## 4. 验证

- [ ] 4.1 运行 browser policy 和 tool 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 手动运行 browser smoke（需 Playwright 环境）。
- [ ] 4.4 运行 OpenSpec strict validate。
- [ ] 4.5 跑通至少一个 benchmark smoke。

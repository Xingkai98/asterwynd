## Context

Asterwynd 当前没有 browser/computer use 工具。浏览器能力会引入外部网络访问、截图 artifact、凭据暴露和页面副作用风险，因此不能直接把通用 Playwright API 暴露给 agent。

本 change 只建立最小浏览器工具和安全基础，服务后续可控的网页观察能力。

## Goals / Non-Goals

**Goals:**

- 提供最小 Playwright-backed 浏览器工具。
- URL 访问、截图保存和工具权限受 WorkspacePolicy 与 agent mode 约束。
- 浏览器工具调用可审计、可测试、可禁用。
- 默认拒绝未允许的 URL 和本地敏感文件访问。

**Non-Goals:**

- 不实现任意桌面操作。
- 不暴露鼠标键盘任意输入。
- 不处理真实登录态自动化。
- 不绕过站点反爬、验证码或权限控制。

## Decisions

### Decision 1: 先做受控浏览器服务层

新增 `agent/browser/` 封装 Playwright 生命周期、URL 校验、超时和 artifact 路径，再由工具调用服务层。

理由：避免每个工具各自管理浏览器实例和安全校验。

### Decision 2: 工具权限显式标注

浏览器工具默认不是纯 read-only。截图、导航和页面读取都必须带权限元数据，并由 mode policy 过滤。

理由：浏览器访问可能产生外部副作用，不能等同于本地 Read/Grep。

### Decision 3: Artifact 只写入受控目录

截图和后续浏览器产物写入 workspace 内受控 artifact 目录，并复用敏感路径拒绝规则。

理由：浏览器产物可能包含页面内容或凭据，必须可追踪、可清理。

## Pre-Implementation Review

完成于 2026-07-11，使用 `grill-with-docs` 逐项审视。以下为确认结论：

- **Scope**: 拆为两个 change。当前 change 只做受控只读浏览器观察基础（7 个工具），交互能力（click、type）放到后续 change。
- **URL Allowlist**: 精确域名 + 通配符子域名（`*.example.com`），仅 `https://`，默认空列表，配置在 `BrowserConfig.url_allowlist`。
- **工具集**: BrowserNavigate、BrowserGetContent、BrowserScreenshot、BrowserScroll、BrowserListTabs、BrowserSwitchTab、BrowserCloseTab。
- **权限元数据**: 新增 `BROWSER_READ_PERMISSION`（capability=BROWSER_CONTROL, risk=MEDIUM, origin=BROWSER）。ModePolicy 控制：build mode 暴露全部 browser tools 但截图需审批；read_only mode 可暴露只读部分但禁截图。
- **Artifact 路径**: `<workspace_root>/.asterwynd/browser-artifacts/`，写入前走 `WorkspacePolicy.assert_write_allowed()`。
- **Browser 生命周期**: 懒启动 + AgentLoop 级生命周期，`idle_timeout` 默认 300s。
- **超时**: navigation 30s, read 15s, screenshot 10s，超时返回 `[Browser Error: ...]` 而非异常。
- **Playwright 依赖**: 保持可选依赖（`dev` extra），lazy import，缺失时返回 `[Browser not available: playwright not installed]`。
- **测试**: 单元测试必跑；集成测试用 `pytest.mark.playwright` 标记，默认跳过。
- **BrowserConfig**: `enabled: false` 默认关闭，显式开启后才暴露 browser tools。
- **Codex 的意见**: 同意拆为两个 change，当前 change 作为受控只读基础；交互能力需动作级审批、页面状态 preflight 和凭据防护，应独立 change。

- Remaining risks:
  - Playwright 安装成本可能影响新人上手体验（通过 lazy import + 默认 disabled 缓解）。
  - URL allowlist 初始为空，需文档引导用户配置。

## Risks / Trade-offs

- [Risk] Playwright 依赖增加安装成本。Mitigation: 将浏览器集成测试标记为可选，核心单元测试使用 fake service。
- [Risk] URL allowlist 过严影响可用性。Mitigation: 初始策略保守，后续通过 change 明确放宽。
- [Risk] 截图泄露敏感内容。Mitigation: 默认 artifact 路径受控，并在 trace 中记录来源。

## Testing Strategy

- 单元测试 URL allowlist、拒绝本地文件、超时和 artifact 路径。
- 工具测试覆盖 schema、权限元数据和错误输出。
- 可选 Playwright 集成测试覆盖打开页面、读取标题和截图。
- OpenSpec 校验覆盖 browser/computer use、tool-system 和 workspace-safety delta。

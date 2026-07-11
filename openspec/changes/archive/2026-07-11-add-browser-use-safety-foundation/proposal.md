## Why

浏览器和桌面操作风险高：可能访问外部站点、暴露凭据、保存截图或执行不可逆操作。OpenSpec 已明确要求先定义安全边界，再增加 browser/computer use 工具。

本 change 只建立浏览器操作的安全基础和最小 Playwright 工具，不扩展到桌面输入或任意 GUI 自动化。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 定义 browser use 的 URL allowlist、凭据处理、截图存储、超时和审计策略。
- 新增最小 Playwright-backed 浏览器工具，例如打开页面、读取标题/文本、截图。
- 工具 SHALL 是受控的、可审计的，并受 agent mode policy 约束。
- 默认不得访问未允许 URL，不得读取本地敏感文件，不得执行登录后破坏性操作。

## Capabilities

### Modified Capabilities

- `browser-computer-use`: 从预留能力域升级为最小浏览器工具安全基础。
- `tool-system`: 增加 browser tools 权限元数据。
- `workspace-safety`: 截图和浏览器 artifact 存储受 workspace policy 约束。

## Impact Analysis

- 影响代码：
  - `agent/browser/`
  - `agent/tools/builtin/`
  - 依赖声明
- 影响测试：
  - browser tool 单元测试
  - 可选 Playwright 集成测试
- 不实现桌面截图、鼠标键盘任意输入，不处理真实登录态自动化。

## Reference Implementation Research

- status: enabled
- reason: 浏览器工具风险高，必须参考其他 coding-agent 对 URL allowlist、凭据边界、截图 artifact、超时和审计的处理。
- research questions:
  - 其他 coding-agent 如何限制浏览器访问范围、登录态和截图保存？
  - browser/computer use 工具如何接入 mode policy、workspace safety 和 trace？
  - 哪些 browser smoke 可以本地稳定运行，哪些必须保持人工或可选验证？
- findings:
  - **Claude Code**: WebFetch（只读抓取，预批准 ~80 个代码文档域名，三层权限检查）+ Claude in Chrome（Chrome 扩展 via MCP 桥接，完整交互：导航/点击/输入/截图/录 GIF/读控制台，ask/skip_all/follow_a_plan 三种权限模式）。WebBrowserTool 由内部 feature flag 控制，未开源。
  - **Codex**: 外部 MCP browser connector（`browser_navigate`、`access_browser_origin`，Playwright 实现）+ 内置 `web.run` 工具（search/open/click/find/screenshot via Responses API）。NetworkDomainPermissions 使用 glob 模式 allow/deny（deny 优先），4 级审批（Auto/Prompt/Approve/Never）+ Guardian AI 自动审查 + 会话级记住批准。
  - **OpenHands**: BrowserGym + Playwright（SDK 外部依赖），10 个工具：navigate、click、type、get_state、get_content、scroll、go_back、list_tabs、switch_tab、close_tab。Screenshot + URL + DOM/axtree 通过 WebSocket 实时传到前端。Docker 沙箱隔离（无 URL allowlist），安全确认模式 + 风险等级（LOW/MEDIUM/HIGH）。
  - **Gemini CLI / Goose / Qwen Code / Aider / KiloCode**: 主要为 `web_fetch`/`web_search` 只读抓取，无完整 browser use 交互能力。
- design impact:
  - 拆为两个 change：当前 change 收敛为"受控只读浏览器观察基础"（7 个工具：navigate、get_content、screenshot、scroll、list_tabs、switch_tab、close_tab），交互能力（click、type）放到后续 change。
  - URL allowlist 采用精确域名 + 通配符子域名匹配，仅 https，默认空列表。
  - BrowserService 作为独立的 `agent/browser/` 模块封装 Playwright 生命周期，工具不直接接触 Playwright API。
  - Artifact 固定路径 `<workspace>/.asterwynd/browser-artifacts/`。
  - Playwright 保持可选依赖，通过 lazy import 处理缺失场景。

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

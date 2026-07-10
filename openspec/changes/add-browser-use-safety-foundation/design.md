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

- Questions resolved:
  - 本 change 尚未按当前新增的 Impact Analysis / Pre-Implementation Review 规则完成开发前设计追问。
- Options considered:
  - 保留原设计，等待开始开发时完整追问。
  - 在本次流程治理 change 中伪造完整追问结论。
- Rejected alternatives:
  - 伪造完整追问结论。原因：该 change 尚未进入实现阶段，必须在真正开发前重新结合当前代码、权限模型和测试策略确认。
- Final confirmations:
  - 开发前必须重新使用 `grill-with-docs` 或等价设计追问确认 URL policy、artifact 路径、权限元数据、超时、凭据边界和测试策略。
- Remaining risks:
  - 浏览器能力风险高，后续设计追问可能要求调整当前 scope 或依赖顺序。

## Risks / Trade-offs

- [Risk] Playwright 依赖增加安装成本。Mitigation: 将浏览器集成测试标记为可选，核心单元测试使用 fake service。
- [Risk] URL allowlist 过严影响可用性。Mitigation: 初始策略保守，后续通过 change 明确放宽。
- [Risk] 截图泄露敏感内容。Mitigation: 默认 artifact 路径受控，并在 trace 中记录来源。

## Testing Strategy

- 单元测试 URL allowlist、拒绝本地文件、超时和 artifact 路径。
- 工具测试覆盖 schema、权限元数据和错误输出。
- 可选 Playwright 集成测试覆盖打开页面、读取标题和截图。
- OpenSpec 校验覆盖 browser/computer use、tool-system 和 workspace-safety delta。

## Context

工具结果既是模型上下文的一部分，也是用户调试界面的信息。展示层需要减少噪声，但不能丢失 trace 中的真实内容。

## Goals / Non-Goals

**Goals:**

- WebFetch 默认折叠展示。
- 长工具结果有统一摘要。
- 展示折叠不影响 trace、messages 或工具返回值。

**Non-Goals:**

- 不改变工具真实返回内容。
- 不压缩 LLM 上下文。
- 不做长期 artifact 浏览器。

## Decisions

### Decision 1: 折叠属于展示策略

工具执行结果和 trace 仍保留完整内容，Web/CLI/TUI 只决定如何展示。

### Decision 2: WebFetch 先默认折叠

WebFetch 是最明确的长内容来源；后续可按长度阈值扩展到 Bash、Read 等工具结果。

### Decision 3: 折叠阈值从 YAML 配置读取

工具结果展示阈值属于非敏感、结构化的本地策略，放入 `myagent.yaml` 的 `tools.display` 配置段：

- `tools.display.max_result_chars` 默认 `4000`
- `tools.display.max_result_lines` 默认 `80`
- `tools.display.preview_chars` 默认 `1200`

WebFetch 工具结果默认折叠；其他工具结果在字符数或行数超过阈值时折叠/摘要。该配置只从 YAML 读取，不增加环境变量覆盖，保持与 `tools.ignore_patterns` 和 `tools.command_denylist` 一致。

### Decision 4: CLI 交互模式保留为低依赖入口

CLI 单轮运行长期作为脚本、CI、benchmark smoke 和快速命令入口。CLI 交互模式长期保留为 SSH、无浏览器环境和最小调试路径下的多轮 fallback，但不追求复杂展开 UI。未来 TUI 承接主要复杂多轮终端体验，包括工具结果展开、planning、diff/test 面板和快捷键。

因此本 change 中 CLI 只需要避免长工具结果刷屏：短结果直接展示，长结果展示摘要和长度信息；完整交互式展开优先由 Web UI 提供，未来 TUI 复用同一 display policy。

## Risks / Trade-offs

- [Risk] 折叠隐藏关键信息。Mitigation: 展示摘要、长度和展开入口。
- [Risk] 各端行为不一致。Mitigation: 抽象 display policy 并写入 CLI/Web/TUI 规格。
- [Risk] 阈值配置过低导致常用短结果频繁折叠。Mitigation: 默认阈值只覆盖明显长结果，用户可在 `myagent.yaml` 调整。
- [Risk] CLI 交互模式被误解为完整 TUI。Mitigation: 文档明确 CLI 是低依赖 fallback，复杂多轮终端体验由未来 TUI 承接。

## Testing Strategy

- Web 测试覆盖默认折叠和展开。
- CLI 测试覆盖长结果摘要。
- Trace 测试确认完整 observation 不变。
- 配置测试覆盖 `tools.display` 默认值、YAML 读取和非法正整数校验。

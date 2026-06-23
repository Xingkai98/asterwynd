## ADDED Requirements

### Requirement: CLI 支持长工具结果摘要

CLI SHALL 对长工具结果展示摘要，并提示用户可通过 trace 或显式展开机制查看完整内容。长结果阈值 SHALL 使用统一 display policy，默认从代码默认值加载，并允许通过 `myagent.yaml` 的 `tools.display` 配置覆盖。

#### Scenario: CLI 显示长 WebFetch 结果

- **GIVEN** WebFetch 返回长内容
- **WHEN** CLI 展示工具结果
- **THEN** CLI SHALL 避免无边界刷屏
- **AND** SHALL 保留定位完整内容的方式

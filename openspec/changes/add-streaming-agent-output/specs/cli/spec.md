## ADDED Requirements

### Requirement: CLI 实时输出 assistant delta

CLI SHALL 在支持 streaming 的运行路径中实时打印 `assistant_delta.delta`。当最终 `llm_response` 带 `streamed: true` 时，CLI SHALL NOT 再次打印该完整文本；非 streaming 路径 SHALL 继续打印 `llm_response.content`。

#### Scenario: CLI 收到 text delta

- **GIVEN** CLI 正在运行 Agent
- **WHEN** runtime 发布 `assistant_delta`
- **THEN** CLI SHALL 实时输出该 delta
- **AND** 当 runtime 随后发布 `llm_response(streamed=true)` 时，CLI SHALL NOT 重复输出该 content

#### Scenario: CLI 非流式输出

- **GIVEN** provider 不支持 streaming
- **WHEN** runtime 发布普通 `llm_response`
- **THEN** CLI SHALL 输出 `llm_response.content`

## MODIFIED Requirements

### Requirement: 多模态 Message 内容

Message 的 `content` 字段 SHALL 支持 `str`（纯文本）和 `list[ContentBlock]`（多模态）两种类型。`ContentBlock` SHALL 支持 `text` 和 `image_url` 两种类型。`str` 类型 SHALL 保持完全向后兼容。

#### Scenario: 纯文本内容不变

- **GIVEN** Message 的 content 为 `str` 类型
- **WHEN** 任意现有代码路径处理该 Message
- **THEN** 行为 SHALL 与改动前完全一致

#### Scenario: 多模态 content 序列化

- **GIVEN** Message 的 content 为 `[TextBlock("解读这张图"), ImageBlock(url="data:image/png;base64,...")]`
- **WHEN** 序列化为 JSON
- **THEN** content SHALL 序列化为 content blocks 数组
- **AND** deserialize 后 SHALL 还原为相同的 content blocks 数组

### Requirement: ToolResult 多模态内容

`ToolResult` SHALL 新增 `content_blocks: list[ContentBlock] | None` 字段。当工具返回了图片或其他非文本内容时，`content_blocks` SHALL 携带结构化内容。AgentLoop 在构建消息时 SHALL 优先使用 `content_blocks`。

#### Scenario: Read 工具读取图片

- **GIVEN** Read 工具读取了一个 PNG 文件
- **WHEN** 工具执行完成
- **THEN** ToolResult.content_blocks SHALL 包含一个 ImageBlock
- **AND** AgentLoop 在构建消息时 SHALL 使用该 ImageBlock

#### Scenario: 普通文本工具结果

- **GIVEN** Read 工具读取了一个 .py 文件
- **WHEN** 工具执行完成
- **THEN** ToolResult.content_blocks SHALL 为 None
- **AND** AgentLoop 在构建消息时 SHALL 使用 ToolResult.output（文本）
